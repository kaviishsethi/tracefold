"""Recheck resolution.

A recheck references an old observation and runs the same check/version over the finding's file in a new
capture. Only complete, equivalent coverage can produce ``not_detected_in_checked_version``; anything
missing, deleted, unsupported, truncated or differently versioned is ``inconclusive``. A local recheck never
touches public-exposure findings, and a stale revision cannot clear a newer detection.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..contracts.enums import Check, CoverageStatus, FindingKind, FindingStatus, RecheckOutcome, ScanState

if TYPE_CHECKING:
    from ..jobs.pipeline import ScanContext


def _outcome(ctx: "ScanContext", final: ScanState) -> tuple[RecheckOutcome, str]:
    repo = ctx.engine.repo
    rc = repo.get_recheck(ctx.scan["recheck_id"])
    f = repo.get_finding(rc["finding_id"])
    target = repo.get_observation(rc["observation_id"]) if rc["observation_id"] else None
    files = [x for x in ctx.capture.files if x.path == f["path"]]
    if not files:
        return RecheckOutcome.inconclusive, "file_not_in_capture"
    cf = files[0]
    if cf.status == "deleted":
        return RecheckOutcome.inconclusive, "file_deleted_removal_check_not_supported"
    if final in (ScanState.failed, ScanState.cancelled, ScanState.interrupted):
        return RecheckOutcome.inconclusive, f"scan_{final.value}"
    if cf.status != "captured" or not any(d.file.file_id == cf.file_id for d in ctx.docs):
        return RecheckOutcome.inconclusive, f"file_not_reviewed:{cf.reason or 'parse_failed'}"
    check = f["check_id"]
    cov = next((c for c in ctx.coverage if c["scope"] == "check" and c["id"] == check), None)
    if cov is None or cov["status"] != CoverageStatus.complete.value:
        return RecheckOutcome.inconclusive, f"incomplete_coverage:{cov['reason'] if cov else 'missing'}"
    if f["kind"] == FindingKind.local_risk.value:
        rule_cov = next((c for c in ctx.coverage if c["scope"] == "rule" and c["id"] == f["rule_id"]), None)
        if rule_cov is not None:
            return RecheckOutcome.inconclusive, f"rule_not_fully_applied:{rule_cov['reason']}"
    published = [(x["finding_id"], x["observation_id"]) for x in ctx.summary.get("published", [])]
    # Equivalent check version.
    if target is not None:
        old_ver = target["data"]["check_version"]
        from ..checks import matcher
        from ..checks.rules import RULES, RULES_VERSION
        if f["kind"] == FindingKind.local_risk.value and f["rule_id"] in RULES:
            new_ver = f"{RULES_VERSION}/{f['rule_id']}@{RULES[f['rule_id']].version}"
        else:
            new_ver = matcher.MATCHER_VERSION
        if old_ver != new_ver:
            return RecheckOutcome.inconclusive, "check_version_changed"
    if any(fid == f["id"] for fid, _ in published):
        return RecheckOutcome.still_detected, "same_evidence_anchor_detected"
    if f["kind"] == FindingKind.local_risk.value:
        # Conservative attribution: a new hit of the same rule in the same file that is not another known
        # finding may be this issue in edited form, so it is not reported as cleared.
        for fid, _ in published:
            other = repo.get_finding(fid)
            if other and other["rule_id"] == f["rule_id"] and other["path"] == f["path"] and other["first_seen_scan"] == ctx.scan_id:
                return RecheckOutcome.still_detected, "same_rule_detected_at_changed_location"
    else:
        sid = target["data"].get("source_id") if target else None
        src = next((s for s in (ctx.public_snapshot or {}).get("sources", []) if s["source_id"] == sid), None)
        if not src or src.get("status") != "ok" or src.get("freshness") != "fresh" or src.get("truncated"):
            return RecheckOutcome.inconclusive, "public_source_not_freshly_retrieved"
    return RecheckOutcome.not_detected_in_checked_version, "not_detected_with_equivalent_coverage"


def resolve_recheck(ctx: "ScanContext", final: ScanState) -> None:
    repo = ctx.engine.repo
    outcome, reason = _outcome(ctx, final)
    if outcome == RecheckOutcome.not_detected_in_checked_version:
        rc = repo.get_recheck(ctx.scan["recheck_id"])
        f = repo.get_finding(rc["finding_id"])
        new_status = (FindingStatus.no_longer_observed if f["kind"] == FindingKind.public_exposure.value
                      else FindingStatus.not_detected_in_checked_version)
        allow_equal = f["kind"] == FindingKind.public_exposure.value
        if not ctx.engine.store.set_status(f["id"], new_status, ctx.scan["revision"], allow_equal=allow_equal):
            if repo.get_finding(f["id"])["status"] != new_status.value:
                reason = "stale_revision_newer_capture_owns_current_status"
    repo.update_recheck(ctx.scan["recheck_id"], outcome.value, reason)
    ctx.summary["recheck"] = {"recheck_id": ctx.scan["recheck_id"], "outcome": outcome.value, "reason": reason}
    repo.update_scan(ctx.scan_id, summary=ctx.summary)


__all__ = ["resolve_recheck", "Check"]
