"""Company-name discovery: approved profiles, immutable query plans, and the per-scan search → validate →
extract → compare flow.

Search results are candidate URLs only. Findings still come exclusively from the existing local matcher over
fully extracted public text; search ranks, titles or snippets never become evidence. Omission from a later
search is never evidence that a public copy disappeared.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.enums import Capability, ComparisonStatus, CoverageStatus, FetchStatus
from ..contracts.models import (
    CompanyIn, CompanyOut, CompanyProfileIn, CompanyProfileList, CompanyProfileOut, DiscoveryRunOut, QueryPlanIn, QueryPlanOut, QueryPlanPage, QueryPresetCatalog,
    SourceOut, SourcePage,
)
from ..errors import ApiError, not_found
from ..policy.auth import Principal
from ..util import iso, new_id, now
from . import identity, presets
from .urls import canonicalize, check_url, source_id_for

if TYPE_CHECKING:
    from ..engine import Engine
    from ..jobs.pipeline import ScanContext

FRESHNESS_NOTE = ("API retrieval during this scan. This is not the origin's publication or crawl time, and provider "
                  "caches are possible.")
RUN_NOTE = ("Discovery shows what the approved queries returned at search time. It is not exhaustive, does not prove "
            "company attribution, and an empty result is not evidence that nothing leaked.")
# Fetch errors that are budget/deadline exhaustion (shown as skipped_limit, never retried).
LIMIT_ERRORS = {"request_budget_exhausted", "deadline_exceeded", "worker_timeout"}
SEARCH_RESPONSE_BYTES = 1024 * 1024


def _other(provider: str) -> str:
    return "tavily" if provider == "exa" else "exa"


class DiscoveryService:
    def __init__(self, engine: "Engine"):
        self.e = engine

    # ------------------------------------------------------------------ configuration (HTTP)
    def _profile_out(self, r: dict) -> CompanyProfileOut:
        return CompanyProfileOut(
            profile_id=r["id"], workspace_id=r["workspace_id"], version=r["version"], display_name=r["display_name"],
            official_domain=r["official_domain"], public_aliases=r["public_aliases"], approved_by=r["approved_by"],
            approved_at=r["approved_at"], privacy_notice_version=r["privacy_notice_version"],
            privacy_notice=identity.PRIVACY_NOTICE)

    def create_profile(self, p: Principal, ws_id: str, body: CompanyProfileIn) -> CompanyProfileOut:
        p.require(ws_id, Capability.configure)
        if self.e.repo.get_workspace(ws_id) is None:
            raise not_found()
        clean = identity.validate_profile(body.display_name, body.official_domain, body.public_aliases)
        if body.profile_id:
            if self.e.repo.get_profile(ws_id, body.profile_id) is None:
                raise not_found()
            pid = body.profile_id
        else:
            pid = new_id("cprof")
        version = self.e.repo.insert_profile_version({
            "id": pid, "workspace_id": ws_id, **clean, "approved_by": p.client_id, "approved_at": iso(now()),
            "privacy_notice_version": identity.PRIVACY_NOTICE_VERSION})
        return self._profile_out(self.e.repo.get_profile(ws_id, pid, version))

    def own_profile(self, ws_id: str) -> dict | None:
        """The approved identity for the workspace's own company (the takedown signer's name), if one exists."""
        rem = self.e.repo.get_remediation_profile(ws_id)
        if not rem:
            return None
        name = " ".join(rem["company_name"].split()).casefold()
        return next((r for r in self.e.repo.list_profiles(ws_id)
                     if not r["id"].startswith("cauto_") and r["display_name"].casefold() == name), None)

    def get_company(self, p: Principal, ws_id: str) -> CompanyOut:
        p.require(ws_id, Capability.read)
        rem = self.e.repo.get_remediation_profile(ws_id)
        own = self.own_profile(ws_id)
        return CompanyOut(name=rem["company_name"] if rem else None, website=own["official_domain"] if own else None,
                          reply_to=rem["reply_to"] if rem else None)

    def put_company(self, p: Principal, ws_id: str, body: CompanyIn) -> CompanyOut:
        """Set the company once: approves its public name for search and signs takedowns with it."""
        p.require(ws_id, Capability.configure)
        if self.e.repo.get_workspace(ws_id) is None:
            raise not_found()
        site = (body.website or "").strip().lower()
        site = site.split("://", 1)[-1].split("/", 1)[0].removeprefix("www.") or None  # accept a pasted URL
        clean = identity.validate_profile(body.name, site, [])
        existing = next((r for r in self.e.repo.list_profiles(ws_id)
                         if not r["id"].startswith("cauto_") and r["display_name"].casefold() == clean["display_name"].casefold()), None)
        if existing is None or existing["official_domain"] != clean["official_domain"]:
            self.e.repo.insert_profile_version({
                "id": existing["id"] if existing else new_id("cprof"), "workspace_id": ws_id, **clean,
                "approved_by": p.client_id, "approved_at": iso(now()), "privacy_notice_version": identity.PRIVACY_NOTICE_VERSION})
        self.e.set_remediation_profile(ws_id, body.name.strip(), body.reply_to.strip())
        return self.get_company(p, ws_id)

    def list_profiles(self, p: Principal, ws_id: str) -> CompanyProfileList:
        p.require(ws_id, Capability.read)
        return CompanyProfileList(items=[self._profile_out(r) for r in self.e.repo.list_profiles(ws_id)])

    def get_profile(self, p: Principal, ws_id: str, profile_id: str) -> CompanyProfileOut:
        p.require(ws_id, Capability.read)
        r = self.e.repo.get_profile(ws_id, profile_id)
        if r is None:
            raise not_found()
        return self._profile_out(r)

    def plan_out(self, r: dict) -> QueryPlanOut:
        plan, prof = r["plan"], r["profile"]
        lim = self.e.settings.limits
        return QueryPlanOut(
            query_plan_id=r["id"], workspace_id=r["workspace_id"], profile_id=r["profile_id"],
            profile_version=r["profile_version"], display_name=prof["display_name"],
            official_domain=prof.get("official_domain"), template_version=plan["template_version"],
            pack=plan.get("pack"), omitted_presets=plan.get("omitted_presets", []),
            searches=plan["searches"], scope=plan["scope"],
            budget={**plan["limits"], "max_unique_pages": lim.max_public_pages,
                    "max_text_per_page": lim.max_public_text_per_page,
                    "max_provider_requests_per_scan": lim.max_provider_requests,
                    "scan_deadline_seconds": lim.scan_deadline_seconds},
            privacy_notice=identity.PRIVACY_NOTICE, created_by=r["created_by"], created_at=r["created_at"])

    def create_plan(self, p: Principal, ws_id: str, body: QueryPlanIn) -> QueryPlanOut:
        p.require(ws_id, Capability.configure)
        prof = self.e.repo.get_profile(ws_id, body.profile_id, body.profile_version)
        if prof is None:
            raise not_found()
        profile = {k: prof[k] for k in ("display_name", "official_domain", "public_aliases")}
        plan = presets.build_plan(profile, body.presets, body.pack, list(body.providers), body.scope.model_dump(),
                                  body.results_per_query, allow_experimental=body.include_experimental)
        rec = {"id": new_id("qplan"), "workspace_id": ws_id, "profile_id": prof["id"], "profile_version": prof["version"],
               "profile": profile, "plan": plan, "created_by": p.client_id, "created_at": iso(now())}
        self.e.repo.insert_query_plan(rec)
        return self.plan_out(self.e.repo.get_query_plan(rec["id"]))

    def preset_catalog(self, p: Principal) -> QueryPresetCatalog:
        return QueryPresetCatalog(**presets.catalog())

    def _plan_in_ws(self, ws_id: str, plan_id: str) -> dict:
        r = self.e.repo.get_query_plan(plan_id)
        if r is None or r["workspace_id"] != ws_id:
            raise not_found()
        return r

    def get_plan(self, p: Principal, ws_id: str, plan_id: str) -> QueryPlanOut:
        p.require(ws_id, Capability.read)
        return self.plan_out(self._plan_in_ws(ws_id, plan_id))

    def list_plans(self, p: Principal, ws_id: str, cursor: str | None, limit: int) -> QueryPlanPage:
        p.require(ws_id, Capability.read)
        limit = max(1, min(limit, self.e.settings.limits.page_size_max))
        rows = self.e.repo.list_query_plans(ws_id, cursor, limit + 1)
        return QueryPlanPage(items=[self.plan_out(r) for r in rows[:limit]],
                             next_cursor=rows[limit - 1]["id"] if len(rows) > limit else None)

    def validate_scan_request(self, ws_id: str, pd) -> None:
        plan = self._plan_in_ws(ws_id, pd.query_plan_id)
        if pd.mode == "snapshot":
            snap = self.e.repo.get_snapshot(pd.snapshot_id or "") if pd.snapshot_id else None
            if snap is None or snap["workspace_id"] != ws_id or snap["manifest_id"] != f"discovery:{plan['id']}":
                raise ApiError(422, "snapshot_required", "snapshot mode requires a saved discovery snapshot for this query plan.")
        elif pd.snapshot_id:
            raise ApiError(422, "snapshot_unexpected", "snapshot_id is only valid with mode 'snapshot'.")

    # ------------------------------------------------------------------ run state
    def _start(self, ctx: "ScanContext", mode: str) -> dict:
        pd = ctx.scan["public_discovery"]
        plan = self.e.repo.get_query_plan(pd["query_plan_id"])
        if plan is None:
            raise RuntimeError("query plan missing")
        run = {"id": new_id("disc"), "workspace_id": ctx.scan["workspace_id"], "scan_id": ctx.scan_id,
               "query_plan_id": plan["id"], "profile_version": plan["profile_version"], "started_at": iso(now()),
               "finished_at": None,
               "data": {"mode": mode, "state": "searching" if mode == "live" else "fetching", "outcome": None,
                        "template_version": plan["plan"]["template_version"],
                        "provider_queries": [{"query_id": q["query_id"], "provider": q["provider"], "query": q["query"],
                                              "template_id": q["template_id"], "include_domains": q["include_domains"],
                                              "num_results": q["num_results"], "status": "pending", "error": None,
                                              "returned": 0, "truncated": False, "searched_at": None, "excess": []}
                                             for q in plan["plan"]["searches"]] if mode == "live" else [],
                        "search_errors": [], "candidates": [], "returned_count": 0, "unique_count": 0,
                        "fetch_attempted_count": 0, "fetched_count": 0, "skipped_count": 0, "truncated": False}}
        ctx.discovery = {"run": run, "sources": [], "plan": plan}
        self._persist(ctx)
        return ctx.discovery

    def _persist(self, ctx: "ScanContext") -> None:
        d = ctx.discovery
        self.e.repo.upsert_discovery_run(d["run"])
        self.e.repo.replace_discovery_sources(d["run"]["id"], ctx.scan_id, d["sources"])
        ctx.summary["discovery"] = self._summary(d)

    @staticmethod
    def _summary(d: dict) -> dict:
        r = d["run"]["data"]
        return {"run_id": d["run"]["id"], "mode": r["mode"], "state": r["state"], "outcome": r["outcome"],
                "searches": len(r["provider_queries"]),
                "searches_ok": sum(q["status"] == "ok" for q in r["provider_queries"]),
                **{k: r[k] for k in ("returned_count", "unique_count", "fetch_attempted_count", "fetched_count",
                                     "skipped_count", "truncated")}}

    def fail(self, ctx: "ScanContext", reason: str) -> None:
        if not getattr(ctx, "discovery", None):
            return
        r = ctx.discovery["run"]
        r["data"]["state"] = "failed"
        r["data"]["outcome"] = r["data"]["outcome"] or reason
        r["finished_at"] = iso(now())
        self._persist(ctx)

    # ------------------------------------------------------------------ stage: public_discovery (search)
    def search(self, ctx: "ScanContext") -> None:
        d = self._start(ctx, "live")
        data, plan, ws_id = d["run"]["data"], d["plan"], ctx.scan["workspace_id"]
        lim = self.e.settings.limits
        # Reserve extraction capacity before issuing searches.
        remaining = lim.max_provider_requests - ctx.budget.get("provider_requests", 0)
        allowed = max(0, remaining - lim.max_public_pages)
        searches = plan["plan"]["searches"]
        runnable = searches[:allowed]
        for q in data["provider_queries"][len(runnable):]:
            q["status"], q["error"] = "skipped", "budget_reserved_for_extraction"
        results: dict[str, dict] = {}
        if runnable:
            req = {"op": "search",
                   "searches": [self._search_entry(q) for q in runnable],
                   "limits": {"max_results": presets.MAX_RESULTS_PER_SEARCH, "max_requests": len(runnable),
                              "concurrency": lim.public_http_concurrency, "max_raw": SEARCH_RESPONSE_BYTES},
                   "deadline_seconds": max(1.0, min(ctx.remaining_seconds() - 5, 60.0))}
            resp = self.e.retrieval.call_worker(ctx, req)
            results = {s["query_id"]: s for s in resp.get("searches", [])}
        by_sid: dict[str, dict] = {}
        for q in data["provider_queries"]:
            r = results.get(q["query_id"])
            if r is None:
                continue
            q.update({"status": r["status"], "error": r.get("error"), "returned": r.get("returned", 0),
                      "truncated": bool(r.get("truncated")), "searched_at": r.get("searched_at"),
                      "excess": [{"rank": x["rank"], "url": x.get("url"), "title": x.get("title")} for x in r.get("excess", [])]})
            if r["status"] != "ok":
                data["search_errors"].append(f"{q['query_id']}:{q['provider']}:{r.get('error')}")
                continue
            data["returned_count"] += r.get("returned", 0)
            data["truncated"] = data["truncated"] or bool(r.get("truncated"))
            for item in r.get("results", []):
                origin = {"query_id": q["query_id"], "provider": q["provider"], "rank": item["rank"],
                          "title": item.get("title"), "returned_url": item.get("url") or ""}
                cand = {**origin, "provider_published_at": item.get("provider_published_at")}
                reason = check_url(item.get("url"))
                if reason:
                    sid = source_id_for(ws_id, "unfetchable:" + str(item.get("url")))
                    cand.update(disposition="blocked", reason=reason, source_id=sid)
                    data["candidates"].append(cand)
                    if sid not in by_sid:
                        by_sid[sid] = self._new_source(sid, item, origin, q["provider"], None)
                        by_sid[sid].update(fetch_status=FetchStatus.blocked.value, failure_reason=reason)
                    else:
                        by_sid[sid]["discovery_origins"].append(origin)
                    continue
                canon = canonicalize(item["url"])
                sid = source_id_for(ws_id, canon)
                if sid in by_sid:
                    by_sid[sid]["discovery_origins"].append(origin)
                    by_sid[sid]["title"] = by_sid[sid]["title"] or item.get("title")
                    cand.update(disposition="duplicate", source_id=sid)
                else:
                    by_sid[sid] = self._new_source(sid, item, origin, q["provider"], canon)
                    cand.update(disposition="source", source_id=sid)
                data["candidates"].append(cand)
        d["sources"] = list(by_sid.values())
        fetchable = [s for s in d["sources"] if s["fetch_status"] == FetchStatus.pending.value]
        data["unique_count"] = len(fetchable)
        ran = [q for q in data["provider_queries"] if q["status"] in ("ok", "failed")]
        ok = [q for q in ran if q["status"] == "ok"]
        if not ran and data["provider_queries"]:
            data["outcome"] = "budget_exhausted"   # nothing was searched, so nothing failed either
        elif not ok:
            data["outcome"] = "search_failed"
        elif not fetchable:
            data["outcome"] = "no_candidates"
        elif len(ok) < len(data["provider_queries"]):
            data["outcome"] = "partial_search"
        else:
            data["outcome"] = "candidates_found"
        data["state"] = "fetching"
        st = next(s for s in ctx.stages if s["name"] == "public_discovery")
        st["detail"] = data["outcome"]
        status = (CoverageStatus.failed if not ok else
                  CoverageStatus.complete if len(ok) == len(data["provider_queries"]) else CoverageStatus.partial)
        ctx.cover("stage", "public_discovery", status, None if status == CoverageStatus.complete else data["outcome"],
                  searches=len(data["provider_queries"]), searches_ok=len(ok), returned=data["returned_count"],
                  unique=len(fetchable))
        self._persist(ctx)

    @staticmethod
    def _search_entry(q: dict) -> dict:
        """Only the stored, rendered plan fields go to the worker. Plans from older template versions lack the v3
        fields and are sent exactly as they were rendered."""
        out = {k: q[k] for k in ("query_id", "provider", "query", "num_results", "include_domains")}
        for k in ("include_domains_mode", "exclude_domains", "category", "topic", "exact_match"):
            if q.get(k) is not None:
                out[k] = q[k]
        return out

    @staticmethod
    def _new_source(sid: str, item: dict, origin: dict, provider: str, canon: str | None) -> dict:
        return {"source_id": sid, "original_url": item.get("url") or "", "canonical_url": canon, "final_url": None,
                "title": item.get("title"), "mode": "discovered", "discovery_origins": [origin],
                "discovery_provider": provider, "extraction_provider": None, "search_rank": origin["rank"],
                "fetch_status": FetchStatus.pending.value, "failure_reason": None, "retrieved_at": None,
                "provider_content_timestamp": item.get("provider_published_at"), "content_hash": None,
                "truncated": False, "comparison_status": ComparisonStatus.not_compared.value, "match_count": 0,
                "freshness": None, "attempts": []}

    # ------------------------------------------------------------------ stage: public_retrieval (extract)
    def fetch(self, ctx: "ScanContext") -> None:
        d = ctx.discovery
        if d is None:
            raise RuntimeError("discovery did not run")
        data = d["run"]["data"]
        lim = self.e.settings.limits
        pending = [s for s in d["sources"] if s["fetch_status"] == FetchStatus.pending.value]
        for s in pending[lim.max_public_pages:]:
            s.update(fetch_status=FetchStatus.skipped_limit.value, failure_reason="page_limit")
        queue = pending[:lim.max_public_pages]
        tried: set[str] = set()
        for attempt in (1, 2):  # primary extraction, then at most one fallback per failed source
            if not queue:
                break
            remaining = lim.max_provider_requests - ctx.budget.get("provider_requests", 0)
            if remaining <= 0:
                for s in queue:
                    if s["fetch_status"] == FetchStatus.pending.value or attempt == 1:
                        s.update(fetch_status=FetchStatus.skipped_limit.value, failure_reason="provider_request_budget")
                break
            batch = []
            for s in queue:
                prov = s["discovery_provider"] if attempt == 1 else _other(s["extraction_provider"] or s["discovery_provider"])
                batch.append({"source_id": s["source_id"], "url": s["canonical_url"], "provider": prov})
            req = self.e.retrieval.build_request(ctx, batch)
            req["limits"]["max_requests"] = remaining
            resp = self.e.retrieval.call_worker(ctx, req)
            res = {r["source_id"]: r for r in resp.get("results", [])}
            retry = []
            for s, b in zip(queue, batch):
                r = res.get(s["source_id"], {"status": "failed", "error": "no_worker_result"})
                tried.add(s["source_id"])
                if r.get("error") in LIMIT_ERRORS:
                    s["attempts"].append({"provider": b["provider"], "status": "skipped", "error": r["error"]})
                    if s["fetch_status"] == FetchStatus.pending.value:
                        s.update(fetch_status=FetchStatus.skipped_limit.value, failure_reason=r["error"])
                    continue
                s["attempts"].append({"provider": b["provider"], "status": r["status"], "error": r.get("error"),
                                      "retrieved_at": r.get("retrieved_at")})
                s["extraction_provider"] = b["provider"]
                s["retrieved_at"] = r.get("retrieved_at")
                if r["status"] == "ok":
                    s.update(fetch_status=FetchStatus.fetched.value, failure_reason=None, final_url=r.get("final_url"),
                             truncated=bool(r.get("truncated")), content_hash=self.e.retrieval.blobs.put(r["text"]),
                             chars=len(r["text"]), freshness="fresh")
                else:
                    s.update(fetch_status=FetchStatus.failed.value, failure_reason=r.get("error") or "failed")
                    retry.append(s)
            queue = retry
        data["fetch_attempted_count"] = len(tried)
        data["fetched_count"] = sum(s["fetch_status"] == FetchStatus.fetched.value for s in d["sources"])
        data["skipped_count"] = sum(s["fetch_status"] == FetchStatus.skipped_limit.value for s in d["sources"])
        self._to_snapshot(ctx, d["sources"], fresh=True)
        data["state"] = "comparing"
        self._persist(ctx)

    def replay(self, ctx: "ScanContext") -> None:
        """Offline replay of a saved discovery snapshot: no search, no network; all content labeled cached."""
        d = self._start(ctx, "snapshot")
        pd = ctx.scan["public_discovery"]
        snap = self.e.repo.get_snapshot(pd["snapshot_id"])
        d["sources"] = [{**{k: v for k, v in s.items() if k not in ("status", "error", "chars", "url")},
                         "original_url": s.get("original_url") or s["url"], "canonical_url": s["url"],
                         "fetch_status": FetchStatus.fetched.value if s.get("status") == "ok" else FetchStatus.failed.value,
                         "failure_reason": s.get("error"), "freshness": "cached",
                         "comparison_status": ComparisonStatus.not_compared.value, "match_count": 0, "chars": s.get("chars", 0)}
                        for s in snap["sources"]]
        d["run"]["data"].update(outcome="snapshot_replay", unique_count=len(d["sources"]),
                                fetched_count=sum(s["fetch_status"] == "fetched" for s in d["sources"]))
        ctx.public_snapshot = {"id": snap["id"], "sources": [{**s, "freshness": "cached"} for s in snap["sources"]]}
        self.e.repo.update_scan(ctx.scan_id, public_snapshot_id=snap["id"])
        ctx.summary["public_freshness"] = (f"cached discovery snapshot from {snap['created_at']}; no live search or "
                                           "retrieval in this scan")
        self._load_texts(ctx)
        d["run"]["data"]["state"] = "comparing"
        self._persist(ctx)

    def _to_snapshot(self, ctx: "ScanContext", sources: list[dict], fresh: bool) -> None:
        run_id = ctx.discovery["run"]["id"]
        entries = []
        for s in sources:
            if s["fetch_status"] not in (FetchStatus.fetched.value, FetchStatus.failed.value):
                continue
            entries.append({"source_id": s["source_id"], "url": s["canonical_url"], "original_url": s["original_url"],
                            "final_url": s.get("final_url"), "title": s.get("title"),
                            "provider": s.get("extraction_provider"), "discovery_provider": s["discovery_provider"],
                            "status": "ok" if s["fetch_status"] == FetchStatus.fetched.value else "failed",
                            "error": s.get("failure_reason"), "retrieved_at": s.get("retrieved_at"),
                            "truncated": s.get("truncated", False), "content_hash": s.get("content_hash"),
                            "chars": s.get("chars", 0), "freshness": "fresh" if fresh else "cached", "mode": "discovered",
                            "discovery_origins": s["discovery_origins"], "discovery_run_id": run_id,
                            "provider_content_timestamp": s.get("provider_content_timestamp")})
        plan_id = ctx.discovery["plan"]["id"]
        snap_id = new_id("snap")
        self.e.repo.insert_snapshot({"id": snap_id, "workspace_id": ctx.scan["workspace_id"],
                                     "manifest_id": f"discovery:{plan_id}",
                                     "manifest_version": ctx.discovery["plan"]["profile_version"],
                                     "sources": entries, "created_at": iso(now())})
        ctx.public_snapshot = {"id": snap_id, "sources": entries}
        self.e.repo.update_scan(ctx.scan_id, public_snapshot_id=snap_id)
        ctx.summary["public_freshness"] = FRESHNESS_NOTE
        self._load_texts(ctx)

    def _load_texts(self, ctx: "ScanContext") -> None:
        ok = 0
        for s in ctx.discovery["sources"]:
            sid, st = s["source_id"], s["fetch_status"]
            if st == FetchStatus.fetched.value:
                text = self.e.retrieval.blobs.read(s["content_hash"]) if s.get("content_hash") else None
                if text is None:
                    s.update(fetch_status=FetchStatus.failed.value, failure_reason="cached_text_unavailable")
                    ctx.cover("source", sid, CoverageStatus.failed, "cached_text_unavailable")
                    continue
                ctx.public_texts[sid] = text
                ok += 1
                ctx.cover("source", sid, CoverageStatus.partial if s.get("truncated") else CoverageStatus.complete,
                          "truncated" if s.get("truncated") else None, chars=len(text))
            elif st == FetchStatus.skipped_limit.value:
                ctx.cover("source", sid, CoverageStatus.not_requested, s.get("failure_reason") or "limit")
            else:
                ctx.cover("source", sid, CoverageStatus.failed,
                          f"{st}:{s.get('failure_reason')}" if st == FetchStatus.blocked.value else s.get("failure_reason"))
        ctx.summary["public_sources_ok"] = ok
        ctx.summary["public_sources_requested"] = len(ctx.discovery["sources"])

    # ------------------------------------------------------------------ stage: public_match (record comparison)
    def coverage_override(self, ctx: "ScanContext", status: CoverageStatus, reason: str | None):
        outcome = ctx.discovery["run"]["data"]["outcome"] if ctx.discovery else None
        if outcome == "search_failed":
            return CoverageStatus.failed, "discovery_search_failed"
        if outcome == "budget_exhausted":
            return CoverageStatus.failed, "discovery_budget_exhausted"
        if outcome == "no_candidates":
            return CoverageStatus.partial, "no_candidate_sources_found"
        if outcome == "partial_search" and status == CoverageStatus.complete:
            return CoverageStatus.partial, "some_searches_failed"
        return status, reason

    def record_comparison(self, ctx: "ScanContext", matches: dict[str, int]) -> None:
        d = ctx.discovery
        if not d:
            return
        for s in d["sources"]:
            sid = s["source_id"]
            s["match_count"] = matches.get(sid, 0)
            if sid not in ctx.public_texts:
                s["comparison_status"] = ComparisonStatus.not_compared.value
            elif s["match_count"]:
                s["comparison_status"] = ComparisonStatus.matched.value
            elif not ctx.docs or s.get("truncated"):
                s["comparison_status"] = ComparisonStatus.incomplete.value  # no match in the retrieved portion only
            else:
                s["comparison_status"] = ComparisonStatus.no_match.value
        d["run"]["data"]["state"] = "done"
        d["run"]["finished_at"] = iso(now())
        self._persist(ctx)

    # ------------------------------------------------------------------ source list (HTTP)
    def _run_out(self, run: dict) -> DiscoveryRunOut:
        r = run["data"]
        return DiscoveryRunOut(
            run_id=run["id"], query_plan_id=run["query_plan_id"], profile_version=run["profile_version"], mode=r["mode"],
            state=r["state"], outcome=r["outcome"], started_at=run["started_at"], finished_at=run["finished_at"],
            provider_queries=[{k: q.get(k) for k in ("query_id", "provider", "query", "status", "error", "returned",
                                                      "truncated", "searched_at")} for q in r["provider_queries"]],
            search_errors=r["search_errors"], returned_count=r["returned_count"], unique_count=r["unique_count"],
            fetch_attempted_count=r["fetch_attempted_count"], fetched_count=r["fetched_count"],
            skipped_count=r["skipped_count"], truncated=r["truncated"], note=RUN_NOTE)

    @staticmethod
    def _source_out(s: dict) -> SourceOut:
        fresh = s.get("freshness")
        return SourceOut(
            source_id=s["source_id"], original_url=s.get("original_url") or s.get("url") or "", final_url=s.get("final_url"),
            title=s.get("title"), mode=s.get("mode", "seeded"), discovery_origins=s.get("discovery_origins") or [],
            discovery_provider=s.get("discovery_provider"), extraction_provider=s.get("extraction_provider") or s.get("provider"),
            search_rank=s.get("search_rank"), fetch_status=s["fetch_status"], failure_reason=s.get("failure_reason"),
            retrieved_at=s.get("retrieved_at"),
            retrieval_note=(FRESHNESS_NOTE if fresh == "fresh" else "Cached content from an earlier scan." if fresh else None),
            provider_content_timestamp=s.get("provider_content_timestamp"), content_hash=s.get("content_hash"),
            truncated=bool(s.get("truncated")), comparison_status=s["comparison_status"], match_count=s.get("match_count", 0),
            freshness=fresh)

    def sources(self, p: Principal, ws_id: str, scan_id: str, cursor: str | None, limit: int) -> SourcePage:
        p.require(ws_id, Capability.read)
        scan = self.e.repo.get_scan(scan_id)
        if scan is None or scan["workspace_id"] != ws_id:
            raise not_found()
        limit = max(1, min(limit, self.e.settings.limits.page_size_max))
        try:
            after = int(cursor) if cursor else -1
        except ValueError:
            raise ApiError(422, "invalid_cursor", "Invalid cursor.")
        run = self.e.repo.discovery_run_for_scan(scan_id)
        if run is not None:
            rows = self.e.repo.discovery_sources(scan_id, after, limit + 1)
            items = [self._source_out(s) for _, s in rows[:limit]]
            nxt = str(rows[limit - 1][0]) if len(rows) > limit else None
            return SourcePage(scan_id=scan_id, discovery=self._run_out(run), items=items, next_cursor=nxt)
        # Seeded/manifest scans: the snapshot is the complete source list.
        snap = self.e.repo.get_snapshot(scan["public_snapshot_id"]) if scan["public_snapshot_id"] else None
        entries = (snap or {}).get("sources", [])
        summary = scan["summary"] or {}
        matches = summary.get("public_source_matches", {})
        compared = {sid for _, sid in summary.get("public_compared", [])}
        recheck_or_manifest = []
        for e in entries:
            ok = e.get("status") == "ok"
            n = matches.get(e["source_id"], 0)
            comp = (ComparisonStatus.matched if n else ComparisonStatus.no_match if e["source_id"] in compared
                    else ComparisonStatus.incomplete if ok and scan["state"] not in ("queued", "running") and
                    "public_source_matches" in summary else ComparisonStatus.not_compared)
            recheck_or_manifest.append({**e, "original_url": e["url"], "mode": e.get("mode", "seeded"),
                                        "fetch_status": FetchStatus.fetched.value if ok else FetchStatus.failed.value,
                                        "failure_reason": e.get("error"), "comparison_status": comp.value,
                                        "match_count": n,
                                        "freshness": "cached" if (scan["public_sources"] or {}).get("mode") == "snapshot"
                                        else e.get("freshness")})
        page = recheck_or_manifest[after + 1: after + 1 + limit]
        nxt = str(after + limit) if after + 1 + limit < len(recheck_or_manifest) else None
        return SourcePage(scan_id=scan_id, discovery=None, items=[self._source_out(x) for x in page], next_cursor=nxt)

