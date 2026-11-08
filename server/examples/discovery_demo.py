"""Company-discovery demo: a mock Apple internal memo, traced to public pages by search on the company name alone.

    cd server
    # 1. one-time setup: workspace, approved public identity, query plan, tokens (operator step; needs no network)
    uv run python examples/discovery_demo.py setup --data data/discovery-demo
    # 2a. rehearse in-process (no server needed), or
    uv run python examples/discovery_demo.py run --data data/discovery-demo
    # 2b. against a running engine: TRACEFOLD_DATA=data/discovery-demo uv run tracefold serve --port 8787
    uv run python examples/discovery_demo.py run --data data/discovery-demo --url http://127.0.0.1:8787

The upload is docs/demo-pairs/mock-leaks/apple_memo/mock-internal-memo.md: a SIMULATED internal memo (invented filler
around two short passages that public outlets quote verbatim from Tim Cook's 2021 leaked memo). Present it as a
simulation. Nothing is hardcoded: the search results, fetched pages and matches are whatever the engine computes now.
`run` exits non-zero if a step does not produce what the demo needs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

SERVER = Path(__file__).resolve().parent.parent
PAIR = SERVER.parent / "docs" / "demo-pairs" / "mock-leaks" / "apple_memo"
WS = "ws_demo"
IDENTITY = {"display_name": "Apple", "official_domain": "apple.com", "public_aliases": [], "confirm_public": True}
# Benchmarked presets that fit a leaked memo (docs/benchmark/README.md), on both providers: 4 searches × 5 results.
PLAN = {"presets": ["leak_news", "leaked_email"], "providers": ["exa", "tavily"], "scope": {"mode": "broad"}}
UPLOAD = "mock-internal-memo.md"
NEGATIVE = "negative-control.md"


class Fail(Exception):
    pass


def expect(cond: bool, what: str) -> None:
    print(("  ✓ " if cond else "  ✗ ") + what, flush=True)
    if not cond:
        raise Fail(what)


def _state(data: Path) -> Path:
    return data / "discovery_demo.json"


# ---------------------------------------------------------------- setup
def setup(data: Path) -> None:
    from fastapi.testclient import TestClient

    from tracefold.api.app import create_app
    from tracefold.config import Settings
    from tracefold.engine import Engine
    s = Settings(data_dir=data.resolve())
    s.start_runner = False
    s.allowed_hosts = (*s.allowed_hosts, "testserver")
    e = Engine(s)
    if e.repo.get_workspace(WS) is None:
        e.add_workspace(WS, "Tracefold demo workspace", None)
    st = json.loads(_state(data).read_text()) if _state(data).exists() else {}
    if "app_token" not in st:
        st["app_token"] = e.add_client("discovery-demo-app", {WS: (["submit", "read", "read_evidence", "cancel"], "full")})
        st["operator_token"] = e.add_client("discovery-demo-operator", {WS: (["configure", "read"], "full")})
    if "web_token" not in st:  # the web app: a person approves identities and plans there (MCP-style tokens can't)
        st["web_token"] = e.add_client("discovery-demo-web", {WS: (["configure", "submit", "read", "read_evidence", "cancel",
                                                                    "recheck", "review"], "full")})
    h = {"Authorization": f"Bearer {st['operator_token']}"}
    with TestClient(create_app(e)) as c:
        if "query_plan_id" in st:  # idempotent: reuse the approved identity and plan
            prof = c.get(f"/v1/workspaces/{WS}/company-profiles/{st['profile_id']}", headers=h).raise_for_status().json()
            plan = c.get(f"/v1/workspaces/{WS}/query-plans/{st['query_plan_id']}", headers=h).raise_for_status().json()
        else:
            prof = c.post(f"/v1/workspaces/{WS}/company-profiles", headers=h, json=IDENTITY).raise_for_status().json()
            plan = c.post(f"/v1/workspaces/{WS}/query-plans", headers=h,
                          json={"profile_id": prof["profile_id"], **PLAN}).raise_for_status().json()
    st.update(profile_id=prof["profile_id"], query_plan_id=plan["query_plan_id"])
    _state(data).write_text(json.dumps(st, indent=2))
    _state(data).chmod(0o600)
    print(f"Workspace {WS} ready in {data}. Approved identity: {prof['display_name']} ({prof['official_domain']}).")
    print(f"Privacy notice shown to the user: {prof['privacy_notice']}")
    print(f"Query plan {plan['query_plan_id']} ({plan['template_version']}), exactly these searches leave the machine:")
    for q in plan["searches"]:
        extra = {k: q[k] for k in ("category", "topic", "exact_match") if q.get(k) is not None}
        print(f"  {q['query_id']} {q['provider']:6} {q['query']!r} {extra} excludes {len(q['exclude_domains'] or [])} domains")
    print(f"Tokens in {_state(data)} (mode 600). app_token (MCP-style) cannot approve identities or plans; web_token "
          "(for the web app, where a person approves them) can.")


# ---------------------------------------------------------------- run
def _client(data: Path, url: str | None):
    if url:
        return httpx.Client(base_url=url, timeout=60), None
    from fastapi.testclient import TestClient

    from tracefold.api.app import create_app
    from tracefold.config import Settings
    from tracefold.engine import Engine
    s = Settings(data_dir=data.resolve())
    s.allowed_hosts = (*s.allowed_hosts, "testserver")
    e = Engine(s)
    c = TestClient(create_app(e))
    c.__enter__()
    return c, e


def run(data: Path, url: str | None) -> int:
    from tracefold.envfile import load_env_file
    load_env_file(SERVER / ".env")
    st = json.loads(_state(data).read_text())
    c, _engine = _client(data, url)
    h = {"Authorization": f"Bearer {st['app_token']}"}
    b = f"/v1/workspaces/{WS}"
    memo = (PAIR / UPLOAD).read_bytes()
    try:
        print("\n[1] The approved query plan (what search providers will see)")
        plan = c.get(f"{b}/query-plans/{st['query_plan_id']}", headers=h).raise_for_status().json()
        for q in plan["searches"]:
            print(f"     {q['provider']:6} {q['query']}")
        from tracefold.discovery.presets import PRESETS
        ident = {"display_name": plan["display_name"], "official_domain": plan["official_domain"], "public_aliases": []}
        rendered = {PRESETS[q["template_id"]][q["provider"]]["query"].format(
            name=ident["display_name"], alias="", domain=ident["official_domain"] or "", hint="").strip() for q in plan["searches"]}
        expect({q["query"] for q in plan["searches"]} <= rendered,
               "every query is a fixed catalog template filled with the approved public name")

        print("\n[2] Upload the mock internal memo and a negative control")
        inp = c.post(f"{b}/uploads", headers=h, files=[("file", (UPLOAD, memo, "text/markdown")),
                                                      ("file", (NEGATIVE, (PAIR / NEGATIVE).read_bytes(), "text/markdown"))]
                     ).raise_for_status().json()
        expect(all(f["status"] == "captured" for f in inp["files"]), "both files captured in memory")

        print("\n[3] Scan: search → validate URLs → extract → compare locally")
        acc = c.post(f"{b}/scans", headers=h, json={"input_id": inp["input_id"], "checks": ["public_match"],
                                                    "public_discovery": {"query_plan_id": st["query_plan_id"]},
                                                    "model_review": False}).raise_for_status().json()
        t0, last = time.time(), None
        while True:
            s = c.get(acc["status_url"], headers=h).raise_for_status().json()
            stages = " → ".join(f"{x['name']}:{x['status']}" for x in s["stages"])
            if stages != last:
                print(f"     {stages}")
                last = stages
            if s["state"] not in ("queued", "running"):
                break
            if time.time() - t0 > 300:
                raise Fail("scan did not finish within 5 minutes")
            time.sleep(0.5)
        d = s["public_discovery"]
        print(f"     {s['state']} in {time.time() - t0:.1f}s: {d['returned_count']} results, {d['unique_count']} unique pages, "
              f"{d['fetched_count']} fetched; {s['budget'].get('provider_requests')} provider requests")
        expect(d["outcome"] in ("candidates_found", "partial_search"), f"search returned candidates ({d['outcome']})")

        print("\n[4] Every source, not just the alarming ones")
        src = c.get(f"{b}/scans/{s['scan_id']}/sources?limit=100", headers=h).raise_for_status().json()
        for x in src["items"]:
            print(f"     [{x['comparison_status']:12}] {x['original_url'][:95]}")

        print("\n[5] Findings: which memo passages appear publicly, and where")
        fs = c.get(f"{b}/findings?scan_id={s['scan_id']}", headers=h).raise_for_status().json()["items"]
        pub = [f for f in fs if f["kind"] == "public_exposure"]
        for f in pub:
            ev = f["latest"]["evidence"][0]
            full = c.get(f"{b}/evidence/{ev['evidence_id']}", headers=h).raise_for_status().json()
            o = ev["public"]["discovery_origins"][0]
            print(f"     {f['path']} lines {ev['location']['line_start']}-{ev['location']['line_end']}  ↔  {ev['public']['url']}")
            print(f"       found by {o['provider']} query {o['query_id']} (rank {o['rank']}); retrieved {ev['public']['retrieved_at']}")
            print(f"       matched text: {' '.join((full.get('public_text') or '').split())!r}")
        expect(len({f['latest']['evidence'][0]['public']['url'] for f in pub}) >= 1, "at least one public page quotes the memo")
        expect(all(f["path"] == UPLOAD for f in pub), "the negative control matched nothing")

        print("\n[6] What left the machine")
        led = c.get(f"{b}/scans/{s['scan_id']}/ledger?limit=100", headers=h).raise_for_status().json()["items"]
        searches = [x for x in led if x["purpose"] == "search_approved_public_query"]
        extracts = [x for x in led if x["purpose"] == "extract_approved_public_url"]
        print(f"     {len(searches)} searches, {len(extracts)} extraction requests")
        dump = json.dumps(led)
        expect(not any(seg in dump for seg in ("leak confidential information", "everything in our power", UPLOAD, "mock-internal")),
               "no memo text or filename in any outbound request")
        expect(all(os.environ.get(k, "~") not in dump for k in ("EXA_API_KEY", "TAVILY_API_KEY")), "provider keys masked")
        print("\nDemo ready. Remember to say: the memo is a simulation built from a real leaked memo's published text.")
        return 0
    except Fail as ex:
        print(f"\nFAILED: {ex}", file=sys.stderr)
        return 1
    finally:
        if hasattr(c, "__exit__"):
            c.__exit__(None, None, None)


# ---------------------------------------------------------------- agent (MCP segment)
# A synthetic code change for the coding-assistant beat: an uncommitted edit that logs an API key. The assistant scans
# it with scan_changes, proposes the fix, the edit is applied in the editor, and recheck_fix checks that one problem.
AGENT_BASE = '''"""Billing client used by the checkout service (synthetic Tracefold demo code)."""
import logging

logger = logging.getLogger(__name__)


def charge(customer_id: str, amount_cents: int, api_key: str) -> dict:
    logger.info("charging %s for %d cents", customer_id, amount_cents)
    return {"customer": customer_id, "amount": amount_cents}
'''
AGENT_CHANGE = AGENT_BASE.replace(
    '    logger.info("charging %s for %d cents", customer_id, amount_cents)\n',
    '    logger.info("charging %s for %d cents", customer_id, amount_cents)\n'
    '    logger.debug("billing request for %s using key %s", customer_id, api_key)\n',
)
MCP_CAPS = ["submit", "read", "read_evidence", "recheck", "cancel"]  # never approve or configure


def agent(data: Path, mcp_config: Path, port: int) -> None:
    """Register a small Git project as the demo workspace's folder, reset its uncommitted risky change, and point the
    MCP adapter at this engine so the app and the assistant share one finding history. Run with the engine stopped."""
    import subprocess

    from tracefold.config import Settings
    from tracefold.engine import Engine
    proj = (data / "agent-project").resolve()
    src = proj / "billing" / "client.py"
    git = ["git", "-C", str(proj), "-c", "user.name=Tracefold demo", "-c", "user.email=demo@example.invalid"]
    if not (proj / ".git").exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(AGENT_BASE)
        subprocess.run([*git[:3], "init", "-q"], check=True)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "Billing client"], check=True)
    src.write_text(AGENT_CHANGE)  # reset the demo: the risky line is back as an uncommitted change

    e = Engine(Settings(data_dir=data.resolve()))
    if e.repo.get_workspace(WS) is None:
        raise SystemExit("Run `setup` first.")
    with e.repo.db.tx() as c:
        c.execute("UPDATE workspaces SET source_type='local_dir', root=? WHERE id=?", (str(proj), WS))
    st = json.loads(_state(data).read_text())
    if "mcp_token" not in st:
        st["mcp_token"] = e.add_client("discovery-demo-assistant", {WS: (MCP_CAPS, "full")})
        _state(data).write_text(json.dumps(st, indent=2))
        _state(data).chmod(0o600)

    mcp_config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = mcp_config.with_suffix(".json.bak")
    if mcp_config.exists() and not backup.exists():
        backup.write_bytes(mcp_config.read_bytes())
        backup.chmod(0o600)
    cfg = {"base_url": f"http://127.0.0.1:{port}", "token": st["mcp_token"], "workspace_id": WS}
    mcp_config.write_text(json.dumps(cfg, indent=2) + "\n")
    mcp_config.chmod(0o600)
    print(f"Workspace {WS} now reads {proj}; billing/client.py has the uncommitted risky change.")
    print(f"MCP adapter config written to {mcp_config} (engine 127.0.0.1:{port}, {WS})."
          + (f" Previous config kept at {backup}." if backup.exists() else ""))
    print("Restart your coding assistant so it reconnects, then ask it to run scan_changes.")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("setup", "run", "agent"):
        p = sub.add_parser(n)
        p.add_argument("--data", default="data/discovery-demo")
        if n == "run":
            p.add_argument("--url", help="running engine base URL; omit to run in-process")
        if n == "agent":
            p.add_argument("--mcp-config", default=str(Path.home() / ".config" / "tracefold" / "mcp.json"))
            p.add_argument("--port", type=int, default=8790)
    a = ap.parse_args()
    data = Path(a.data)
    if a.cmd == "setup":
        data.mkdir(parents=True, exist_ok=True)
        setup(data)
        return 0
    if a.cmd == "agent":
        agent(data, Path(a.mcp_config).expanduser(), a.port)
        return 0
    return run(data, a.url)


if __name__ == "__main__":
    raise SystemExit(main())
