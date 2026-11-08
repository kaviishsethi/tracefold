"""Pydantic request/response DTOs: the one validated contract shared by the app and MCP adapter."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ActionKind,
    ActionStatus,
    Capability,
    Check,
    ComparisonStatus,
    FetchStatus,
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


class ManifestSourceOut(BaseModel):
    source_id: str
    url: str
    provider: str
    mode: Literal["seeded", "discovered"]


class ManifestOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    manifest_id: str
    version: int
    sources: list[ManifestSourceOut]
    outbound_note: str


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


# ---------- company discovery ----------

class CompanyProfileIn(Strict):
    display_name: str = Field(min_length=2, max_length=80)
    official_domain: str | None = Field(default=None, max_length=253)
    public_aliases: list[str] = Field(default_factory=list, max_length=2)
    confirm_public: Literal[True] = Field(
        description="Confirms this identity is public and may be sent to the selected search providers.")
    profile_id: str | None = Field(default=None, max_length=100, description="Revise an existing profile (new version).")


class CompanyIn(Strict):
    """The workspace's own company: searched for in every public check and used to sign takedown requests."""
    name: str = Field(min_length=2, max_length=80)
    website: str | None = Field(default=None, max_length=253)
    reply_to: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    industry: Literal["financial", "healthcare", "government", "retail", "technology"] | None = None


class ScheduleIn(Strict):
    """Re-run a scan on a schedule. ``scan_id`` re-checks that scan's uploaded files; omit it to re-check the
    registered folder's uncommitted changes."""
    scan_id: str | None = Field(default=None, max_length=100)
    every: Literal["hour", "day", "week"] | None = None
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000, description="Exact interval; overrides every.")
    start_at: str | None = Field(default=None, max_length=40, description="ISO 8601 time of the first run; default one interval from now.")
    public: bool = True
    name: str | None = Field(default=None, max_length=120)


class SchedulePatch(Strict):
    enabled: bool | None = None
    every: Literal["hour", "day", "week"] | None = None
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000)
    start_at: str | None = Field(default=None, max_length=40)
    run_now: bool = False


class SitesIn(Strict):
    """Pages checked in every public scan, and hosts that are never fetched (subdomains included)."""
    always_check: list[str] = Field(default_factory=list, max_length=20)
    never_fetch: list[str] = Field(default_factory=list, max_length=50)


class SitesOut(BaseModel):
    always_check: list[str] = Field(default_factory=list)
    never_fetch: list[str] = Field(default_factory=list)


class CompanyOut(BaseModel):
    name: str | None = None
    website: str | None = None
    reply_to: str | None = None
    industry: str | None = None


class CompanyProfileOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    profile_id: str
    workspace_id: str
    version: int
    display_name: str
    official_domain: str | None
    public_aliases: list[str]
    approved_by: str
    approved_at: str
    privacy_notice_version: str
    privacy_notice: str


class CompanyProfileList(BaseModel):
    items: list[CompanyProfileOut]


class QueryScopeIn(Strict):
    mode: Literal["broad", "selected"] = "broad"
    site_groups: list[str] = Field(default_factory=list, max_length=6)
    exclude_official_domain: bool = Field(default=True, description="Leave the company's own site out of results.")
    exclude_noise: bool = Field(default=True, description="Leave the versioned noise-domain list out of results.")


class QueryPlanIn(Strict):
    """Exactly one of `presets` or `pack`."""
    profile_id: str = Field(max_length=100)
    profile_version: int | None = None
    presets: list[str] | None = Field(default=None, min_length=1, max_length=8)
    pack: str | None = Field(default=None, max_length=50)
    providers: list[Literal["exa", "tavily"]] = Field(default_factory=lambda: ["exa", "tavily"], min_length=1, max_length=2)
    scope: QueryScopeIn = Field(default_factory=QueryScopeIn)
    results_per_query: int | None = Field(default=None, ge=1, le=5, description="Default: the budget shape's maximum.")
    include_experimental: bool = Field(default=False, description="Let a pack use presets without a benchmark target yet.")


class PlannedSearchOut(BaseModel):
    query_id: str
    template_id: str
    provider: str
    query: str
    num_results: int
    include_domains: list[str] | None
    include_domains_mode: str | None = None
    exclude_domains: list[str] | None = None
    category: str | None = None
    topic: str | None = None
    exact_match: bool | None = None
    preset_status: str | None = None


