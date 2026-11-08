"""One bounded live company-discovery rehearsal (docs/COMPANY_DISCOVERY_PLAN.md step 6).

Approves a public company identity, creates a fixed query plan, and runs one real scan through the HTTP API with the
isolated worker: Exa/Tavily search → URL validation → extraction → local matching. Uploads are compared locally only.
Nothing is injected: whatever the searches actually return is what gets fetched and reported, including zero results.

    cd server && uv run python examples/discovery_rehearsal.py --out ../docs/sample-documents/nothing-memo/discovery-rehearsal.json

Other companies: --name, --domain, --alias (≤2), --presets, --providers, --upload (local files, repeatable) and an
optional --target URL to report whether search returned it. Defaults reproduce the Nothing run 2.

Costs: at most 4 searches + ~20 extractions (+ fallbacks), capped at 40 provider requests by the engine.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

SERVER = Path(__file__).resolve().parent.parent
PAIR = SERVER.parent / "docs" / "sample-documents" / "nothing-memo"
WS = "ws_discovery_rehearsal"

IDENTITY = {"display_name": "Nothing Technology", "official_domain": "nothing.tech", "public_aliases": ["Nothing Phone"],
            "confirm_public": True}
# Run 1 (company_queries_v1, presets identity + internal_docs) did not return the target; see the saved record.
PLAN = {"presets": ["leak_reports", "alias_leak_reports"], "providers": ["exa", "tavily"], "scope": {"mode": "broad"},
        "results_per_query": 5}
TARGET = "https://www.phonearena.com/news/nothings-first-flagship-phone-coming-this-quarter_id166566"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--presets", help="comma-separated presets (default: the current PLAN)")
    ap.add_argument("--providers", help="comma-separated providers (default: exa,tavily)")
    ap.add_argument("--name")
    ap.add_argument("--domain")
    ap.add_argument("--alias", action="append")
    ap.add_argument("--upload", action="append", help="local file compared locally (repeatable)")
    ap.add_argument("--target", help="URL to check for in the returned candidates (reporting only; never injected)")
    args = ap.parse_args()
    if args.presets:
        PLAN["presets"] = args.presets.split(",")
    if args.providers:
        PLAN["providers"] = args.providers.split(",")
    identity = dict(IDENTITY)
    if args.name:
        identity = {"display_name": args.name, "official_domain": args.domain, "public_aliases": args.alias or [],
                    "confirm_public": True}
    uploads = [Path(u) for u in args.upload] if args.upload else [PAIR / "upload-reference.txt", PAIR / "negative-control.txt"]
    target = args.target if (args.target or args.name) else TARGET

    from tracefold.envfile import load_env_file
    loaded = load_env_file(SERVER / ".env")
    from tracefold.api.app import create_app
    from tracefold.config import Settings
    from tracefold.engine import Engine

    data = Path(tempfile.mkdtemp(prefix="tf-discovery-rehearsal-"))
    s = Settings(data_dir=data)
    s.allowed_hosts = (*s.allowed_hosts, "testserver")
    s.retrieval_in_process = False  # real isolated worker process
    e = Engine(s)
    e.add_workspace(WS, "Discovery rehearsal", None)
    app_token = e.add_client("rehearsal-app", {WS: (["configure", "submit", "read", "read_evidence"], "full")})
    h = {"Authorization": f"Bearer {app_token}"}
    b = f"/v1/workspaces/{WS}"
    with TestClient(create_app(e)) as c:
        prof = c.post(f"{b}/company-profiles", headers=h, json=identity).raise_for_status().json()
        plan = c.post(f"{b}/query-plans", headers=h, json={"profile_id": prof["profile_id"], **PLAN}).raise_for_status().json()
        print("Approved identity:", prof["display_name"], prof["official_domain"], prof["public_aliases"])
        print("Privacy notice:", prof["privacy_notice"])
        for q in plan["searches"]:
            print(f"  {q['query_id']} {q['provider']:6} {q['query']}")
        files = [("file", (u.name, u.read_bytes(), "text/plain")) for u in uploads]
        inp = c.post(f"{b}/uploads", headers=h, files=files).raise_for_status().json()
        acc = c.post(f"{b}/scans", headers=h, json={"input_id": inp["input_id"], "checks": ["public_match"],
                                                      "public_discovery": {"query_plan_id": plan["query_plan_id"]},
                                                      "model_review": False}).raise_for_status().json()
        t0 = time.time()
        while True:
            scan = c.get(acc["status_url"], headers=h).raise_for_status().json()
            if scan["state"] not in ("queued", "running"):
                break
            time.sleep(0.5)
        elapsed = round(time.time() - t0, 1)
        sources = c.get(f"{b}/scans/{scan['scan_id']}/sources?limit=100", headers=h).raise_for_status().json()
        findings = c.get(f"{b}/findings?scan_id={scan['scan_id']}", headers=h).raise_for_status().json()["items"]
        ledger = c.get(f"{b}/scans/{scan['scan_id']}/ledger?limit=100", headers=h).raise_for_status().json()["items"]

    pub_cov = next(x for x in scan["coverage"] if x["scope"] == "check" and x["id"] == "public_match")
    matches = []
    for f in findings:
        ev = f["latest"]["evidence"][0]
        matches.append({"local_file": f["path"], "url": ev["public"]["url"], "matched_tokens": ev["matched_tokens"],
                        "segment_coverage": ev["segment_coverage"], "retrieved_at": ev["public"]["retrieved_at"],
                        "extraction_provider": ev["public"]["provider"], "discovery_origins": ev["public"]["discovery_origins"]})
    bytes_in = sum(x["payload_summary"].get("bytes", 0) for x in ledger)
    out = {
        "kind": "live_company_discovery_rehearsal",
        "note": "Actual results of one live run. Nothing was injected; zero/failed results are recorded as returned.",
        "identity": {k: prof[k] for k in ("display_name", "official_domain", "public_aliases", "version",
                                          "privacy_notice_version")},
        "query_plan": {"template_version": plan["template_version"], "searches": plan["searches"], "scope": plan["scope"]},
        "uploads_compared_locally": [u.name for u in uploads],
        "scan": {"state": scan["state"], "created_at": scan["created_at"], "finished_at": scan["finished_at"],
                 "elapsed_seconds": elapsed, "public_match_coverage": pub_cov, "budget": scan["budget"],
                 "retrieval_isolation": scan["summary"].get("retrieval_isolation"), "errors": scan["errors"]},
        "discovery": sources["discovery"],
        "sources": [{k: x[k] for k in ("original_url", "title", "discovery_origins", "extraction_provider", "fetch_status",
                                        "failure_reason", "retrieved_at", "provider_content_timestamp", "truncated",
                                        "comparison_status", "match_count")} for x in sources["items"]],
        "matches": matches,
        "expected_target": ({"url": target, "returned_by_search": any(
            x["original_url"].rstrip("/") == target.rstrip("/") for x in sources["items"])} if target else None),
        "provider_requests": [{"host": x["destination_host"], "purpose": x["purpose"], "status": x["status"],
                               "at": x["at"], "query_or_url": x["payload_summary"].get("query") or x["payload_summary"].get("urls")}
                              for x in ledger if x["destination_category"] == "provider_api"],
        "response_bytes": bytes_in,
        "env_loaded": sorted(loaded),
    }
    Path(args.out).write_text(json.dumps(out, indent=2) + "\n")
    d = sources["discovery"]
    print(f"\nScan {scan['state']} in {elapsed}s; public_match coverage {pub_cov['status']} ({pub_cov['reason']})")
    print(f"Discovery outcome {d['outcome']}: returned {d['returned_count']}, unique {d['unique_count']}, "
          f"fetched {d['fetched_count']}, skipped {d['skipped_count']}, errors {d['search_errors']}")
    print(f"Provider requests: {scan['budget'].get('provider_requests')}; response bytes {bytes_in}")
    for x in sources["items"]:
        print(f"  [{x['fetch_status']:13}] [{x['comparison_status']:12}] {x['original_url']}")
    if target:
        print(f"Expected target returned by search: {out['expected_target']['returned_by_search']}")
    for m in matches:
        print(f"  MATCH {m['local_file']} ↔ {m['url']} ({m['matched_tokens']} tokens)")
    print(f"Saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
