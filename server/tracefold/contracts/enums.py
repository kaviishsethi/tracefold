from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover
        return self.value


class ScanState(StrEnum):
    queued = "queued"
    running = "running"
    completed = "completed"
    partial = "partial"
    failed = "failed"
    cancelled = "cancelled"
    interrupted = "interrupted"


TERMINAL_STATES = {ScanState.completed, ScanState.partial, ScanState.failed, ScanState.cancelled, ScanState.interrupted}


class Check(StrEnum):
    public_match = "public_match"
    local_risk = "local_risk"


class Capability(StrEnum):
    submit = "submit"
    read = "read"
    read_evidence = "read_evidence"
    recheck = "recheck"
    cancel = "cancel"
    review = "review"
    approve = "approve"  # approve or reject remediation actions (takedowns, credential disabling)


class Disclosure(StrEnum):
    full = "full"        # paths and evidence snippets allowed (strict-private local host)
    minimal = "minimal"  # opaque IDs, no paths/snippets (e.g. cloud-backed assistant)


class CoverageStatus(StrEnum):
    complete = "complete"
    partial = "partial"
    failed = "failed"
    not_requested = "not_requested"


class FindingKind(StrEnum):
    public_exposure = "public_exposure"
    local_risk = "local_risk"


class FindingStatus(StrEnum):
    open = "open"
    not_detected_in_checked_version = "not_detected_in_checked_version"
    no_longer_observed = "no_longer_observed"


class RiskReview(StrEnum):
    supported = "supported"
    inconclusive = "inconclusive"
    dismissed = "dismissed"
    unavailable = "unavailable"
    not_requested = "not_requested"


class HumanReview(StrEnum):
    unreviewed = "unreviewed"
    acknowledged = "acknowledged"
    dismissed = "dismissed"


class RecheckOutcome(StrEnum):
    still_detected = "still_detected"
    not_detected_in_checked_version = "not_detected_in_checked_version"
    inconclusive = "inconclusive"


class Origin(StrEnum):
    rule = "rule"
    model = "model"
    matcher = "matcher"


class PublicMode(StrEnum):
    refresh = "refresh"
    snapshot = "snapshot"


class ActionKind(StrEnum):
    takedown_request = "takedown_request"
    disable_aws_key = "disable_aws_key"


class ActionStatus(StrEnum):
    drafted = "drafted"                                    # waiting for a person to approve
    awaiting_manual_submission = "awaiting_manual_submission"  # approved; host only accepts its own web form
    executing = "executing"
    submitted = "submitted"                                # takedown sent (or marked sent); not the same as removed
    completed = "completed"                                # credential disabled
    failed = "failed"                                      # may be approved again
    rejected = "rejected"
