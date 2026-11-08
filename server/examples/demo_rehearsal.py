"""Rehearse docs/DEMO_PLAN.md against a running engine, step by step.

    # 1. one-time setup (workspace, git repo for the "unpublished change", tokens, source lists)
    uv run python examples/demo_rehearsal.py setup --data demo-data --repo demo-repo
    # 2. start the engine with the same data dir (provider keys from server/.env)
    TRACEFOLD_DATA=demo-data uv run tracefold serve --port 8787
    # 3. rehearse (exits non-zero if any beat does not produce what the plan expects)
    uv run python examples/demo_rehearsal.py run --data demo-data --repo demo-repo

Uses the verified Nothing memo pair (docs/demo-pairs/nothing-memo) for the public beats and a small
synthetic service.py for the MCP beats. Nothing here is hardcoded: every result is computed by the engine.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

SERVER = Path(__file__).resolve().parent.parent
PAIR = SERVER.parent / "docs" / "demo-pairs" / "nothing-memo"
WS = "ws_demo"

SERVICE_BASE = '''import logging

logger = logging.getLogger("northstar.partner_export")


def send_export(partner_id: str, batch_ref: str) -> None:
    logger.info("sending export batch=%s partner=%s", batch_ref, partner_id)
'''

SERVICE_RISKY = '''import logging

logger = logging.getLogger("northstar.partner_export")


def send_export(partner_id: str, batch_ref: str, api_token: str) -> None:
    logger.info("sending export batch=%s partner=%s token=%s", batch_ref, partner_id, api_token)
    upload(batch_ref, api_token)


def upload(batch_ref: str, api_token: str) -> None:
    pass
'''

SERVICE_FIXED = SERVICE_RISKY.replace(
    'logger.info("sending export batch=%s partner=%s token=%s", batch_ref, partner_id, api_token)',
    'logger.info("sending export batch=%s partner=%s", batch_ref, partner_id)')


# ---------------------------------------------------------------- setup
def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=Tracefold Demo", "-c", "user.email=demo@example.invalid",
                    "-c", "commit.gpgsign=false", *args], cwd=repo, check=True, capture_output=True)


def setup(data: Path, repo: Path) -> None:
    os.environ["TRACEFOLD_DATA"] = str(data)
    from tracefold.config import Settings
    from tracefold.engine import Engine
    s = Settings(data_dir=data.resolve())
    s.start_runner = False
    e = Engine(s)
    repo.mkdir(parents=True, exist_ok=True)
    if not (repo / ".git").exists():
        git(repo, "init", "-q", "-b", "main")
        (repo / "service.py").write_text(SERVICE_BASE)
        git(repo, "add", "service.py")
        git(repo, "commit", "-q", "-m", "Partner export service (published baseline)")
    if e.repo.get_workspace(WS) is None:
        e.add_workspace(WS, "Tracefold demo workspace", str(repo.resolve()))
    sources = json.loads((PAIR / "sources.json").read_text())
    e.add_manifest(WS, "nothing_live", [{**x, "mode": "seeded"} for x in sources])
    e.add_manifest(WS, "nothing_tavily", [{"source_id": "nothing_tavily", "url": sources[0]["url"], "provider": "tavily",
                                           "mode": "seeded"}])
    tokens_file = data / "demo_tokens.json"
    if not tokens_file.exists():
        tokens = {
            "app": e.add_client("demo-upload-app", {WS: (["submit", "read", "read_evidence", "recheck", "cancel", "review"], "full")}),
            "mcp": e.add_client("demo-mcp-adapter", {WS: (["submit", "read", "read_evidence", "recheck", "cancel"], "full")}),
        }
        tokens_file.write_text(json.dumps(tokens))
        tokens_file.chmod(0o600)
    print(f"Ready. Workspace {WS} → {repo.resolve()}\nTokens in {tokens_file} (mode 600).")


# ---------------------------------------------------------------- run
class Fail(Exception):
    pass


def expect(cond: bool, what: str) -> None:
    print(("  ✓ " if cond else "  ✗ ") + what)
    if not cond:
        raise Fail(what)


def wait(c: httpx.Client, url: str, h: dict, timeout: float = 180) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        s = c.get(url, headers=h).raise_for_status().json()
        if s["state"] not in ("queued", "running"):
            return s
        time.sleep(0.3)
    raise Fail(f"scan did not finish: {url}")


def cov(scan: dict, scope: str, id_: str) -> dict:
    return next((x for x in scan["coverage"] if x["scope"] == scope and x["id"] == id_), {})


def run(base: str, data: Path, repo: Path) -> int:
    tok = json.loads((data / "demo_tokens.json").read_text())
    app = {"Authorization": f"Bearer {tok['app']}"}
    mcp = {"Authorization": f"Bearer {tok['mcp']}"}
    b = f"/v1/workspaces/{WS}"
    t0 = time.time()
    with httpx.Client(base_url=base, timeout=60) as c:
        print("0:00 Platform, workspace and source list")
        caps = c.get("/v1/capabilities", headers=app).raise_for_status().json()
        m = c.get(f"{b}/manifests/nothing_live", headers=app).raise_for_status().json()
        for s in m["sources"]:
            print(f"     source {s['source_id']}: {s['url']} via {s['provider']} [{s['mode']}]")
        expect(m["sources"][0]["provider"] == "exa" and m["sources"][0]["mode"] == "seeded", "source list shows the seeded Exa URL")
        print(f"     model: {caps['model'].get('model_id') or caps['model']}")

        print("0:20 Upload the reference and scan")
        up = c.post(f"{b}/uploads", headers=app, files=[("file", ("upload-reference.txt",
                    (PAIR / "upload-reference.txt").read_bytes(), "text/plain"))]).raise_for_status().json()
        acc = c.post(f"{b}/scans", headers=app, json={"input_id": up["input_id"], "checks": ["public_match", "local_risk"],
                     "public_sources": {"manifest_id": "nothing_live", "mode": "refresh"}}).raise_for_status().json()
        s1 = wait(c, acc["status_url"], app)
        expect(s1["state"] == "completed", f"scan completed (state={s1['state']})")
        expect(s1["public_freshness"] == "fresh retrieval", "public source retrieved during this scan")

        print("0:45 Public exposure finding, side by side")
        f1 = c.get(f"{b}/findings", params={"scan_id": s1["scan_id"]}, headers=app).raise_for_status().json()["items"]
        pub = [f for f in f1 if f["kind"] == "public_exposure"]
        expect(len(pub) == 1, "exactly one public-exposure finding")
        ev_ref = pub[0]["latest"]["evidence"][0]
        ev = c.get(f"{b}/evidence/{ev_ref['evidence_id']}", headers=app).raise_for_status().json()
        print(f"     local : {ev['local_text'][:120]!r}")
        print(f"     public: …{ev['public_text'][60:200]!r}…")
        print(f"     {ev['public']['url']}\n     retrieved {ev['public']['retrieved_at']} via {ev['public']['provider']}, "
              f"{ev['public']['freshness']}, {ev['public']['mode']}; {ev['matched_tokens']} tokens, "
              f"{int(ev['segment_coverage'] * 100)}% of the passage")
        expect(ev["matched_tokens"] >= 12 and ev["public"]["provider"] == "exa", "computed overlap from the live Exa text")
        expect("smartphone" in ev["public_text"].lower(), "public span really contains the memo sentence")
        public_id = pub[0]["finding_id"]
        snap = s1["public_snapshot_id"]

        print("1:15 Same-topic negative, reusing the dated snapshot")
        up2 = c.post(f"{b}/uploads", headers=app, files=[("file", ("negative-control.txt",
                     (PAIR / "negative-control.txt").read_bytes(), "text/plain"))]).raise_for_status().json()
        acc2 = c.post(f"{b}/scans", headers=app, json={"input_id": up2["input_id"], "checks": ["public_match"],
                      "public_sources": {"manifest_id": "nothing_live", "mode": "snapshot", "snapshot_id": snap}}).raise_for_status().json()
        s2 = wait(c, acc2["status_url"], app)
        f2 = c.get(f"{b}/findings", params={"scan_id": s2["scan_id"]}, headers=app).raise_for_status().json()["items"]
        pm = cov(s2, "check", "public_match")
        print(f"     {s2['public_freshness']}; sources checked ok: {pm['counts'].get('sources_ok')}/{pm['counts'].get('sources_requested')}")
        expect(f2 == [] and pm["status"] == "complete", "no match in the checked sources (complete coverage)")
        expect(s2["public_freshness"].startswith("cached snapshot"), "snapshot reuse is disclosed")

        print("1:35 Assistant (MCP client) scans the unpublished service.py change")
        (repo / "service.py").write_text(SERVICE_RISKY)
        cap = c.post(f"{b}/captures", headers=mcp, json={"mode": "changes", "baseline": "HEAD"}).raise_for_status().json()
        expect([f["path"] for f in cap["files"]] == ["service.py"], "change capture picked up only service.py")
        acc3 = c.post(f"{b}/scans", headers=mcp, json={"input_id": cap["input_id"], "checks": ["local_risk"]}).raise_for_status().json()
        s3 = wait(c, acc3["status_url"], mcp)
        local = c.get(f"{b}/findings", params={"scan_id": s3["scan_id"]}, headers=mcp).raise_for_status().json()["items"]
        rule = [f for f in local if f["latest"]["origin"] == "rule"]
        expect(len(rule) == 1 and rule[0]["rule_id"] == "py_sensitive_logging", "one sensitive-logging finding")
        o = rule[0]["latest"]
        line = o["evidence"][0]["location"]["line_start"]
        print(f"     service.py:{line} — {o['claim']}\n     review: {o['risk_review']} ({o['model_id']})\n"
              f"     conditions: {o['conditions']}\n     fix: {o['suggested_fix']}")
        expect(line == 7, "real line reference (service.py:7)")
        expect(o["risk_review"] == "supported", "local model review supports it")
        others = [f for f in local if f["latest"]["origin"] == "model"]
        if others:
            print(f"     (+{len(others)} model-only suggestion(s) marked 'requires review')")
        local_id = rule[0]["finding_id"]

        print("2:10 Reviewed correction, recheck, platform shows the update")
        (repo / "service.py").write_text(SERVICE_FIXED)
        cap2 = c.post(f"{b}/captures", headers=mcp, json={"mode": "changes", "baseline": "HEAD"}).raise_for_status().json()
        rc = c.post(f"{b}/findings/{local_id}/rechecks", headers=mcp, json={"input_id": cap2["input_id"]}).raise_for_status().json()
        wait(c, rc["status_url"], mcp)
        d = c.get(f"{b}/findings/{local_id}", headers=app).raise_for_status().json()
        print(f"     finding {local_id}: {d['status']} at input revision {d['current_revision']} "
              f"(was {d['observations'][0]['revision']}); recheck {d['rechecks'][-1]['outcome']}")
        expect(d["rechecks"][-1]["outcome"] == "not_detected_in_checked_version", "pattern no longer detected in the checked version")
        expect(d["current_revision"] > d["observations"][0]["revision"], "same finding ID, new input version")
        pstat = c.get(f"{b}/findings/{public_id}", headers=app).raise_for_status().json()["status"]
        expect(pstat == "open", "earlier public exposure remains open")

        print("2:40 Outbound ledger and deployment boundary")
        for sid, label in ((s1["scan_id"], "upload scan"), (s3["scan_id"], "MCP scan")):
            led = c.get(f"{b}/scans/{sid}/ledger", headers=app).raise_for_status().json()["items"]
            for e_ in led:
                ps = e_["payload_summary"]
                print(f"     [{label}] {e_['destination_category']:<16} {e_['destination_host']:<16} {e_['status']:<4} "
                      f"{ps.get('urls') or ps.get('endpoint') or ''} {ps.get('auth', '')}")
            if label == "upload scan":
                ext = [x for x in led if x["destination_category"] != "local_model"]
                expect(ext and all(x["destination_host"] == "api.exa.ai" for x in ext), "only the Exa API call left the machine")
                expect(all(x["payload_summary"].get("urls") == [m["sources"][0]["url"]] for x in ext),
                       "it carried only the approved URL")
                expect(not any("smartphone" in json.dumps(x) for x in led), "no private text in outbound payloads")
            else:
                expect(all(x["destination_host"] in ("127.0.0.1", "localhost") for x in led), "MCP scan stayed on loopback")
        print(f"     retrieval isolation: {s1['summary'].get('retrieval_isolation')}")

        print("Rehearsal extra: a failed provider is not a negative result")
        up3 = c.post(f"{b}/uploads", headers=app, files=[("file", ("upload-reference.txt",
                     (PAIR / "upload-reference.txt").read_bytes(), "text/plain"))]).raise_for_status().json()
        acc4 = c.post(f"{b}/scans", headers=app, json={"input_id": up3["input_id"], "checks": ["public_match"],
                      "public_sources": {"manifest_id": "nothing_tavily", "mode": "refresh"}}).raise_for_status().json()
        s4 = wait(c, acc4["status_url"], app)
        src = cov(s4, "source", "nothing_tavily")
        print(f"     tavily: {src.get('status')} ({src.get('reason')}); scan state {s4['state']}")
        expect(s4["state"] != "completed" and cov(s4, "check", "public_match")["status"] == "failed",
               "failed retrieval is reported as failed, not 'no match'")

    (repo / "service.py").write_text(SERVICE_BASE)  # reset the working tree for the next rehearsal
    print(f"\nAll demo beats passed in {time.time() - t0:.1f}s.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("setup", "run"):
        p = sub.add_parser(name)
        p.add_argument("--data", default="demo-data")
        p.add_argument("--repo", default="demo-repo")
        if name == "run":
            p.add_argument("--base", default="http://127.0.0.1:8787")
    a = ap.parse_args()
    data, repo = Path(a.data).resolve(), Path(a.repo).resolve()
    if a.cmd == "setup":
        setup(data, repo)
        return 0
    try:
        return run(a.base, data, repo)
    except Fail as ex:
        print(f"\nREHEARSAL FAILED: {ex}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
