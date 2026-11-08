"""`tracefold quickstart`: one-step local setup that a coding agent can run unattended."""
from __future__ import annotations

import json
import stat

import pytest

from tracefold.cli import main
from tracefold.config import Settings
from tracefold.engine import Engine
from tracefold.policy.auth import authenticate


def _run(tmp_path, capsys, *extra):
    data, root = tmp_path / "data", tmp_path / "project"
    root.mkdir(exist_ok=True)
    args = ["--data", str(data), "quickstart", "--root", str(root), "--frontend-env", str(tmp_path / "fe" / ".env.local"),
            "--mcp-config", str(tmp_path / "cfg" / "mcp.json"), *extra]
    assert main(args) in (0, None)
    return capsys.readouterr().out


def _engine(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    s.start_runner = False
    return Engine(s)


def test_quickstart_writes_private_configs_and_never_prints_tokens(tmp_path, capsys):
    out = _run(tmp_path, capsys, "--public-url", "https://forum.example/t/1", "--json")
    r = json.loads(out)
    assert r["workspace"] == "ws_project" and r["workspace_created"] is True
    assert r["public_sources"] == {"manifest_id": "public", "version": 1, "count": 1}

    env = (tmp_path / "fe" / ".env.local").read_text()
    mcp = json.loads((tmp_path / "cfg" / "mcp.json").read_text())
    app_token = next(l.split("=", 1)[1] for l in env.splitlines() if l.startswith("TRACEFOLD_APP_TOKEN="))
    assert "TRACEFOLD_ENGINE_URL=http://127.0.0.1:8787" in env
    assert mcp["workspace_id"] == "ws_project" and mcp["base_url"] == "http://127.0.0.1:8787"
    for p in (tmp_path / "fe" / ".env.local", tmp_path / "cfg" / "mcp.json"):
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert app_token not in out and mcp["token"] not in out

    e = _engine(tmp_path)
    app = authenticate(e.repo, f"Bearer {app_token}").grants["ws_project"]
    assistant = authenticate(e.repo, f"Bearer {mcp['token']}").grants["ws_project"]
    assert "approve" in {c.value for c in app.capabilities}
    assert "approve" not in {c.value for c in assistant.capabilities}  # assistants can't approve takedowns or key changes


def test_rerun_reuses_workspace_and_rotates_tokens(tmp_path, capsys):
    _run(tmp_path, capsys)
    old = json.loads((tmp_path / "cfg" / "mcp.json").read_text())["token"]
    out = _run(tmp_path, capsys)
    assert "reused" in out and "are not shown here" in out
    new = json.loads((tmp_path / "cfg" / "mcp.json").read_text())["token"]
    assert new != old
    e = _engine(tmp_path)
    from tracefold.errors import ApiError
    with pytest.raises(ApiError):
        authenticate(e.repo, f"Bearer {old}")
    authenticate(e.repo, f"Bearer {new}")


def test_refuses_to_repoint_an_existing_workspace(tmp_path, capsys):
    _run(tmp_path, capsys)
    other = tmp_path / "elsewhere" / "project"
    other.mkdir(parents=True)
    with pytest.raises(SystemExit, match="already points at"):
        main(["--data", str(tmp_path / "data"), "quickstart", "--root", str(other),
              "--frontend-env", str(tmp_path / "fe2"), "--mcp-config", str(tmp_path / "m2.json")])


def test_company_sets_signer_identity_and_plan_once(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-test-key-123456")
    extra = ("--company", "Northwind Relay, Inc.", "--domain", "northwind.example.com", "--reply-to", "legal@northwind.example.com", "--json")
    first = json.loads(_run(tmp_path, capsys, *extra))["company"]
    again = json.loads(_run(tmp_path, capsys, *extra))["company"]
    assert first["identity"] == again["identity"] and first["plan"]["query_plan_id"] == again["plan"]["query_plan_id"]
    assert first["plan"]["providers"] == ["exa"] and first["plan"]["pack"] == "broad_triage"
    e = _engine(tmp_path)
    assert e.repo.get_remediation_profile("ws_project")["company_name"] == "Northwind Relay, Inc."
    assert len(e.repo.list_profiles("ws_project")) == 1 and len(e.repo.list_query_plans("ws_project", None, 100)) == 1


def test_company_without_search_keys_explains_missing_plan(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    out = json.loads(_run(tmp_path, capsys, "--company", "Northwind Relay", "--json"))["company"]
    assert out["plan"] is None and "EXA_API_KEY" in out["plan_note"]
