"""Documented fixture flow that exercises every engine endpoint over HTTP.

It plays both clients against one engine: the upload app (existing material + public sources) and the
MCP-style assistant (workspace change → findings → fix → recheck). Usage against a running server:

    uv run python examples/demo_flow.py --base http://127.0.0.1:8787 --workspace ws_demo \
        --app-token "$APP_TOKEN" --mcp-token "$MCP_TOKEN" --workspace-root /path/to/registered/root

Everything it writes is synthetic fixture content.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "private"

RISKY = '''import logging

logger = logging.getLogger(__name__)


def charge(card_number: str, amount: int) -> None:
    logger.info("charging card %s for %d", card_number, amount)
'''
FIXED = RISKY.replace('logger.info("charging card %s for %d", card_number, amount)',
                      'logger.info("charging card ending %s for %d", mask(card_number), amount)')


def wait(c: httpx.Client, url: str, h: dict, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        s = c.get(url, headers=h).raise_for_status().json()
        if s["state"] not in ("queued", "running"):
            return s
        time.sleep(0.2)
    raise TimeoutError(url)


def run(c: httpx.Client, ws: str, app_token: str, mcp_token: str, root: Path, manifest: str = "sources_demo") -> dict:
    app = {"Authorization": f"Bearer {app_token}"}
    mcp = {"Authorization": f"Bearer {mcp_token}"}
    out: dict = {}
    base = f"/v1/workspaces/{ws}"

    assert c.get("/v1/health").json() == {"status": "ok"}
    out["capabilities"] = c.get("/v1/capabilities", headers=app).raise_for_status().json()
    out["workspaces"] = [w["id"] for w in c.get("/v1/workspaces", headers=mcp).raise_for_status().json()["items"]]

    # --- Upload app: existing material against approved public sources -------------------------------
    files = [("file", ("roadmap.md", (FIXTURES / "roadmap.md").read_bytes(), "text/markdown")),
             ("file", ("same_topic.md", (FIXTURES / "same_topic.md").read_bytes(), "text/markdown"))]
    up = c.post(f"{base}/uploads", headers=app, files=files).raise_for_status().json()
    acc = c.post(f"{base}/scans", headers={**app, "Idempotency-Key": "demo-upload-1"}, json={
        "input_id": up["input_id"], "checks": ["public_match", "local_risk"],
        "public_sources": {"manifest_id": manifest, "mode": "refresh"}}).raise_for_status().json()
    s1 = wait(c, acc["status_url"], app)
    out["upload_scan"] = {"state": s1["state"], "freshness": s1["public_freshness"]}
    f1 = c.get(f"{base}/findings", params={"scan_id": s1["scan_id"]}, headers=app).raise_for_status().json()["items"]
    public = next(f for f in f1 if f["kind"] == "public_exposure")
    ev = c.get(f"{base}/evidence/{public['latest']['evidence'][0]['evidence_id']}", headers=app).raise_for_status().json()
    out["public_finding"] = {"id": public["finding_id"], "path": public["path"], "url": ev["public"]["url"],
                             "lines": [ev["location"]["line_start"], ev["location"]["line_end"]],
                             "matched_tokens": ev["matched_tokens"]}
    out["upload_ledger"] = c.get(f"{base}/scans/{s1['scan_id']}/ledger", headers=app).raise_for_status().json()["items"]

    # --- Assistant: unpublished change → finding → fix → recheck --------------------------------------
    (root / "billing.py").write_text(RISKY)
    cap = c.post(f"{base}/captures", headers=mcp, json={"mode": "files", "paths": ["billing.py"]}).raise_for_status().json()
    acc2 = c.post(f"{base}/scans", headers=mcp, json={"input_id": cap["input_id"], "checks": ["local_risk"]}).raise_for_status().json()
    s2 = wait(c, acc2["status_url"], mcp)
    local = c.get(f"{base}/findings", params={"scan_id": s2["scan_id"]}, headers=mcp).raise_for_status().json()["items"][0]
    detail = c.get(f"{base}/findings/{local['finding_id']}", headers=mcp).raise_for_status().json()
    out["local_finding"] = {"id": local["finding_id"], "rule": local["rule_id"],
                            "line": detail["latest"]["evidence"][0]["location"]["line_start"],
                            "risk_review": detail["latest"]["risk_review"], "fix": detail["latest"]["suggested_fix"]}

    (root / "billing.py").write_text(FIXED)  # applied through the user's editor workflow, not by Tracefold
    cap2 = c.post(f"{base}/captures", headers=mcp, json={"mode": "files", "paths": ["billing.py"]}).raise_for_status().json()
    rc = c.post(f"{base}/findings/{local['finding_id']}/rechecks", headers=mcp, json={"input_id": cap2["input_id"]}).raise_for_status().json()
    wait(c, rc["status_url"], mcp)
    after = c.get(f"{base}/findings/{local['finding_id']}", headers=app).raise_for_status().json()  # seen from the app
    out["recheck"] = {"outcome": after["rechecks"][-1]["outcome"], "status": after["status"]}
    out["public_still_open"] = c.get(f"{base}/findings/{public['finding_id']}", headers=app).json()["status"] == "open"

    # --- Human review and cancellation --------------------------------------------------------------
    rv = c.patch(f"{base}/findings/{public['finding_id']}/review", headers=app,
                 json={"state": "acknowledged", "expected_version": public["version"]}).raise_for_status().json()
    out["review"] = rv["human_review"]
    acc3 = c.post(f"{base}/scans", headers=app, json={"input_id": up["input_id"], "checks": ["local_risk"]})
    if acc3.status_code == 202:
        cs = c.post(f"{base}/scans/{acc3.json()['scan_id']}/cancel", headers=app).raise_for_status().json()
        out["cancel"] = cs["state"]
    else:
        out["cancel"] = acc3.json()["error"]["code"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8787")
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--app-token", required=True)
    ap.add_argument("--mcp-token", required=True)
    ap.add_argument("--workspace-root", required=True)
    ap.add_argument("--manifest", default="sources_demo")
    a = ap.parse_args()
    with httpx.Client(base_url=a.base, timeout=30) as c:
        print(json.dumps(run(c, a.workspace, a.app_token, a.mcp_token, Path(a.workspace_root), a.manifest), indent=2))


if __name__ == "__main__":
    main()
