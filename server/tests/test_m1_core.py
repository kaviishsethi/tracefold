"""Milestone 1: contracts, SQLite, workspace grants, queue and capture registry."""
from __future__ import annotations

import os
from datetime import timedelta

import pytest

from tracefold.engine import Engine
from tracefold.jobs.runner import RunnerConflict
from tracefold.util import now

from .conftest import make_settings


def test_health_and_auth_boundaries(env):
    c = env.client
    assert c.get("/v1/health").json() == {"status": "ok"}
    r = c.get("/v1/workspaces")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated" and r.json()["request_id"]
    assert c.get("/v1/workspaces", headers={"Authorization": "Bearer tf_wrong"}).status_code == 401
    assert c.get("/v1/workspaces", headers=env.h(Host="evil.example")).json()["error"]["code"] == "invalid_host"
    r = c.get("/v1/workspaces", headers=env.h(Origin="https://evil.example"))
    assert r.status_code == 403 and r.json()["error"]["code"] == "invalid_origin"
    assert c.get("/v1/workspaces", headers=env.h(Origin="http://localhost:3000")).status_code == 200
    # ledger requires auth like every other read
    assert c.get("/v1/workspaces/ws_a/scans/scan_x/ledger").status_code == 401


def test_workspaces_lists_only_granted(env):
    items = env.client.get("/v1/workspaces", headers=env.h("app")).json()["items"]
    assert [w["id"] for w in items] == ["ws_a"]
    items = env.client.get("/v1/workspaces", headers=env.h("other")).json()["items"]
    assert [w["id"] for w in items] == ["ws_b"]
    caps = env.client.get("/v1/capabilities", headers=env.h("app")).json()
    assert "ws_a" in caps["client_capabilities"] and "ws_b" not in caps["client_capabilities"]


def test_two_clients_share_one_job(env):
    inp = env.upload({"notes.md": b"# Plan\nnothing sensitive here\n"}, who="app")
    assert inp["files"][0]["status"] == "captured" and inp["revision"] >= 1
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h("app"),
                        json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    assert r.status_code == 202
    sid = r.json()["scan_id"]
    assert r.json()["status_url"] == f"/v1/workspaces/ws_a/scans/{sid}"
    assert env.get_scan(sid, "mcp")["state"] == "queued"
    env.engine.runner.run_pending()
    a, b = env.get_scan(sid, "app"), env.get_scan(sid, "mcp")
    assert a == b
    assert a["state"] not in ("queued", "running")
    assert [s["name"] for s in a["stages"]][0] == "parse"
    assert any(c["scope"] == "check" and c["id"] == "public_match" and c["status"] == "not_requested" for c in a["coverage"])


def test_cross_workspace_access_denied(env):
    inp = env.upload({"a.txt": b"hello world"}, who="app")
    s = env.scan(inp["input_id"], run=False)
    sid = s["scan_id"]
    # other workspace's client: non-enumerating 404 everywhere
    for path in (f"/v1/workspaces/ws_a/scans/{sid}", "/v1/workspaces/ws_a/findings", f"/v1/workspaces/ws_a/scans/{sid}/ledger"):
        r = env.client.get(path, headers=env.h("other"))
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    # nested ID from ws_a must not be usable via ws_b
    assert env.client.get(f"/v1/workspaces/ws_b/scans/{sid}", headers=env.h("other")).status_code == 404
    r = env.client.post("/v1/workspaces/ws_b/scans", headers=env.h("other"),
                        json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    assert r.status_code == 404
    # upload to a workspace without a grant
    r = env.client.post("/v1/workspaces/ws_b/uploads", headers=env.h("app"), files=[("file", ("x.txt", b"x"))])
    assert r.status_code == 404


def test_capability_enforced(env):
    inp = env.upload({"a.txt": b"hello"}, who="app")
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h("reader"),
                        json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


def test_contract_validation(env):
    inp = env.upload({"a.txt": b"hello"})
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={"input_id": inp["input_id"], "checks": ["nope"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(),
                        json={"input_id": inp["input_id"], "checks": ["local_risk"], "shell": "rm -rf /"})
    assert r.status_code == 422  # unknown fields rejected
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={"input_id": inp["input_id"], "checks": ["public_match"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "public_sources_required"


def test_idempotency(env):
    inp = env.upload({"a.txt": b"hello"})
    body = {"input_id": inp["input_id"], "checks": ["local_risk"]}
    r1 = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(**{"Idempotency-Key": "k1"}), json=body)
    r2 = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(**{"Idempotency-Key": "k1"}), json=body)
    assert r1.json()["scan_id"] == r2.json()["scan_id"]
    r3 = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(**{"Idempotency-Key": "k1"}),
                         json={**body, "model_review": False})
    assert r3.status_code == 409 and r3.json()["error"]["code"] == "idempotency_conflict"
    # key is scoped per client: the mcp client may reuse the same key independently
    r4 = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h("mcp", **{"Idempotency-Key": "k1"}), json=body)
    assert r4.status_code == 202 and r4.json()["scan_id"] != r1.json()["scan_id"]


def test_cancel_queued_and_running(env):
    inp = env.upload({"a.txt": b"hello"})
    s = env.scan(inp["input_id"], run=False)
    r = env.client.post(f"/v1/workspaces/ws_a/scans/{s['scan_id']}/cancel", headers=env.h("mcp"))
    assert r.status_code == 202 and r.json()["state"] == "cancelled"

    s2 = env.scan(inp["input_id"], run=False)

    def cancel_during(ctx, name):
        if name == "parse":
            env.engine.repo.request_cancel(ctx.scan_id)
    env.engine.hooks.before_stage = cancel_during
    env.engine.runner.run_pending()
    out = env.get_scan(s2["scan_id"])
    assert out["state"] == "cancelled"
    assert any(e["code"] == "cancelled" for e in out["errors"])
    assert next(st for st in out["stages"] if st["name"] == "parse")["status"] == "cancelled"


