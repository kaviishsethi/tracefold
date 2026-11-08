"""Pydantic request/response DTOs: the one validated contract shared by the app and MCP adapter."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ActionKind,
    ActionStatus,
    Capability,
    Check,
    CoverageStatus,
    Disclosure,
    FindingKind,
    FindingStatus,
    HumanReview,
    Origin,
    PublicMode,
    RecheckOutcome,
    RiskReview,
    ScanState,
)

SCHEMA_VERSION = 1


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool


class ErrorEnvelope(BaseModel):
    error: ErrorBody
    request_id: str


# ---------- capabilities / workspaces ----------

class CapabilitiesOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    engine_version: str
    checks: list[Check]
    supported_inputs: list[str]
    local_risk_rules: list[str]
    model: dict[str, Any]
    limits: dict[str, int]
    client_capabilities: dict[str, list[Capability]]
    remediation: dict[str, str] = {}


class WorkspaceOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    name: str
    source_type: str
    revision: int
    capabilities: list[Capability]
    disclosure: Disclosure
    manifests: list[str]


class WorkspaceList(BaseModel):
    items: list[WorkspaceOut]


# ---------- captures ----------

class CapturedFileOut(BaseModel):
    file_id: str
    path: str | None
    status: Literal["captured", "deleted", "rejected"]
    reason: str | None = None
    size: int | None = None
    kind: str | None = None
    change: str | None = None


class InputOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    input_id: str
    workspace_id: str
    revision: int
    expires_at: str
    baseline: str | None = None
    files: list[CapturedFileOut]
    omitted_context: list[str] = []


class CaptureRequest(Strict):
    mode: Literal["files", "changes"]
    paths: list[str] | None = Field(default=None, max_length=100)
    baseline: str | None = Field(default=None, max_length=200)
    include_untracked: bool = False


# ---------- scans ----------

class PublicSourcesIn(Strict):
    manifest_id: str = Field(max_length=100)
    mode: PublicMode = PublicMode.refresh
    snapshot_id: str | None = Field(default=None, max_length=100)
    source_ids: list[str] | None = Field(default=None, max_length=50)


class ScanRequest(Strict):
    input_id: str = Field(max_length=100)
    checks: list[Check] = Field(min_length=1, max_length=2)
    public_sources: PublicSourcesIn | None = None
    review_profile: Literal["data_exposure_v1"] = "data_exposure_v1"
    model_review: bool = True


class ScanAccepted(BaseModel):
    schema_version: int = SCHEMA_VERSION
    scan_id: str
    state: ScanState
    input_id: str
    status_url: str


class CoverageEntry(BaseModel):
    scope: str  # check | source | file | stage
    id: str
    status: CoverageStatus
    reason: str | None = None
    counts: dict[str, int] = {}


class StageOut(BaseModel):
    name: str
    status: Literal["pending", "running", "done", "failed", "skipped", "cancelled"]
    detail: str | None = None


class ScanOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    scan_id: str
    workspace_id: str
    input_id: str
    state: ScanState
    checks: list[Check]
    recheck_of: str | None = None
    public_snapshot_id: str | None = None
    public_freshness: str | None = None
    stages: list[StageOut]
    coverage: list[CoverageEntry]
    budget: dict[str, int]
    versions: dict[str, str]
    errors: list[ErrorBody]
    summary: dict[str, Any]
    created_at: str
    started_at: str | None
    finished_at: str | None
    deadline_at: str | None


# ---------- findings / evidence ----------

class LocationOut(BaseModel):
    file_id: str
    path: str | None
    start: int
    end: int
    line_start: int | None = None
    line_end: int | None = None
    paragraph_id: str | None = None


class PublicSpanOut(BaseModel):
    source_id: str
    url: str
    start: int
    end: int
    retrieved_at: str | None
    freshness: Literal["fresh", "cached"]
    snapshot_id: str


class EvidenceOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    evidence_id: str
    scan_id: str
    kind: Literal["local_span", "public_match"]
    location: LocationOut
    file_sha256_prefix: str
    public: PublicSpanOut | None = None
    rule_id: str | None = None
    matched_tokens: int | None = None
    segment_coverage: float | None = None
    availability: Literal["available", "evidence_unavailable", "withheld_by_policy"] | None = None
    local_text: str | None = None
    public_text: str | None = None


class ObservationOut(BaseModel):
    observation_id: str
    finding_id: str
    scan_id: str
    input_id: str
    revision: int
    origin: Origin
    check_id: str
    check_version: str
    rule_id: str | None
    title: str
    claim: str | None
    conditions: str | None
    missing_context: str | None
    uncertainty: str | None
    suggested_fix: str | None
    verification_step: str | None
    severity: str | None
    severity_rationale: str | None
    risk_review: RiskReview
    counterevidence: str | None
    model_id: str | None
    prompt_version: str | None
    evidence: list[EvidenceOut]
    created_at: str


class FindingOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    finding_id: str
    workspace_id: str
    kind: FindingKind
    check_id: str
    rule_id: str | None
    status: FindingStatus
    human_review: HumanReview
    human_review_reason: str | None
    version: int
    path: str | None
    first_seen_scan: str
    last_seen_scan: str
    current_revision: int
    latest: ObservationOut | None = None


class FindingPage(BaseModel):
    items: list[FindingOut]
    next_cursor: str | None


class RecheckOut(BaseModel):
    recheck_id: str
    finding_id: str
    observation_id: str
    scan_id: str
    outcome: RecheckOutcome | None
    reason: str | None
    created_at: str


class FindingDetail(FindingOut):
    observations: list[ObservationOut]
    rechecks: list[RecheckOut]


class RecheckRequest(Strict):
    input_id: str = Field(max_length=100)
    observation_id: str | None = Field(default=None, max_length=100)


class RecheckAccepted(BaseModel):
    schema_version: int = SCHEMA_VERSION
    recheck_id: str
    scan_id: str
    state: ScanState
    status_url: str


class ReviewRequest(Strict):
    state: HumanReview
    reason: str | None = Field(default=None, max_length=500)
    expected_version: int


# ---------- ledger ----------

class LedgerEventOut(BaseModel):
    event_id: str
    scan_id: str | None
    destination_category: str
    destination_host: str
    purpose: str
    source_id: str | None
    status: str
    payload_summary: dict[str, Any]
    at: str


class LedgerPage(BaseModel):
    items: list[LedgerEventOut]
    next_cursor: str | None


# ---------- remediation actions ----------

class ActionDelivery(BaseModel):
    method: Literal["email", "form", "none"]
    address: str | None = None        # the host's abuse/legal email, when method=email
    form_url: str | None = None       # the host's own removal form, when method=form
    transport: str | None = None      # outbox | resend (email only)


class ActionOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    action_id: str
    workspace_id: str
    finding_id: str
    kind: ActionKind
    status: ActionStatus
    version: int
    summary: str
    target: dict[str, Any]
    delivery: ActionDelivery | None = None
    subject: str | None = None
    body: str | None = None          # rendered preview: company filled in, signature (or placeholder) appended
    draft_body: str | None = None    # raw editable text for PATCH: keeps the {company} token, no signature
    approver: dict[str, Any] | None = None
    approved_at: str | None = None
    executed_at: str | None = None
    result: dict[str, Any] = {}
    removal_observed: bool | None = None
    created_at: str
    updated_at: str


class ActionPage(BaseModel):
    items: list[ActionOut]
    next_cursor: str | None


class ApproverIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    title: str | None = Field(default=None, max_length=120)


class ApproveRequest(Strict):
    approver: ApproverIn
    attest_authorized: bool
    expected_version: int


class RejectRequest(Strict):
    reason: str = Field(min_length=1, max_length=500)
    expected_version: int


class EditActionRequest(Strict):
    """Edit an unsent takedown. ``body`` replaces the draft text (ActionOut.draft_body), not the rendered preview:
    keep the {company} token and leave the signature off; both are added when the letter is rendered and sent."""
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, min_length=1, max_length=5000)
    expected_version: int


class MarkSubmittedRequest(Strict):
    note: str | None = Field(default=None, max_length=500)
    expected_version: int
