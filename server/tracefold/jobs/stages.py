"""Stage implementations used by the pipeline."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..checks import matcher
from ..checks.rules import RULES_VERSION, check_version, gitleaks_hits, run_rules
from ..contracts.enums import Check, CoverageStatus, FindingKind, FindingStatus, Origin, RiskReview
from ..parsing import PARSER_VERSION
from ..parsing.document import ParsedDoc, parse_text
from .model import Proposed

if TYPE_CHECKING:
    from .pipeline import ScanContext


def versions(engine=None) -> dict[str, str]:
    v = {"parser": PARSER_VERSION, "normalization": matcher.NORMALIZATION_VERSION, "matcher": matcher.MATCHER_VERSION,
         "rules": RULES_VERSION}
    if engine is not None:
        v["secret_scanner"] = engine.secret_scanner.check_version()
    return v


def _scope_files(ctx: "ScanContext"):
    """Files in scope: all captured files, or only the recheck target's file."""
    files = ctx.capture.files
    scope = ctx.summary.get("scope_paths")
    if scope:
        files = [f for f in files if f.path in scope]
    return files


def parse_stage(ctx: "ScanContext") -> None:
    files = _scope_files(ctx)
    if ctx.summary.get("scope_paths") and not files:
        ctx.summary["scope_missing"] = True
    for f in files:
        ctx.checkpoint()
        if f.status == "rejected":
            ctx.cover("file", f.file_id, CoverageStatus.failed, f.reason or "rejected")
            continue
        if f.status == "deleted":
            ctx.cover("file", f.file_id, CoverageStatus.not_requested, "deleted_in_working_tree")
            continue
        try:
            if f.kind == "docx":
                from ..parsing.docx import parse_docx
                doc = parse_docx(f, ctx.engine.settings.limits)
            else:
                doc = parse_text(f)
        except Exception as ex:  # parser errors are per-file coverage, never a clean result
            reason = getattr(ex, "reason", None) or "parse_error"
            ctx.cover("file", f.file_id, CoverageStatus.failed, reason)
            continue
        ctx.docs.append(doc)
        ctx.cover("file", f.file_id, CoverageStatus.complete, None, chars=len(doc.text))
    ctx.summary["files_parsed"] = len(ctx.docs)


# ---------------- public exposure ----------------
def public_discovery_stage(ctx: "ScanContext") -> None:
    """Search the approved public query plan. Inputs come only from the stored plan, never from ctx.docs."""
    if (ctx.scan.get("public_discovery") or {}).get("automatic"):
        from ..discovery.automatic import prepare
        if not prepare(ctx):
            return
    ctx.engine.discovery.search(ctx)


def public_retrieval_stage(ctx: "ScanContext") -> None:
    pd = ctx.scan.get("public_discovery")
    if pd and pd.get("automatic") and not pd.get("query_plan_id"):
        return
    if pd and pd.get("mode") == "snapshot":
        ctx.engine.discovery.replay(ctx)
    elif pd:
        ctx.engine.discovery.fetch(ctx)
    else:
        ctx.engine.retrieval.run(ctx)


def _doc_location(doc: ParsedDoc, start: int, end: int) -> dict:
    return doc.location(start, end)