def test_queue_full(env):
    inp = env.upload({"a.txt": b"hello"})
    for _ in range(env.engine.settings.limits.max_queued_scans):
        env.scan(inp["input_id"], run=False)
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    assert r.status_code == 429 and r.json()["error"]["retryable"] is True


def test_input_expiry(env):
    inp = env.upload({"a.txt": b"hello"})
    cap = env.engine.registry.get(inp["input_id"])
    cap.expires_at = now() - timedelta(seconds=1)
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    assert r.status_code == 410 and r.json()["error"]["code"] == "input_expired"


def test_restart_interrupts_running_and_expires_queued(tmp_path, make_env):
    env = make_env()
    inp = env.upload({"a.txt": b"hello"})
    queued = env.scan(inp["input_id"], run=False)["scan_id"]
    running = env.scan(inp["input_id"], run=False)["scan_id"]
    env.engine.repo.update_scan(running, state="running")
    env.client.__exit__(None, None, None)  # shutdown releases the runner lock
    eng2 = Engine(make_settings(tmp_path))  # fresh process: registry is empty
    eng2.startup()
    try:
        assert eng2.repo.get_scan(running)["state"] == "interrupted"
        q = eng2.repo.get_scan(queued)
        assert q["state"] == "failed" and q["errors"][0]["code"] == "input_expired"
    finally:
        eng2.shutdown()


def test_single_runner_enforced(tmp_path, make_env):
    env = make_env()
    env.engine.runner.run_pending()  # acquires the lock
    eng2 = Engine(make_settings(tmp_path))
    with pytest.raises(RunnerConflict):
        eng2.runner.acquire()


def test_capture_registry_capacity(env):
    a = env.upload({"a.txt": b"one"})
    b = env.upload({"b.txt": b"two"})
    # both captures are unconsumed: a third is rejected rather than spilling to disk
    r = env.client.post("/v1/workspaces/ws_a/uploads", headers=env.h(), files=[("file", ("c.txt", b"three"))])
    assert r.status_code == 429 and r.json()["error"]["code"] == "capture_capacity"
    env.scan(a["input_id"])  # consumed by a finished scan -> evictable
    env.upload({"c.txt": b"three"})
    assert env.engine.registry.get(a["input_id"]) is None
    assert env.engine.registry.get(b["input_id"]) is not None


def test_upload_limits_and_rejections(env):
    big = b"x" * (env.engine.settings.limits.max_request_bytes + 10)
    r = env.client.post("/v1/workspaces/ws_a/uploads", headers=env.h(), files=[("file", ("big.txt", big))])
    assert r.status_code == 413
    inp = env.upload({"pic.png": b"\x89PNG", "bad.txt": b"\xff\xfe\x00bad", "../../etc/passwd.md": b"ok"})
    by = {f["path"]: f for f in inp["files"]}
    assert by["pic.png"]["reason"] == "unsupported_type"
    assert by["bad.txt"]["status"] == "rejected"
    assert "passwd.md" in by and by["passwd.md"]["status"] == "captured"  # filename never used as a path


def test_workspace_capture_safety(env):
    root = env.root
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text("print('hi')\n")
    (root / ".env").write_text("SECRET=1\n")
    os.symlink("/etc/hosts", root / "link.txt")
    fifo = root / "pipe.txt"
    os.mkfifo(fifo)
    r = env.client.post("/v1/workspaces/ws_a/captures", headers=env.h(),
                        json={"mode": "files", "paths": ["src/app.py", "../outside.txt", ".env", "link.txt", "pipe.txt", "missing.py"]})
    assert r.status_code == 201, r.text
    by = {f["path"]: f for f in r.json()["files"]}
    assert by["src/app.py"]["status"] == "captured"
    assert by["../outside.txt"]["reason"] == "path_traversal"
    assert by[".env"]["reason"] == "excluded_path"
    assert by["link.txt"]["reason"] == "symlink_refused"
    assert by["pipe.txt"]["reason"] == "special_file"
    assert by["missing.py"]["reason"] == "not_found"
    # upload-only workspace cannot capture directories
    r = env.client.post("/v1/workspaces/ws_b/captures", headers=env.h("other"), json={"mode": "files", "paths": ["a"]})
    assert r.status_code == 422


def test_concurrent_change_during_capture(env):
    (env.root / "a.py").write_text("x = 1\n")

    def mutate():
        (env.root / "a.py").write_text("x = 2  # changed during capture\n")
    env.engine.hooks.after_read = mutate
    r = env.client.post("/v1/workspaces/ws_a/captures", headers=env.h(), json={"mode": "files", "paths": ["a.py"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "capture_conflict"


def test_minimal_disclosure_hides_paths(env):
    (env.root / "a.py").write_text("x = 1\n")
    r = env.client.post("/v1/workspaces/ws_a/captures", headers=env.h("cloud"), json={"mode": "files", "paths": ["a.py"]})
    assert r.status_code == 201 and r.json()["files"][0]["path"] is None


def test_background_runner_thread(tmp_path, make_env):
    env = make_env(start_runner=True)
    inp = env.upload({"a.txt": b"hello"})
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={"input_id": inp["input_id"], "checks": ["local_risk"]})
    s = env.wait(r.json()["scan_id"])
    assert s["state"] in ("completed", "partial", "failed") and s["finished_at"]
