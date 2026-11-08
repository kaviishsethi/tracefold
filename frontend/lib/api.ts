// Typed client for the Tracefold engine (/v1, docs/ENGINE_API.md).
// The browser never holds the engine token: requests go to /api/engine/*, a same-origin proxy that adds it server-side.
// Render what the engine returns. Never invent "safe" or "fixed".
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export const ENGINE = "/api/engine";

// ---------- vocabulary (mirrors server/tracefold/contracts/enums.py) ----------
export type Capability = "submit" | "read" | "read_evidence" | "recheck" | "cancel" | "review" | "approve" | "configure";
export type Disclosure = "full" | "minimal";
export type Check = "public_match" | "local_risk";
export type ScanState = "queued" | "running" | "completed" | "partial" | "failed" | "cancelled" | "interrupted";
export type CoverageStatus = "complete" | "partial" | "failed" | "not_requested";
export type FindingKind = "public_exposure" | "local_risk";
export type FindingStatus = "open" | "not_detected_in_checked_version" | "no_longer_observed";
export type HumanReview = "unreviewed" | "acknowledged" | "dismissed";
export type RiskReview = "supported" | "inconclusive" | "dismissed" | "unavailable" | "not_requested";
export type Origin = "rule" | "model" | "matcher";
export type RecheckOutcome = "still_detected" | "not_detected_in_checked_version" | "inconclusive";
export type Severity = "high" | "medium" | "low";
export type ActionKind = "takedown_request" | "disable_aws_key";
export type ActionStatus =
  | "drafted"
  | "awaiting_manual_submission"
  | "executing"
  | "submitted"
  | "completed"
  | "failed"
  | "rejected";

export const TERMINAL: ScanState[] = ["completed", "partial", "failed", "cancelled", "interrupted"];
export const isTerminal = (s: ScanState) => TERMINAL.includes(s);

// ---------- records ----------
export interface EngineErrorBody {
  code: string;
  message: string;
  retryable: boolean;
}

export interface Capabilities {
  engine_version: string;
  checks: Check[];
  supported_inputs: string[];
  local_risk_rules: string[];
  model: { available?: boolean; model?: string; reason?: string; [k: string]: unknown };
  limits: Record<string, number>;
  client_capabilities: Record<string, Capability[]>;
  remediation?: { takedown_delivery?: string; aws_key_disable?: string };
}

export interface Workspace {
  id: string;
  name: string;
  source_type: "local_dir" | "upload_only" | string;
  revision: number;
  capabilities: Capability[];
  disclosure: Disclosure;
  manifests: string[];
}

export interface CapturedFile {
  file_id: string;
  path: string | null;
  status: "captured" | "deleted" | "rejected";
  reason: string | null;
  size: number | null;
  kind: string | null;
  change: string | null;
}

export interface Input {
  input_id: string;
  workspace_id: string;
  revision: number;
  expires_at: string;
  baseline: string | null;
  files: CapturedFile[];
  omitted_context: string[];
}

export interface ScanAccepted {
  scan_id: string;
  state: ScanState;
  input_id: string;
  status_url: string;
}

export interface Coverage {
  scope: "check" | "source" | "file" | "stage" | "rule" | string;
  id: string;
  status: CoverageStatus;
  reason: string | null;
  counts: Record<string, number>;
}

export interface Stage {
  name: string;
  status: "pending" | "running" | "done" | "failed" | "skipped" | "cancelled";
  detail: string | null;
}

export interface Scan {
  scan_id: string;
  workspace_id: string;
  input_id: string;
  state: ScanState;
  checks: Check[];
  recheck_of: string | null;
  public_snapshot_id: string | null;
  public_freshness: string | null;
  stages: Stage[];
  coverage: Coverage[];
  budget: Record<string, number>;
  versions: Record<string, string>;
  errors: EngineErrorBody[];
  summary: Record<string, unknown>;
  /** Present when the scan searched with an approved query plan instead of a fixed source list. */
  public_discovery?: DiscoveryStatus | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  deadline_at: string | null;
  /** Which client started it: the coding assistant (MCP), this web app, or something else (CLI, tests). */
  initiated_by?: string | null;
  started_from?: "assistant" | "app" | "other";
}

