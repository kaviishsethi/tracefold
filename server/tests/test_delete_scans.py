"""Deleting scans: one or all, removing only what those scans produced."""
from .conftest import fx
from .test_m8_remediation import WS, actions, aws_scan, public_scan


def delete(env, path="", who="app"):
    return env.client.delete(f"{WS}/scans{path}", headers=env.h(who))


def test_delete_one_scan_keeps_findings_seen_by_another(env):
    first = aws_scan(env)
    second = aws_scan(env)                      # same file again: same findings, second observation
    keys = actions(env)
    assert keys
    r = delete(env, f"/{first['scan_id']}")
    assert r.status_code == 200 and r.json() == {"scans": 1, "findings": 0}
    assert env.findings() and actions(env) == keys
    r = delete(env, f"/{second['scan_id']}")
    assert r.json()["scans"] == 1 and r.json()["findings"] > 0
    assert env.findings() == [] and actions(env) == []
    assert env.client.get(f"{WS}/scans/{second['scan_id']}", headers=env.h()).status_code == 404


def test_clear_all_removes_every_finished_scan(env):
    public_scan(env)
    aws_scan(env)
    r = delete(env)
    assert r.status_code == 200 and r.json()["scans"] == 2
    assert env.client.get(f"{WS}/scans", headers=env.h()).json()["items"] == []
    assert env.findings() == [] and actions(env) == []
    assert env.engine.repo.all_ledger() == [] or all(e.get("scan_id") is None for e in env.engine.repo.all_ledger())


def test_assistants_cannot_delete_and_running_scans_are_kept(env):
    s = aws_scan(env)
    assert delete(env, f"/{s['scan_id']}", who="cloud").status_code == 403
    inp = env.upload({"risky_app.py": fx("risky_app.py")})
    r = env.client.post(f"{WS}/scans", headers=env.h(), json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    queued = r.json()["scan_id"]
    assert delete(env, f"/{queued}").json()["error"]["code"] == "scan_running"
    delete(env)
    assert [x["scan_id"] for x in env.client.get(f"{WS}/scans", headers=env.h()).json()["items"]] == [queued]