def public_match_stage(ctx: "ScanContext") -> None:
    if (ctx.scan.get("public_discovery") or {}).get("automatic") and not ctx.scan["public_discovery"].get("query_plan_id"):
        return  # retain the actual identity failure; zero sources is not a completed public check
    snap = ctx.public_snapshot or {"id": None, "sources": []}
    by_id = {s["source_id"]: s for s in snap["sources"]}
    found = 0
    skipped = 0
    compared: list[tuple[str, str]] = []  # (path, source_id) pairs with complete comparison
    per_source: dict[str, int] = {}
    for doc in ctx.docs:
        policy = matcher.policy_for(doc.kind)
        for sid, text in ctx.public_texts.items():
            ctx.checkpoint()
            src = by_id[sid]
            res = matcher.find_matches(doc.text, text, policy)
            skipped += res.boilerplate_skipped
            if not src.get("truncated"):
                compared.append((doc.file.path, sid))
            for m in res.matches:
                found += 1
                per_source[sid] = per_source.get(sid, 0) + 1
                loc = _doc_location(doc, m.local_start, m.local_end)
                cov = matcher.segment_coverage(doc.text, m, policy)
                ev = {
                    "kind": "public_match", "location": loc, "file_sha256": doc.file.sha256, "file_kind": doc.kind,
                    "public": {"source_id": sid, "url": src["url"], "start": m.public_start, "end": m.public_end,
                               "retrieved_at": src.get("retrieved_at"), "freshness": src.get("freshness", "fresh"),
                               "snapshot_id": snap["id"], "mode": src.get("mode", "seeded"),
                               "provider": src.get("provider"), "discovery_run_id": src.get("discovery_run_id"),
                               "discovery_origins": src.get("discovery_origins")},
                    "public_blob": src.get("content_hash"), "matched_tokens": m.tokens, "segment_coverage": cov,
                    "normalization": policy,
                }
                fresh = src.get("freshness", "fresh") == "fresh"
                ctx.candidates.append(Proposed(
                    kind=FindingKind.public_exposure.value, check_id=Check.public_match.value,
                    check_version=matcher.MATCHER_VERSION, rule_id=None, origin=Origin.matcher.value, file=doc.file,
                    anchor=_anchor_hash(m.normalized),
                    title="Matching content found publicly" if fresh else "Matching content in cached public evidence",
                    evidence=[ev], source_id=sid,
                    claim=f"{m.tokens} contiguous normalized tokens ({int(cov * 100)}% of the local passage) match text "
                          f"{'retrieved' if fresh else 'cached'} from the approved source {sid}.",
                    conditions="The overlap was observed at the cited URL at the retrieval time shown.",
                    uncertainty="Overlap does not establish who published the content or whether publication was authorized."
                                + ("" if fresh else " This is cached evidence, not a verified current page."),
                    suggested_fix="Confirm whether this publication was authorized. If not: restrict or remove the public copy, "
                                  "contact the host or owner, investigate how it was published, then recheck the source.",
                    verification_step="Run a fresh public recheck of this source; only a successful fresh retrieval without the "
                                      "passage can show it is no longer observed at this URL.",
                    severity="high" if cov >= 0.5 else "medium",
                    severity_rationale="Based on the share of the local passage reproduced publicly; business sensitivity "
                                       "requires human context.",
                    meta={"fresh": fresh},
                ))
    ctx.summary["public_matches"] = found
    ctx.summary["boilerplate_skipped"] = skipped
    ctx.summary["public_compared"] = compared
    ctx.summary["public_source_matches"] = per_source
    req = ctx.summary.get("public_sources_requested", 0)
    ok = ctx.summary.get("public_sources_ok", 0)
    if req == 0 or ok == 0:
        status, reason = CoverageStatus.failed, "no_public_source_retrieved"
    elif ok < req or any(c["scope"] == "source" and c["status"] != "complete" for c in ctx.coverage):
        status, reason = CoverageStatus.partial, "some_sources_failed_or_truncated"
    else:
        status, reason = CoverageStatus.complete, None
    if ctx.discovery:
        status, reason = ctx.engine.discovery.coverage_override(ctx, status, reason)
    if not ctx.docs:
        status, reason = CoverageStatus.failed, "no_parsed_input"
    if ctx.discovery:
        ctx.engine.discovery.record_comparison(ctx, per_source)
    ctx.cover("check", Check.public_match.value, status, reason, sources_ok=ok, sources_requested=req, matches=found,
              boilerplate_skipped=skipped)


def _anchor_hash(normalized: str) -> str:
    from ..util import sha256
    return sha256("passage:" + normalized)