export interface Location {
  file_id: string;
  path: string | null;
  start: number;
  end: number;
  line_start: number | null;
  line_end: number | null;
  paragraph_id: string | null;
}

export interface PublicSpan {
  source_id: string;
  url: string;
  start: number;
  end: number;
  retrieved_at: string | null;
  freshness: "fresh" | "cached";
  snapshot_id: string;
  mode?: "seeded" | "discovered";
  provider?: string | null;
  discovery_run_id?: string | null;
  discovery_origins?: DiscoveryOrigin[] | null;
}

// ---------- company discovery (docs/ENGINE_API.md "Company-name discovery") ----------
export interface CompanyProfile {
  profile_id: string;
  workspace_id: string;
  version: number;
  display_name: string;
  official_domain: string | null;
  public_aliases: string[];
  approved_by: string;
  approved_at: string;
  privacy_notice_version: string;
  privacy_notice: string;
}

export interface PlannedSearch {
  query_id: string;
  template_id: string;
  provider: "exa" | "tavily" | string;
  query: string;
  num_results: number;
  include_domains: string[] | null;
  include_domains_mode?: string | null;
  exclude_domains?: string[] | null;
  category?: string | null;
  topic?: string | null;
  exact_match?: boolean | null;
  preset_status?: "benchmarked" | "experimental" | "legacy" | string | null;
}

export interface QueryPlan {
  query_plan_id: string;
  workspace_id: string;
  profile_id: string;
  profile_version: number;
  display_name: string;
  official_domain: string | null;
  template_version: string;
  pack: string | null;
  omitted_presets: { preset: string; reason: string }[];
  searches: PlannedSearch[];
  scope: { mode: "broad" | "selected"; site_groups: string[]; exclude_official_domain?: boolean; exclude_noise?: boolean };
  budget: Record<string, number | string>;
  privacy_notice: string;
  created_by: string;
  created_at: string;
}

export interface PresetInfo {
  preset_id: string;
  description: string;
  status: "benchmarked" | "experimental" | "legacy";
  needs: string[];
  benchmark: { cases_hit: string[]; providers_hit: string[] } | null;
  site_groups: string[];
}

export interface PresetCatalog {
  template_version: string;
  benchmark_version: string;
  noise_domains: string[];
  site_groups: Record<string, string[]>;
  presets: PresetInfo[];
  packs: { pack_id: string; description: string; shape: string; presets: string[] }[];
  shapes: Record<string, { max_searches: number; max_results_per_search: number }>;
}

export interface DiscoveryOrigin {
  query_id: string;
  provider: string;
  rank: number;
  title: string | null;
  returned_url: string;
}

export interface DiscoveryStatus {
  query_plan_id: string;
  mode: "live" | "snapshot";
  run_id?: string;
  state?: "searching" | "fetching" | "comparing" | "done" | "failed";
  outcome?: "candidates_found" | "partial_search" | "no_candidates" | "search_failed" | "snapshot_replay" | string | null;
  searches?: number;
  searches_ok?: number;
  returned_count?: number;
  unique_count?: number;
  fetch_attempted_count?: number;
  fetched_count?: number;
  skipped_count?: number;
  truncated?: boolean;
}

export type FetchStatus = "pending" | "fetched" | "failed" | "blocked" | "skipped_limit";
export type ComparisonStatus = "matched" | "no_match" | "incomplete" | "not_compared";

export interface SourceRow {
  source_id: string;
  original_url: string;
  final_url: string | null;
  title: string | null;
  mode: "seeded" | "discovered";
  discovery_origins: DiscoveryOrigin[];
  discovery_provider: string | null;
  extraction_provider: string | null;
  search_rank: number | null;
  fetch_status: FetchStatus;
  failure_reason: string | null;
  retrieved_at: string | null;
  retrieval_note: string | null;
  provider_content_timestamp: string | null;
  truncated: boolean;
  comparison_status: ComparisonStatus;
  match_count: number;
  freshness: "fresh" | "cached" | null;
}

