"""Adapter tests against a real engine process: the assistant flow, policy, error mapping and config safety."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from tracefold_mcp.config import AdapterConfig, ConfigError, load_config, validate_base_url, write_config
from tracefold_mcp.server import build_server

from .conftest import FIXED, RISKY, Engine, _git

pytestmark = pytest.mark.anyio

TOOLS = {"get_capabilities", "list_workspaces", "scan_changes", "get_scan", "cancel_scan", "get_findings",
         "explain_finding", "recheck_fix"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def cfg(engine: Engine, who: str = "mcp", ws: str = "ws_demo") -> AdapterConfig:
    return AdapterConfig(base_url=engine.base, token=engine.tokens[who], workspace_id=ws)


async def call(client: Client, name: str, args: dict | None = None) -> dict:
    r = await client.call_tool(name, args or {})
    text = r.content[0].text if r.content else ""
    if r.is_error:  # "Error executing tool <name>: {"error": {...}}"
        return {"_error": json.loads(text[text.index("{"):])["error"] if "{" in text else text}
    return r.structured_content if r.structured_content is not None else json.loads(text)


async def until_done(client: Client, scan: dict) -> dict:
    for _ in range(60):
        if scan["done"]:
            return scan
        scan = await call(client, "get_scan", {"scan_id": scan["scan"]["scan_id"], "wait_seconds": 1})
    raise AssertionError("scan did not finish")


async def test_tool_surface_matches_engine_api(engine):
    async with Client(build_server(cfg(engine))) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
        assert set(tools) == TOOLS
        # the host cannot pass a server URL, token or filesystem root through any tool
        for t in tools.values():
            props = set(t.input_schema.get("properties", {}))
            assert not props & {"base_url", "url", "token", "root", "server"}, t.name
        assert tools["get_findings"].annotations.read_only_hint is True
        assert "never" in (c.instructions or "").lower() or "Never" in (c.instructions or "")


async def test_change_scan_explain_fix_recheck(engine):
    (engine.root / "billing.py").write_text(RISKY)  # untracked change in the Git workspace
    async with Client(build_server(cfg(engine))) as c:
        ws = await call(c, "list_workspaces")
        assert ws["default_workspace_id"] == "ws_demo" and [w["id"] for w in ws["items"]] == ["ws_demo"]

        scan = await until_done(c, await call(c, "scan_changes", {"wait_seconds": 10}))
        assert scan["scan"]["state"] in ("completed", "partial")
        assert "not mean there are no risks" in scan["state_meaning"] or scan["scan"]["state"] == "partial"
        sid = scan["scan"]["scan_id"]

        found = await call(c, "get_findings", {"scan_id": sid})
        assert found["public_exposure"] == []
        assert "not requested" in found["coverage_notes"]["public_exposure"]  # never rendered as "no match"
        risk = next(f for f in found["local_risk"] if f["path"] == "billing.py")
        assert risk["rule_id"] == "py_sensitive_logging"

        ex = await call(c, "explain_finding", {"finding_id": risk["finding_id"], "include_evidence": True})
        latest = ex["finding"]["latest"]
        assert latest["evidence"][0]["location"]["line_start"] == 7
        assert latest["risk_review"] == "unavailable"  # no model configured: rule finding is kept, not erased
        assert ex["evidence"][0]["kind"] == "local_span"

        (engine.root / "billing.py").write_text(FIXED)  # the user's editor applies the fix, not Tracefold
        rc = await call(c, "recheck_fix", {"finding_id": risk["finding_id"], "wait_seconds": 15})
        assert rc["outcome"] == "not_detected_in_checked_version"
        assert rc["finding_status"] == "not_detected_in_checked_version"
        assert "fixed" in rc["outcome_meaning"]  # explicitly says this is not a 'fixed' verdict

        # the same finding, same status, is visible to the upload app through the engine (shared findings store)
    async with Client(build_server(cfg(engine, "app"))) as app:
        same = await call(app, "explain_finding", {"finding_id": risk["finding_id"]})
        assert same["finding"]["status"] == "not_detected_in_checked_version"
        assert same["finding"]["rechecks"][-1]["recheck_id"] == rc["recheck_id"]
    (engine.root / "billing.py").unlink()


async def test_public_match_through_manifest(engine):
    src = Path(__file__).resolve().parents[3] / "server" / "fixtures" / "private" / "roadmap.md"
    (engine.root / "roadmap.md").write_text(src.read_text())
    async with Client(build_server(cfg(engine))) as c:
        scan = await until_done(c, await call(c, "scan_changes", {
            "mode": "files", "paths": ["roadmap.md"], "check_public_sources": "sources_demo", "model_review": False}))
        found = await call(c, "get_findings", {"scan_id": scan["scan"]["scan_id"]})
        assert [f["path"] for f in found["public_exposure"]] == ["roadmap.md"]
        ex = await call(c, "explain_finding", {"finding_id": found["public_exposure"][0]["finding_id"],
                                               "include_evidence": True})
        assert ex["evidence"][0]["public"]["url"] == "https://forum.example/t/123"
    (engine.root / "roadmap.md").unlink()


async def test_minimal_disclosure_and_missing_capability(engine):
    (engine.root / "notes.py").write_text(RISKY)
    async with Client(build_server(cfg(engine, "cloud"))) as c:
        scan = await until_done(c, await call(c, "scan_changes", {"mode": "files", "paths": ["notes.py"],
                                                                   "model_review": False}))
        found = await call(c, "get_findings", {"scan_id": scan["scan"]["scan_id"]})
        risk = found["local_risk"][0]
        assert risk["path"] is None  # paths withheld from a cloud-backed host
        ex = await call(c, "explain_finding", {"finding_id": risk["finding_id"], "include_evidence": True})
        assert ex["finding"]["latest"]["claim"] is None
        assert ex["evidence"][0]["error"]["code"] == "forbidden"  # no read_evidence for this client
        # recheck without a known path: the host may name the file it edited
        (engine.root / "notes.py").write_text(FIXED)
        rc = await call(c, "recheck_fix", {"finding_id": risk["finding_id"], "paths": ["notes.py"], "wait_seconds": 15})
        assert rc["outcome"] == "not_detected_in_checked_version"
    (engine.root / "notes.py").unlink()


async def test_engine_error_codes_are_preserved(engine):
    async with Client(build_server(cfg(engine))) as c:
        r = await call(c, "get_scan", {"scan_id": "scan_doesnotexist"})
        assert r["_error"]["code"] == "not_found" and r["_error"]["http_status"] == 404
        r = await call(c, "get_scan", {"scan_id": "../../capabilities"})
        assert r["_error"]["code"] == "invalid_request"
        r = await call(c, "scan_changes", {"workspace_id": "ws_other"})  # not granted → indistinguishable 404
        assert r["_error"]["http_status"] == 404
        r = await call(c, "scan_changes", {"mode": "files", "paths": ["../outside.txt"]})
        assert "_error" in r or all(f["status"] == "rejected" for f in r["capture"]["files"])
        r = await call(c, "scan_changes", {"baseline": "not-a-ref"})
        assert r["_error"]["code"] == "invalid_baseline"
    async with Client(build_server(AdapterConfig(engine.base, "tf_wrong", "ws_demo"))) as c:
        r = await call(c, "list_workspaces")
        assert r["_error"]["http_status"] == 401
        assert "tf_wrong" not in json.dumps(r)
    async with Client(build_server(AdapterConfig("http://127.0.0.1:9", engine.tokens["mcp"], "ws_demo"))) as c:
        r = await call(c, "get_capabilities")
        assert r["_error"]["code"] == "engine_unreachable" and r["_error"]["retryable"] is True


async def test_stdio_server_end_to_end(engine, tmp_path):
    path = write_config(tmp_path / "mcp.json", engine.base, engine.tokens["mcp"] + "\n", "ws_demo")
    params = StdioServerParameters(command=sys.executable, args=["-m", "tracefold_mcp.cli", "--config", str(path)],
                                   env={"PATH": os.environ.get("PATH", "")})
    async with Client(params) as c:
        assert {t.name for t in (await c.list_tools()).tools} == TOOLS
        caps = await call(c, "get_capabilities")
        assert "local_risk" in caps["checks"]


# ---------- config safety ----------

def test_config_requires_loopback_and_private_file(tmp_path):
    for bad in ("https://127.0.0.1:8787", "http://example.com:8787", "http://user:pw@127.0.0.1:1",
                "http://127.0.0.1:8787/other", "http://10.0.0.5"):
        with pytest.raises(ConfigError):
            validate_base_url(bad)
    assert validate_base_url("http://127.0.0.1:8787/v1/") == "http://127.0.0.1:8787"

    p = write_config(tmp_path / "c" / "mcp.json", "http://localhost:8787", "tf_abc\n", "ws_demo")
    assert oct(p.stat().st_mode & 0o777) == "0o600"
    c = load_config(p)
    assert c.token == "tf_abc" and "tf_abc" not in repr(c)
    p.chmod(0o644)
    with pytest.raises(ConfigError, match="readable by other users"):
        load_config(p)
    p.chmod(0o600)
    p.write_text(json.dumps({"base_url": "http://evil.example", "token": "tf_x", "workspace_id": "w"}))
    with pytest.raises(ConfigError):
        load_config(p)
    with pytest.raises(ConfigError):
        write_config(tmp_path / "x.json", "http://127.0.0.1:1", "not-a-token", "ws")
