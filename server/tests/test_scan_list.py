"""GET /scans: every client's scans in one list, so assistant (MCP) activity is visible in the web app."""
from __future__ import annotations

from .conftest import fx


def test_lists_scans_from_app_and_assistant_newest_first(env):
    inp = env.upload({"risky_app.py": fx("risky_app.py")})
    a = env.scan(inp["input_id"], who="app", model_review=False)
    inp2 = env.upload({"risky_app.py": fx("risky_app.py")}, who="mcp")
    b = env.scan(inp2["input_id"], who="mcp", model_review=False)

    r = env.client.get("/v1/workspaces/ws_a/scans", headers=env.h("app"))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [s["scan_id"] for s in items[:2]] == [b["scan_id"], a["scan_id"]]
    assert items[0]["started_from"] == "assistant" and items[1]["started_from"] == "app"
    assert items[0]["initiated_by"].startswith("mcp")
    # single-scan reads carry the same attribution
    assert env.get_scan(b["scan_id"])["started_from"] == "assistant"


def test_pagination_and_isolation(env):
    inp = env.upload({"a.txt": b"nothing here"})
    for _ in range(3):
        env.scan(inp["input_id"])
    page = env.client.get("/v1/workspaces/ws_a/scans?limit=2", headers=env.h("app")).json()
    assert len(page["items"]) == 2 and page["next_cursor"]
    rest = env.client.get(f"/v1/workspaces/ws_a/scans?limit=2&cursor={page['next_cursor']}", headers=env.h("app")).json()
    assert len(rest["items"]) == 1
    assert env.client.get("/v1/workspaces/ws_a/scans", headers=env.h("other")).status_code == 404