# ---------------- local risk ----------------
def local_rules_stage(ctx: "ScanContext") -> None:
    rule_notes: dict[str, list[str]] = {}
    n_hits = 0
    scanner = ctx.engine.secret_scanner
    gl_version = scanner.check_version()
    gl_failed = False      # Gitleaks was expected (configured or required) but did not complete for a file
    gl_counts = {"files": 0, "leads": 0, "unlocated": 0}
    gl_skipped: set[str] = set()   # Gitleaks off or not installed in a mode where it is optional
    for doc in ctx.docs:
        ctx.checkpoint()
        hits, notes = run_rules(doc)
        res = scanner.scan_text(doc.text)
        if res.status == "ok":
            gl_counts["files"] += 1
            extra, unlocated = gitleaks_hits(doc, res.leaks, hits)
            gl_counts["leads"] += len(res.leaks)
            gl_counts["unlocated"] += unlocated
            hits += extra
            if unlocated:
                notes["gitleaks_secret"] = "gitleaks_lead_not_located"
        elif res.status in ("off", "unavailable") and scanner.mode != "required":
            gl_skipped.add(res.reason or res.status)
        else:
            notes["gitleaks_secret"] = res.reason or res.status
            if res.status == "failed" or scanner.mode == "required":
                gl_failed = True
        del res
        for rid, why in notes.items():
            rule_notes.setdefault(rid, []).append(why)
        for h in hits:
            n_hits += 1
            ev = {"kind": "local_span", "location": doc.location(h.start, h.end), "file_sha256": doc.file.sha256,
                  "file_kind": doc.kind, "rule_id": h.rule_id, "mask_spans": h.mask_spans}
            ctx.candidates.append(Proposed(
                kind=FindingKind.local_risk.value, check_id=Check.local_risk.value,
                check_version=check_version(h.rule_id, gl_version), rule_id=h.rule_id,
                origin=Origin.rule.value, file=doc.file, anchor=h.anchor, title=h.title, evidence=[ev],
                claim=h.claim, conditions=h.conditions, missing_context=h.missing_context, uncertainty=h.uncertainty,
                suggested_fix=h.suggested_fix, verification_step=h.verification_step, severity=h.severity,
                severity_rationale=h.severity_rationale, secret_values=h.secret_values,
                risk_review=RiskReview.not_requested.value, meta={**h.meta, "start": h.start, "end": h.end},
            ))
    for rid, whys in rule_notes.items():
        ctx.cover("rule", rid, CoverageStatus.partial, ",".join(sorted(set(whys))), files=len(whys))
    if gl_skipped and "gitleaks_secret" not in rule_notes:
        ctx.cover("rule", "gitleaks_secret", CoverageStatus.not_requested, ",".join(sorted(gl_skipped)))
    ctx.summary["secret_scanner"] = {"mode": scanner.mode, "version": gl_version, **gl_counts}
    file_failed = any(c["scope"] == "file" and c["status"] == "failed" for c in ctx.coverage)
    syntax = any("python_syntax_error" in w for w in rule_notes.get("py_sensitive_logging", []))
    if not ctx.docs:
        ctx.cover("check", Check.local_risk.value, CoverageStatus.failed, "no_parsed_input")
    elif file_failed or syntax or gl_failed:
        reason = ("some_files_not_reviewed" if file_failed else "python_syntax_error" if syntax
                  else "secret_scanner_incomplete")
        ctx.cover("check", Check.local_risk.value, CoverageStatus.partial, reason, hits=n_hits)
    else:
        ctx.cover("check", Check.local_risk.value, CoverageStatus.complete, None, hits=n_hits, files=len(ctx.docs))
    ctx.summary["local_rule_hits"] = n_hits


def model_review_stage(ctx: "ScanContext") -> None:
    ctx.engine.reviewer.review(ctx)