export interface DiscoveryRun {
  run_id: string;
  query_plan_id: string;
  mode: "live" | "snapshot";
  state: string;
  outcome: string | null;
  provider_queries: { query_id: string; provider: string; query: string; status: string; error: string | null; returned: number; truncated: boolean }[];
  search_errors: string[];
  returned_count: number;
  unique_count: number;
  fetched_count: number;
  skipped_count: number;
  truncated: boolean;
  note: string;
}

export interface SourcePage {
  scan_id: string;
  discovery: DiscoveryRun | null;
  items: SourceRow[];
  next_cursor: string | null;
}

/** Every source for a scan (all pages), including no-match, failed, blocked and skipped ones. */
export async function allSources(workspaceId: string, scanId: string): Promise<SourcePage> {
  let page = await api<SourcePage>(ws(workspaceId, `/scans/${encodeURIComponent(scanId)}/sources?limit=100`));
  const items = [...page.items];
  for (let i = 0; i < 10 && page.next_cursor; i++) {
    page = await api<SourcePage>(ws(workspaceId, `/scans/${encodeURIComponent(scanId)}/sources?limit=100&cursor=${encodeURIComponent(page.next_cursor)}`));
    items.push(...page.items);
  }
  return { ...page, items };
}

export const DISCOVERY_OUTCOME: Record<string, string> = {
  budget_exhausted: "No searches ran: this scan's request budget was already used. Nothing was checked, so this isn't a result.",
  candidates_found: "Search returned candidate pages; each was fetched and compared on this machine.",
  partial_search: "Some searches failed. Pages that were returned were fetched and compared.",
  no_candidates: "Search returned no candidate pages. That's not a \"no leak\" result.",
  search_failed: "Search failed, so discovery is inconclusive.",
  snapshot_replay: "Replayed from a saved snapshot: no search or fetch ran in this scan.",
};

export const FETCH_LABEL: Record<FetchStatus, string> = {
  pending: "Pending",
  fetched: "Fetched",
  failed: "Fetch failed",
  blocked: "Blocked (unsafe URL)",
  skipped_limit: "Skipped (limit)",
};

export const COMPARISON_LABEL: Record<ComparisonStatus, string> = {
  matched: "Matched",
  no_match: "No match",
  incomplete: "No match in the retrieved part",
  not_compared: "Not compared",
};

export interface Evidence {
  evidence_id: string;
  scan_id: string;
  kind: "local_span" | "public_match";
  location: Location;
  file_sha256_prefix: string;
  public: PublicSpan | null;
  rule_id: string | null;
  matched_tokens: number | null;
  segment_coverage: number | null;
  availability: "available" | "evidence_unavailable" | "withheld_by_policy" | null;
  local_text: string | null;
  public_text: string | null;
}

export interface Observation {
  observation_id: string;
  finding_id: string;
  scan_id: string;
  input_id: string;
  revision: number;
  origin: Origin;
  check_id: string;
  check_version: string;
  rule_id: string | null;
  title: string;
  claim: string | null;
  conditions: string | null;
  missing_context: string | null;
  uncertainty: string | null;
  suggested_fix: string | null;
  verification_step: string | null;
  severity: Severity | null;
  severity_rationale: string | null;
  risk_review: RiskReview;
  counterevidence: string | null;
  model_id: string | null;
  prompt_version: string | null;
  evidence: Evidence[];
  created_at: string;
}

export interface Finding {
  finding_id: string;
  workspace_id: string;
  kind: FindingKind;
  check_id: string;
  rule_id: string | null;
  status: FindingStatus;
  human_review: HumanReview;
  human_review_reason: string | null;
  version: number;
  path: string | null;
  first_seen_scan: string;
  last_seen_scan: string;
  current_revision: number;
  latest: Observation | null;
}

export interface Recheck {
  recheck_id: string;
  finding_id: string;
  observation_id: string;
  scan_id: string;
  outcome: RecheckOutcome | null;
  reason: string | null;
  created_at: string;
}

export interface FindingDetail extends Finding {
  observations: Observation[];
  rechecks: Recheck[];
}

export interface RecheckAccepted {
  recheck_id: string;
  scan_id: string;
  state: ScanState;
  status_url: string;
}

