"""Preset benchmark (docs/PRESET_PLAN.md §5–6): record live runs once, score offline.

    cd server
    uv run python examples/preset_benchmark.py record --cases ../docs/benchmark/cases.json --out ../docs/benchmark/v3
    uv run python examples/preset_benchmark.py score --dir ../docs/benchmark/v3

`record` runs one real scan per case × pack through the HTTP API and the isolated worker (each capped at 40 provider
requests). It saves search metadata (URL, title, rank), per-source fetch/compare status, and two locally computed facts per
fetched page: whether it mentions the company and which uploads matched. Page text is not saved. Known copies are used
only for scoring; they are never sent to a provider or injected into results.
`score` recomputes per-preset and per-pack metrics from the saved records with no network access.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

SERVER = Path(__file__).resolve().parent.parent
REPO = SERVER.parent


def norm(url: str) -> str:
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    path = p.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, p.query, ""))


def is_known(url: str, known: list[dict]) -> int | None:
    u = norm(url)
    for i, k in enumerate(known):
        if k.get("url_regex"):
            if re.match(k["url_regex"], url.strip().split("#")[0]):
                return i
            continue
        ku = norm(k["url"])
        if k.get("prefix"):
            if u.startswith(ku.rstrip("/")) and u.endswith(k.get("suffix", "")):
                return i
        elif u == ku:
            return i
    return None


# ------------------------------------------------------------------ record
def record(cases_path: Path, out_dir: Path, only: set[str] | None, force: bool = False) -> None:
    from fastapi.testclient import TestClient

    from tracefold.envfile import load_env_file
    load_env_file(SERVER / ".env")
    from tracefold.api.app import create_app
    from tracefold.config import Settings
    from tracefold.engine import Engine

    out_dir.mkdir(parents=True, exist_ok=True)
    cases = json.loads(cases_path.read_text())
    for case in cases:
        if only and case["case_id"] not in only:
            continue
        runs = [(x, {"pack": x}) if isinstance(x, str) else (x["name"], {"presets": x["presets"]}) for x in case["packs"]]
        runs = [(n, body) for n, body in runs if force or not (out_dir / f"{case['case_id']}__{n}.json").exists()]
        if not runs:
            continue
        data = Path(tempfile.mkdtemp(prefix=f"tf-bench-{case['case_id']}-"))
        s = Settings(data_dir=data)
        s.allowed_hosts = (*s.allowed_hosts, "testserver")
        s.retrieval_in_process = False
        e = Engine(s)
        ws = "ws_bench"
        e.add_workspace(ws, "Preset benchmark", None)
        tok = e.add_client("bench", {ws: (["configure", "submit", "read", "read_evidence"], "full")})
        h = {"Authorization": f"Bearer {tok}"}
        b = f"/v1/workspaces/{ws}"
        ident = case["identity"]
        terms = [t.lower() for t in [ident["display_name"], ident.get("official_domain") or "", *ident.get("public_aliases", [])] if t]
        uploads = [(REPO / x, "reference") for x in case["references"]] + [(REPO / x, "negative") for x in case["negatives"]]
        roles = {p.name: role for p, role in uploads}
        with TestClient(create_app(e)) as c:
            prof = c.post(f"{b}/company-profiles", headers=h, json={**ident, "confirm_public": True}).raise_for_status().json()
            for pack, body in runs:
                r0 = c.post(f"{b}/query-plans", headers=h, json={"profile_id": prof["profile_id"], **body,
                                                               "include_experimental": True})
                if r0.status_code == 422:  # e.g. every preset in a group needs a domain or alias this profile lacks
                    print(f"{case['case_id']:13} {pack:16} skipped: {r0.json()['error']['message']}", flush=True)
                    continue
                plan = r0.raise_for_status().json()
                inp = c.post(f"{b}/uploads", headers=h, files=[("file", (p.name, p.read_bytes(), "text/plain"))
                                                               for p, _ in uploads]).raise_for_status().json()
                acc = c.post(f"{b}/scans", headers=h, json={"input_id": inp["input_id"], "checks": ["public_match"],
                                                              "public_discovery": {"query_plan_id": plan["query_plan_id"]},
                                                              "model_review": False}).raise_for_status().json()
                t0 = time.time()
                while (scan := c.get(acc["status_url"], headers=h).raise_for_status().json())["state"] in ("queued", "running"):
                    time.sleep(0.5)
                elapsed = round(time.time() - t0, 1)
                run = e.repo.discovery_run_for_scan(scan["scan_id"])
                raw = [d for _, d in e.repo.discovery_sources(scan["scan_id"], -1, 1000)]
                findings = c.get(f"{b}/findings?scan_id={scan['scan_id']}&limit=100", headers=h).raise_for_status().json()["items"]
                matched: dict[str, list[dict]] = {}
                for f in findings:
                    ev = f["latest"]["evidence"][0]
                    matched.setdefault(ev["public"]["source_id"], []).append(
                        {"upload": f["path"], "role": roles.get(f["path"]), "tokens": ev["matched_tokens"]})
                ledger = c.get(f"{b}/scans/{scan['scan_id']}/ledger?limit=100", headers=h).raise_for_status().json()["items"]
                sources = []
                for d in raw:
                    text = e.retrieval.blobs.read(d["content_hash"]) if d.get("content_hash") else None
                    sources.append({
                        "source_id": d["source_id"], "url": d["original_url"], "fetch_status": d["fetch_status"],
                        "failure_reason": d.get("failure_reason"), "comparison_status": d["comparison_status"],
                        "truncated": d.get("truncated", False), "origins": d["discovery_origins"],
                        "mentions_company": (any(t in text.lower() for t in terms) if text is not None else None),
                        "matches": matched.get(d["source_id"], [])})
                rec = {"case_id": case["case_id"], "label": case["label"], "pack": pack,
                       "template_version": plan["template_version"], "searches": plan["searches"],
                       "omitted_presets": plan["omitted_presets"], "scan_state": scan["state"],
                       "elapsed_seconds": elapsed, "provider_requests": scan["budget"].get("provider_requests", 0),
                       "response_bytes": sum(x["payload_summary"].get("bytes", 0) for x in ledger),
                       "provider_queries": [{k: q.get(k) for k in ("query_id", "template_id", "provider", "query", "status",
                                                                     "error", "returned", "truncated", "searched_at")}
                                            for q in run["data"]["provider_queries"]],
                       "sources": sources, "recorded_at": scan["finished_at"]}
                path = out_dir / f"{case['case_id']}__{pack}.json"
                path.write_text(json.dumps(rec, indent=2) + "\n")
                print(f"{case['case_id']:13} {pack:16} {scan['state']:9} {elapsed:5}s req={rec['provider_requests']:2} "
                      f"sources={len(sources)} matched={sum(bool(x['matches']) for x in sources)}", flush=True)


# ------------------------------------------------------------------ score
def score(rec_dir: Path, cases_path: Path) -> dict:
    cases = {c["case_id"]: c for c in json.loads(cases_path.read_text())}
    recs = [json.loads(p.read_text()) for p in sorted(rec_dir.glob("*__*.json"))]
    per_preset: dict[tuple[str, str], dict] = {}
    per_pack: list[dict] = []
    for r in recs:
        known = cases[r["case_id"]]["known_copies"]
        qmeta = {q["query_id"]: q for q in r["provider_queries"]}
        found_known: set[int] = set()
        for q in r["provider_queries"]:
            k = (q["template_id"], q["provider"])
            m = per_preset.setdefault(k, {"preset": k[0], "provider": k[1], "searches": 0, "searches_failed": 0, "returned": 0,
                                          "fetched": 0, "noise": 0, "matched_pages": 0, "target_hits": 0,
                                          "target_opportunities": 0, "cases_hit": set(), "negative_matches": 0})
            m["searches"] += 1
            m["searches_failed"] += q["status"] != "ok"
            m["returned"] += q.get("returned") or 0
            m["target_opportunities"] += len(known)
        for s in r["sources"]:
            ki = is_known(s["url"], known)
            for o in s["origins"]:
                q = qmeta.get(o["query_id"])
                if q is None:
                    continue
                m = per_preset[(q["template_id"], q["provider"])]
                if s["fetch_status"] == "fetched":
                    m["fetched"] += 1
                    m["noise"] += s["mentions_company"] is False
                    m["matched_pages"] += any(x["role"] == "reference" for x in s["matches"])
                    m["negative_matches"] += any(x["role"] == "negative" for x in s["matches"])
                if ki is not None:
                    m["target_hits"] += 1
                    m["cases_hit"].add(r["case_id"] + (" (first-party)" if known[ki].get("first_party") else ""))
            if ki is not None:
                found_known.add(ki)
        fetched = [s for s in r["sources"] if s["fetch_status"] == "fetched"]
        third = [i for i, k in enumerate(known) if not k.get("first_party")]
        first = [i for i, k in enumerate(known) if k.get("first_party")]
        per_pack.append({
            "case_id": r["case_id"], "pack": r["pack"], "scan_state": r["scan_state"],
            "third_party_found": f"{len(found_known & set(third))}/{len(third)}" if third else "n/a",
            "first_party_found": f"{len(found_known & set(first))}/{len(first)}" if first else "n/a",
            "matched_pages": sum(any(x["role"] == "reference" for x in s["matches"]) for s in fetched),
            "negative_matches": sum(any(x["role"] == "negative" for x in s["matches"]) for s in fetched),
            "fetched": len(fetched), "noise_rate": round(sum(s["mentions_company"] is False for s in fetched) / len(fetched), 2)
            if fetched else None, "provider_requests": r["provider_requests"], "elapsed_seconds": r["elapsed_seconds"],
            "omitted_presets": [o["preset"] for o in r["omitted_presets"]]})
    presets = []
    for m in per_preset.values():
        m["cases_hit"] = sorted(m["cases_hit"])
        m["noise_rate"] = round(m["noise"] / m["fetched"], 2) if m["fetched"] else None
        presets.append(m)
    presets.sort(key=lambda m: (m["preset"], m["provider"]))
    return {"records": len(recs), "per_pack": per_pack, "per_preset": presets}


def to_markdown(sc: dict) -> str:
    lines = ["First-party copies live on the company's own domain, which v3 excludes from results by default.", "",
             "| Case | Pack | State | Third-party copies found | First-party found | Matched pages | Neg. matches | Fetched | "
             "Noise rate | Requests | Seconds |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in sc["per_pack"]:
        lines.append(f"| {p['case_id']} | {p['pack']} | {p['scan_state']} | {p['third_party_found']} | {p['first_party_found']} | "
                     f"{p['matched_pages']} | "
                     f"{p['negative_matches']} | {p['fetched']} | {p['noise_rate']} | {p['provider_requests']} | {p['elapsed_seconds']} |")
    lines += ["", "| Preset | Provider | Searches (failed) | Returned | Fetched | Noise rate | Matched pages | Known-copy hits | Cases hit |",
              "|---|---|---|---|---|---|---|---|---|"]
    for m in sc["per_preset"]:
        lines.append(f"| {m['preset']} | {m['provider']} | {m['searches']} ({m['searches_failed']}) | {m['returned']} | "
                     f"{m['fetched']} | {m['noise_rate']} | {m['matched_pages']} | {m['target_hits']} | "
                     f"{', '.join(m['cases_hit']) or '–'} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--cases", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--only", help="comma-separated case ids")
    r.add_argument("--force", action="store_true", help="re-record runs that already have a record")
    s = sub.add_parser("score")
    s.add_argument("--dir", required=True)
    s.add_argument("--cases", default=str(REPO / "docs" / "benchmark" / "cases.json"))
    a = ap.parse_args()
    if a.cmd == "record":
        record(Path(a.cases), Path(a.out), set(a.only.split(",")) if a.only else None, a.force)
        return 0
    sc = score(Path(a.dir), Path(a.cases))
    Path(a.dir, "scores.json").write_text(json.dumps(sc, indent=2) + "\n")
    Path(a.dir, "scores.md").write_text(to_markdown(sc))
    sys.stdout.write(to_markdown(sc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