class QueryPlanOut(BaseModel):
    schema_version: int = SCHEMA_VERSION
    query_plan_id: str
    workspace_id: str
    profile_id: str
    profile_version: int
    display_name: str
    official_domain: str | None
    template_version: str
    pack: str | None = None
    omitted_presets: list[dict[str, str]] = []
    searches: list[PlannedSearchOut]
    scope: dict[str, Any]
    budget: dict[str, Any]
    privacy_notice: str
    created_by: str
    created_at: str


class QueryPresetCatalog(BaseModel):
    schema_version: int = SCHEMA_VERSION
    template_version: str
    noise_domains_version: str
    benchmark_version: str
    noise_domains: list[str]
    site_groups: dict[str, list[str]]
    presets: list[dict[str, Any]]
    packs: list[dict[str, Any]]
    shapes: dict[str, dict[str, int]]


class QueryPlanPage(BaseModel):
    items: list[QueryPlanOut]
    next_cursor: str | None


class DiscoveryOriginOut(BaseModel):
    query_id: str
    provider: str
    rank: int
    title: str | None
    returned_url: str


class ProviderQueryOut(BaseModel):
    query_id: str
    provider: str
    query: str
    status: Literal["pending", "ok", "failed", "skipped"]
    error: str | None = None
    returned: int = 0
    truncated: bool = False
    searched_at: str | None = None


class DiscoveryRunOut(BaseModel):
    run_id: str
    query_plan_id: str
    profile_version: int
    mode: Literal["live", "snapshot"]
    state: Literal["searching", "fetching", "comparing", "done", "failed"]
    outcome: str | None
    started_at: str
    finished_at: str | None
    provider_queries: list[ProviderQueryOut]
    search_errors: list[str]
    returned_count: int
    unique_count: int
    fetch_attempted_count: int
    fetched_count: int
    skipped_count: int
    truncated: bool
    note: str


class SourceOut(BaseModel):
    source_id: str
    original_url: str
    final_url: str | None = None
    title: str | None = None
    mode: Literal["seeded", "discovered"]
    discovery_origins: list[DiscoveryOriginOut] = []
    discovery_provider: str | None = None
    extraction_provider: str | None = None
    search_rank: int | None = None
    fetch_status: FetchStatus
    failure_reason: str | None = None
    retrieved_at: str | None = None
    retrieval_note: str | None = None
    provider_content_timestamp: str | None = None
    content_hash: str | None = None
    truncated: bool = False
    comparison_status: ComparisonStatus
    match_count: int = 0
    freshness: Literal["fresh", "cached"] | None = None


class SourcePage(BaseModel):
    schema_version: int = SCHEMA_VERSION
    scan_id: str
    discovery: DiscoveryRunOut | None
    items: list[SourceOut]
    next_cursor: str | None


# ---------- scans ----------

class PublicSourcesIn(Strict):
    manifest_id: str = Field(max_length=100)
    mode: PublicMode = PublicMode.refresh
    snapshot_id: str | None = Field(default=None, max_length=100)
    source_ids: list[str] | None = Field(default=None, max_length=50)


class PublicDiscoveryIn(Strict):
    """Select an already approved query plan. No company name, query or document-derived field is accepted."""
    query_plan_id: str = Field(max_length=100)
    mode: Literal["live", "snapshot"] = "live"
    snapshot_id: str | None = Field(default=None, max_length=100)


class ScanRequest(Strict):
    input_id: str = Field(max_length=100)
    checks: list[Check] = Field(min_length=1, max_length=2)
    public_sources: PublicSourcesIn | None = None
    public_discovery: PublicDiscoveryIn | None = None
    automatic_discovery: bool = False
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
    public_discovery: dict[str, Any] | None = None
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
    initiated_by: str | None = None          # name of the client that started the scan
    started_from: Literal["assistant", "app", "other"] = "other"


class ScanList(BaseModel):
    items: list[ScanOut]
    next_cursor: str | None


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
    mode: Literal["seeded", "discovered"] = "seeded"
    provider: str | None = None
    discovery_run_id: str | None = None
    discovery_origins: list[DiscoveryOriginOut] | None = None


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
    # [start, end) of the matched passage inside local_text / public_text, for highlighting
    local_highlight: list[int] | None = None
    public_highlight: list[int] | None = None


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
    """Approving needs the ``approve`` capability, which only the company's own app token holds. ``approver`` is optional:
    without it the action is recorded against that client and takedowns are signed with the company name and reply-to."""
    approver: ApproverIn | None = None
    attest_authorized: bool = True
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