# ---------------- failure handling ----------------
def on_stage_failure(ctx: "ScanContext", name: str) -> None:
    if name in ("public_discovery", "public_retrieval", "public_match"):
        ctx.cover("check", Check.public_match.value, CoverageStatus.failed, f"{name}_failed")
        ctx.engine.discovery.fail(ctx, f"{name}_failed")
    elif name == "local_rules":
        ctx.cover("check", Check.local_risk.value, CoverageStatus.failed, "local_rules_failed")
    elif name == "model_review":
        for p in ctx.candidates:
            if p.kind == FindingKind.local_risk.value and p.origin == Origin.rule.value:
                p.risk_review = RiskReview.unavailable.value
        ctx.cover("stage", "model_review", CoverageStatus.failed, "model_review_failed")
    elif name == "parse":
        for chk in ctx.checks:
            ctx.cover("check", chk, CoverageStatus.failed, "parse_failed")


def on_deadline(ctx: "ScanContext") -> None:
    for chk in ctx.checks:
        cur = next((c for c in ctx.coverage if c["scope"] == "check" and c["id"] == chk), None)
        if cur is None or cur["status"] != CoverageStatus.complete.value:
            ctx.cover("check", chk, CoverageStatus.partial if ctx.candidates else CoverageStatus.failed, "deadline_exceeded")


# ---------------- publication ----------------
def publish_stage(ctx: "ScanContext") -> None:
    from ..analysis.validate import validate_candidates
    kept, rejected = validate_candidates(ctx)
    ctx.candidates = kept
    if rejected:
        ctx.summary["rejected_candidates"] = rejected
    published = ctx.engine.store.publish(ctx.scan, ctx.candidates)
    ctx.summary["observations"] = len(published)
    try:  # draft takedowns / key-disable actions for a person to approve; never executes anything
        ctx.summary["actions_drafted"] = ctx.engine.remediation.draft_for_scan(ctx, published)
    except Exception as ex:  # drafting must never cost the scan its findings
        import logging
        logging.getLogger("tracefold.remediation").error("drafting failed: %s", type(ex).__name__)
        ctx.summary["actions_drafted"] = "failed"
    ctx.summary["published"] = [{"finding_id": f, "observation_id": o} for f, o in published]
    _update_public_absence(ctx, {f for f, _ in published})


def _update_public_absence(ctx: "ScanContext", detected: set[str]) -> None:
    """A fresh, successful, complete comparison that no longer contains a previously observed passage may mark
    that occurrence 'no longer observed at this URL'. Failures, truncation and cached snapshots never do."""
    if Check.public_match.value not in ctx.checks or not ctx.public_snapshot:
        return
    if ctx.scan.get("public_discovery"):
        # Search results change; omission or re-observation through discovery never resolves an exposure.
        # Only an explicit recheck of the cited URL can.
        return
    fresh_ok = {s["source_id"] for s in ctx.public_snapshot["sources"]
                if s.get("freshness") == "fresh" and s.get("status") == "ok" and not s.get("truncated")}
    compared = {tuple(x) for x in ctx.summary.get("public_compared", [])}
    store, repo = ctx.engine.store, ctx.engine.repo
    for f in repo.open_findings(ctx.scan["workspace_id"], FindingKind.public_exposure.value):
        if f["id"] in detected:
            continue
        obs = repo.observations_for_finding(f["id"])
        sid = obs[-1]["data"].get("source_id") if obs else None
        if sid in fresh_ok and (f["path"], sid) in compared:
            store.set_status(f["id"], FindingStatus.no_longer_observed, ctx.scan["revision"], allow_equal=True)


def after_scan(ctx: "ScanContext", final) -> None:
    if ctx.discovery and ctx.discovery["run"]["data"]["state"] not in ("done", "failed"):
        ctx.engine.discovery.fail(ctx, f"scan_{final.value}")
    if ctx.scan.get("recheck_id"):
        from ..services.rechecks import resolve_recheck
        resolve_recheck(ctx, final)
