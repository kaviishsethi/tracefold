"""Milestone 7: integration handoff — OpenAPI contract, documented flow over real HTTP, CLI provisioning."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from tracefold.api.app import create_app

from .conftest import FIXTURES, fx

SERVER = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER / "examples"))
import demo_flow  # noqa: E402

ROUTES = {
    ("get", "/v1/health"), ("get", "/v1/capabilities"), ("get", "/v1/workspaces"),
    ("post", "/v1/workspaces/{ws_id}/uploads"), ("post", "/v1/workspaces/{ws_id}/captures"),
    ("post", "/v1/workspaces/{ws_id}/scans"), ("get", "/v1/workspaces/{ws_id}/scans/{scan_id}"),
    ("post", "/v1/workspaces/{ws_id}/scans/{scan_id}/cancel"), ("get", "/v1/workspaces/{ws_id}/findings"),
    ("get", "/v1/workspaces/{ws_id}/findings/{finding_id}"), ("get", "/v1/workspaces/{ws_id}/evidence/{evidence_id}"),
    ("post", "/v1/workspaces/{ws_id}/findings/{finding_id}/rechecks"),
    ("patch", "/v1/workspaces/{ws_id}/findings/{finding_id}/review"),
    ("get", "/v1/workspaces/{ws_id}/scans/{scan_id}/ledger"),
}


def check_flow(out: dict) -> None:
    assert out["upload_scan"] == {"state": "completed", "freshness": "fresh retrieval"}
    assert out["public_finding"]["path"] == "roadmap.md" and out["public_finding"]["lines"] == [5, 7]
    assert out["public_finding"]["url"] == "https://forum.example/t/123"
    assert out["local_finding"]["rule"] == "py_sensitive_logging" and out["local_finding"]["line"] == 7
    assert out["recheck"] == {"outcome": "not_detected_in_checked_version", "status": "not_detected_in_checked_version"}
    assert out["public_still_open"] is True
    assert out["review"] == "acknowledged"
    assert out["cancel"] in ("cancelled", "completed")


def test_openapi_covers_contract_and_is_current(env):
    spec = create_app(env.engine).openapi()
    have = {(m, p) for p, ops in spec["paths"].items() for m in ops}
    assert ROUTES <= have
    for name in ("ScanRequest", "ScanOut", "FindingOut", "EvidenceOut", "ErrorEnvelope", "RecheckRequest", "LedgerPage"):
        assert name in spec["components"]["schemas"]
    committed = json.loads((SERVER / "openapi.json").read_text())
    assert committed["paths"].keys() == spec["paths"].keys()
    assert committed["components"]["schemas"].keys() == spec["components"]["schemas"].keys()


def test_documented_flow_in_process(make_env):
    env = make_env(start_runner=True)
    out = demo_flow.run(env.client, "ws_a", env.tokens["app"], env.tokens["mcp"], env.root)
    check_flow(out)
    assert out["workspaces"] == ["ws_a"]
    # fixture provider makes no network requests; only the (failed) loopback model probe is recorded
    assert all(e["destination_category"] == "local_model" and e["destination_host"] == "127.0.0.1" for e in out["upload_ledger"])


def test_retention_keeps_scans_backing_findings(make_env):
    env = make_env()
    env.engine.settings.limits.retained_scans = 1
    inp = env.upload({"a.txt": b"nothing here"})
    ids = [env.scan(inp["input_id"])["scan_id"] for _ in range(3)]
    remaining = [i for i in ids if env.engine.repo.get_scan(i)]
    assert remaining == [ids[-1]]
    inp2 = env.upload({"risky_app.py": fx("risky_app.py")})
    s = env.scan(inp2["input_id"], model_review=False)
    env.scan(inp["input_id"])
    assert env.engine.repo.get_scan(s["scan_id"]) is not None  # backs findings, never pruned


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cli_provisioning_and_real_server(tmp_path):
    data, root = tmp_path / "data", tmp_path / "ws"
    root.mkdir()
    env = {**os.environ, "TRACEFOLD_DATA": str(data), "TRACEFOLD_FIXTURES": str(FIXTURES),
           "TRACEFOLD_OLLAMA_URL": "http://127.0.0.1:9"}
    cli = [sys.executable, "-m", "tracefold.cli"]

    def run(*args):
        return subprocess.run([*cli, *args], env=env, capture_output=True, text=True, check=True, cwd=SERVER).stdout.strip()
    run("init")
    run("add-workspace", "ws_demo", "--name", "Demo", "--root", str(root))
    app_token = run("add-client", "upload-app", "--workspace", "ws_demo")
    mcp_token = run("add-client", "mcp-adapter", "--workspace", "ws_demo",
                    "--caps", "submit,read,read_evidence,recheck,cancel")
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture",
                                     "fixture_path": "public/forum_post.html"}]))
    run("add-manifest", "ws_demo", "sources_demo", str(manifest))
    assert app_token.startswith("tf_") and app_token != mcp_token
    assert app_token not in (data / "tracefold.db").read_bytes().decode("latin-1")  # only hashes are stored

    port = _free_port()
    proc = subprocess.Popen([*cli, "serve", "--port", str(port)], env=env, cwd=SERVER,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                if httpx.get(base + "/v1/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        with httpx.Client(base_url=base, timeout=30) as c:
            out = demo_flow.run(c, "ws_demo", app_token, mcp_token, root)
            check_flow(out)
            # the MCP client was provisioned without 'review': review is denied for it
            r = c.patch(f"/v1/workspaces/ws_demo/findings/{out['public_finding']['id']}/review",
                        headers={"Authorization": f"Bearer {mcp_token}"}, json={"state": "acknowledged", "expected_version": 2})
            assert r.status_code == 403
            # Host header outside the loopback allowlist is rejected (DNS-rebinding guard)
            assert c.get("/v1/health", headers={"Host": "attacker.example"}).status_code == 400
    finally:
        proc.terminate()
        proc.wait(timeout=10)