export interface LedgerEvent {
  event_id: string;
  scan_id: string | null;
  destination_category: string;
  destination_host: string;
  purpose: string;
  source_id: string | null;
  status: string;
  payload_summary: Record<string, unknown>;
  at: string;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

/** Remediation actions: drafted automatically, executed only after a named person approves. */
export interface Action {
  action_id: string;
  workspace_id: string;
  finding_id: string;
  kind: ActionKind;
  status: ActionStatus;
  version: number;
  summary: string;
  target: { url?: string; host?: string; source_id?: string; excerpt?: string; retrieved_at?: string; access_key_id?: string };
  delivery: { method: "email" | "form" | "none"; address: string | null; form_url: string | null; transport: string | null } | null;
  subject: string | null;
  /** Rendered letter preview (company and signature filled in). */
  body: string | null;
  /** Raw editable draft for PATCH, when the engine provides it. */
  draft_body?: string | null;
  approver: { name?: string; email?: string; title?: string | null; client?: string } | null;
  approved_at: string | null;
  executed_at: string | null;
  result: { error?: EngineErrorBody; [k: string]: unknown };
  removal_observed: boolean | null;
  created_at: string;
  updated_at: string;
}

// ---------- transport ----------
export class ApiError extends Error {
  constructor(public status: number, message: string, public code: string = "http_error", public retryable = false) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  let res: Response;
  try {
    res = await fetch(`${ENGINE}${path}`, {
      ...rest,
      headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...rest.headers },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "Can't reach the Tracefold app server.", "app_unreachable", true);
  }
  if (!res.ok) {
    let err: EngineErrorBody = { code: `http_${res.status}`, message: res.statusText || "Request failed.", retryable: res.status >= 500 };
    try {
      const body = await res.json();
      if (body?.error?.code) err = body.error;
    } catch {}
    throw new ApiError(res.status, err.message, err.code, err.retryable);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** Workspace-scoped path. */
export const ws = (workspaceId: string, path = "") => `/workspaces/${encodeURIComponent(workspaceId)}${path}`;

// ---------- current workspace ----------
const WS_KEY = "tracefold.workspace";

export function storedWorkspace(): string | null {
  try {
    return localStorage.getItem(WS_KEY);
  } catch {
    return null;
  }
}

export function storeWorkspace(id: string) {
  try {
    localStorage.setItem(WS_KEY, id);
  } catch {}
}

/** The workspaces this app's grant covers, and the one currently selected. */
export function useWorkspace() {
  const [state, setState] = useState<{ list: Workspace[]; current: Workspace | null; error: ApiError | null; ready: boolean }>({
    list: [],
    current: null,
    error: null,
    ready: false,
  });
  useEffect(() => {
    api<{ items: Workspace[] }>("/workspaces")
      .then(({ items }) => {
        const want = storedWorkspace();
        const current = items.find((w) => w.id === want) ?? items[0] ?? null;
        setState({ list: items, current, error: null, ready: true });
      })
      .catch((e: ApiError) => setState({ list: [], current: null, error: e, ready: true }));
  }, []);
  const select = useCallback((id: string) => {
    storeWorkspace(id);
    setState((s) => ({ ...s, current: s.list.find((w) => w.id === id) ?? s.current }));
  }, []);
  return { ...state, select };
}

// ---------- recent scans (the engine has no list-scans endpoint yet; this browser remembers its own) ----------
const SCANS_KEY = "tracefold.recentScans";

export interface RecentScan {
  scan_id: string;
  workspace_id: string;
  label: string;
  at: string;
}

export function recentScans(workspaceId?: string): RecentScan[] {
  try {
    const all = JSON.parse(localStorage.getItem(SCANS_KEY) ?? "[]") as RecentScan[];
    return workspaceId ? all.filter((s) => s.workspace_id === workspaceId) : all;
  } catch {
    return [];
  }
}

export function rememberScan(s: RecentScan) {
  try {
    const all = recentScans().filter((x) => x.scan_id !== s.scan_id);
    localStorage.setItem(SCANS_KEY, JSON.stringify([s, ...all].slice(0, 50)));
  } catch {}
}

/** Every scan in the workspace from every client, newest first (the web app and the coding assistant share one engine). */
export function listScans(workspaceId: string, limit = 20) {
  return api<Page<Scan>>(ws(workspaceId, `/scans?limit=${limit}`));
}

// ---------- flows ----------
export async function uploadFiles(workspaceId: string, files: File[]): Promise<Input> {
  const form = new FormData();
  for (const f of files) form.append("file", f, f.name);
  return api<Input>(ws(workspaceId, "/uploads"), { method: "POST", body: form });
}

export async function startScan(
  workspaceId: string,
  body: {
    input_id: string;
    checks: Check[];
    public_sources?: { manifest_id: string; mode?: "refresh" | "snapshot" };
    public_discovery?: { query_plan_id: string; mode?: "live" | "snapshot"; snapshot_id?: string };
    model_review?: boolean;
  },
  label: string,
): Promise<ScanAccepted> {
  const acc = await api<ScanAccepted>(ws(workspaceId, "/scans"), { method: "POST", json: body });
  rememberScan({ scan_id: acc.scan_id, workspace_id: workspaceId, label, at: new Date().toISOString() });
  return acc;
}

/** Poll a scan every second until it reaches a terminal state. */
export function useScan(workspaceId: string | null, scanId: string | null) {
  const [scan, setScan] = useState<Scan | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!workspaceId || !scanId) return;
    let alive = true;
    const tick = async () => {
      try {
        const s = await api<Scan>(ws(workspaceId, `/scans/${scanId}`));
        if (!alive) return;
        setScan(s);
        if (!isTerminal(s.state)) timer.current = setTimeout(tick, 1000);
      } catch (e) {
        if (alive) setError(e as ApiError);
      }
    };
    tick();
    return () => {
      alive = false;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [workspaceId, scanId]);
  return { scan, error };
}

// ---------- wording the UI must use (docs/ENGINE_API.md "Vocabulary to render") ----------
export const STATE_MEANING: Record<ScanState, string> = {
  queued: "Waiting to run.",
  running: "Running.",
  completed: "Every requested check finished within its stated coverage. This doesn't mean there are no risks.",
  partial: "Some checks or coverage didn't finish. Results are usable but incomplete.",
  failed: "No requested check completed.",
  cancelled: "Cancelled. Anything found before cancelling is partial evidence.",
  interrupted: "The engine restarted during this scan. Upload or capture again.",
};

export const RECHECK_LABEL: Record<RecheckOutcome, string> = {
  still_detected: "Still detected",
  not_detected_in_checked_version: "Not detected in the checked version",
  inconclusive: "Inconclusive",
};

export const RISK_REVIEW_LABEL: Record<RiskReview, string> = {
  supported: "Supported by the reviewed source",
  inconclusive: "Inconclusive",
  dismissed: "Dismissed by review",
  unavailable: "Model review unavailable",
  not_requested: "Not reviewed",
};

export const ACTION_STATUS_LABEL: Record<ActionStatus, string> = {
  drafted: "Needs approval",
  awaiting_manual_submission: "Approved · submit on the host's form",
  executing: "Running",
  submitted: "Submitted",
  completed: "Done",
  failed: "Failed",
  rejected: "Rejected",
};

/** "No match in N checked sources" etc., from the scan's own coverage. */
export function coverageNote(scan: Scan, kind: FindingKind, count: number): string | null {
  const check = scan.coverage.find((c) => c.scope === "check" && c.id === (kind === "public_exposure" ? "public_match" : "local_risk"));
  if (!check || check.status === "not_requested")
    return kind === "public_exposure" ? "Public matching wasn't requested for this scan. That's not a 'no match' result." : "Risk review wasn't requested.";
  if (kind === "public_exposure" && check.reason === "no_candidate_sources_found")
    return "Search returned no candidate pages for the approved queries. That's not a \"no leak\" result.";
  if (kind === "public_exposure" && check.reason === "discovery_search_failed") return "Search failed, so public matching is inconclusive.";
  if (check.status !== "complete") return `${kind === "public_exposure" ? "Public matching" : "Risk review"} ${check.status}: ${check.reason ?? "see coverage"}.`;
  if (count > 0) return null;
  if (kind === "public_exposure") return `No match in ${check.counts.sources_ok ?? 0} checked sources.`;
  return `No potential risks identified by this review (${check.counts.files ?? 0} files covered).`;
}
