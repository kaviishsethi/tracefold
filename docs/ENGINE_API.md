# Tracefold engine API — client handoff

For whoever builds the upload app or the MCP adapter. The MCP adapter now exists in [`adapters/mcp/`](../adapters/mcp/README.md) and follows the tool mapping below. The engine is implemented in [`server/`](../server/README.md);
the machine-readable contract is [`server/openapi.json`](../server/openapi.json) (regenerate with
`uv run tracefold export-openapi openapi.json`). [`server/examples/demo_flow.py`](../server/examples/demo_flow.py)
calls every endpoint and is exercised by the test suite against a real `tracefold serve` process.

Clients must not parse files, call a model, assign severity, or keep their own findings. Render what the engine
returns.

## Connecting

- Base URL `http://127.0.0.1:<port>/v1`. Requests with any other `Host` get 400. Browser requests must come from an
  allowed `Origin` (default `http://localhost:3000`, `http://127.0.0.1:3000`).
- `Authorization: Bearer tf_…` on every route except `/health`. An operator provisions tokens with the CLI. Clients
  cannot register workspaces, roots or manifests.
- Each grant has **capabilities** (`submit`, `read`, `read_evidence`, `recheck`, `cancel`, `review`) and a
  **disclosure** policy:
  - `full`: paths, model explanations and evidence text.
  - `minimal`: no paths, no free-text explanations, evidence text withheld. Use `minimal` for any assistant whose
    model is cloud-hosted.
- A workspace, scan, finding or evidence ID that belongs to another workspace returns 404, as if it doesn't exist.

## Flow

```text
capture (upload or workspace files/changes) → input_id (expires; in memory only)
POST scans {input_id, checks, public_sources?} → 202 {scan_id, status_url}
poll GET status_url until state ∉ {queued, running}
GET findings?scan_id=… → findings, each with its latest observation and evidence refs
GET evidence/{id} → masked local text and public text (needs read_evidence and full disclosure)
user edits file → new capture → POST findings/{id}/rechecks {input_id} → poll → GET findings/{id}
```

Long operations always return 202. Don't hold a request (or an MCP tool call) open for a scan; poll every
0.5–2 s.

## Endpoints and MCP tool mapping

| Endpoint | Purpose | MCP tool |
|---|---|---|
| `GET /health` | Liveness | – |
| `GET /capabilities` | Checks, rules, limits, model availability, this client's grants | `get_capabilities` |
| `GET /workspaces` | Granted workspaces only | `list_workspaces` |
| `POST /workspaces/{ws}/uploads` | multipart `file` parts → `InputOut` | app only |
| `POST /workspaces/{ws}/captures` | `{"mode":"files","paths":[…]}` or `{"mode":"changes","baseline":"HEAD","include_untracked":true}` | inside `scan_changes` |
| `POST /workspaces/{ws}/scans` | Queue a scan (`Idempotency-Key` supported) | `scan_changes` = capture + submit |
| `GET /workspaces/{ws}/scans/{id}` | State, stages, coverage, budget, versions, errors | `get_scan` |
| `POST /workspaces/{ws}/scans/{id}/cancel` | Cooperative cancellation | `cancel_scan` |
| `GET /workspaces/{ws}/findings?scan_id=&cursor=&limit=` | Paginated (default 50, max 100) | `get_findings` |
| `GET /workspaces/{ws}/findings/{id}` | Full history: observations and rechecks | `explain_finding` (reads the stored explanation; never generate a second one) |
| `GET /workspaces/{ws}/evidence/{id}` | Policy-gated evidence text | only if host policy permits |
| `POST /workspaces/{ws}/findings/{id}/rechecks` | `{input_id}` → scoped recheck scan | `recheck_fix` |
| `PATCH /workspaces/{ws}/findings/{id}/review` | `{state, reason?, expected_version}`; dismissal needs a reason | later |
| `GET /workspaces/{ws}/scans/{id}/ledger` | Redacted outbound-request accounting | app |

The MCP adapter holds its own token in local config. It must not accept a server URL, token, workspace root or
network query from the host.

## Remediation actions (approval required)

After every scan the engine drafts remediation **actions** for a person to approve. Nothing is sent or changed
until someone approves; this keeps the plan's rule that Tracefold never silently sends takedowns or rotates
credentials ([PLAN.md](../PLAN.md) §"Act").

| Action `kind` | Drafted for | On approval |
|---|---|---|
| `takedown_request` | every `public_exposure` finding | Emailed to the host's configured abuse/legal address, or, if the host only takes its own web form, moved to `awaiting_manual_submission` with the form link and the prefilled text. |
| `disable_aws_key` | every long-term AWS access key ID (`AKIA…`) found in a scanned file | The key is set **Inactive** in IAM using the company's remediation credentials. The leaked key is never used, and no replacement key is created. |

| Endpoint | Purpose | Capability |
|---|---|---|
| `GET /workspaces/{ws}/actions?status=&finding_id=&cursor=&limit=` | List actions | `read` |
| `GET /workspaces/{ws}/actions/{id}` | One action, with the rendered letter (full disclosure only) | `read` |
| `PATCH /workspaces/{ws}/actions/{id}` | `{subject?, body?, expected_version}`: edit a takedown before it's sent. `body` replaces the **draft** text: edit `draft_body`, not `body` | `approve` |
| `POST /workspaces/{ws}/actions/{id}/approve` | `{approver: {name, email, title?}, attest_authorized: true, expected_version}`: sign and execute | `approve` |
| `POST /workspaces/{ws}/actions/{id}/reject` | `{reason, expected_version}` | `approve` |
| `POST /workspaces/{ws}/actions/{id}/mark-submitted` | `{note?, expected_version}` after filing a host's web form | `approve` |

A takedown action carries two texts. `body` is the rendered preview: company details filled in and the signature
(or a placeholder before approval) appended. `draft_body` is the editable text: it keeps the literal `{company}`
token and has no signature. Edit `draft_body` and send it back as `body` in PATCH; the engine adds the company
details and exactly one signature when it renders and sends the letter. Both are withheld under `minimal` disclosure.

Action `status`: `drafted` → (`awaiting_manual_submission` →) `submitted` for takedowns, `completed` for keys;
`failed` (can be approved again) or `rejected`. **`submitted` is not removed.** `removal_observed` becomes true only
after a later fresh public scan no longer finds the passage at that URL.

`approve` is a separate capability. `tracefold add-client` grants every capability by default, so give assistants
an explicit `--caps` list without it (the MCP adapter setup already does). Takedown letters contain only the public
URL, the copied text as it appears there (secret-shaped values masked) and the company's details. They never
include the private file's name or other private text. Under `minimal` disclosure the letter and excerpt are
withheld and AWS key IDs are always shown masked.

Approval errors (409): `remediation_profile_missing`, `no_takedown_contact`, `aws_remediation_not_configured`,
`invalid_state`, `version_conflict`. Missing attestation is 422 `attestation_required`.

Operator setup (CLI only):

```bash
uv run tracefold set-remediation-profile ws_demo --company "Northwind Relay, Inc." --reply-to legal@northwind.example
uv run tracefold add-takedown-contact ws_demo forum.example --email abuse@forum.example
uv run tracefold add-takedown-contact ws_demo pastes.example --form-url https://pastes.example/legal/removal
```

There is no built-in directory of host contacts: an operator adds each one. `GET /capabilities` reports
`remediation.takedown_delivery` (`outbox`, `resend`, `resend_not_configured`) and `remediation.aws_key_disable`.

## Vocabulary to render (never invent "safe")

| Field | Values | Show as |
|---|---|---|
| scan `state` | `completed` / `partial` / `failed` / `cancelled` / `interrupted` | Completed means every requested check finished within its stated coverage. It does not mean "no risks". |
| coverage `status` per check/source/file/rule/stage | `complete` / `partial` / `failed` / `not_requested` | Always show the reason. `not_requested` public matching ≠ "no match". |
| finding `kind` | `public_exposure` / `local_risk` | Two separate sections: **Public exposure** and **Potential risks in your files**. |
| finding `status` | `open` / `not_detected_in_checked_version` / `no_longer_observed` | The last one only comes from a fresh, successful retrieval. |
| observation `risk_review` | `supported` / `inconclusive` / `dismissed` / `unavailable` / `not_requested` | `supported` = supported by the reviewed source, not confirmed at runtime. |
| observation `origin` | `matcher` / `rule` / `model` | `model` = model-only suggestion that needs review. |
| recheck `outcome` | `still_detected` / `not_detected_in_checked_version` / `inconclusive` | Never "fixed". |
| public `freshness` | `fresh` / `cached` | Label cached evidence with its retrieval time. |

Empty results:

- Public matching: "No match in N checked sources" (from `coverage.counts.sources_ok`).
- Risk review: "No potential risks identified by this review", with the files and checks covered.

## Errors

Every error uses one shape: `{"error": {"code", "message", "retryable"}, "request_id"}`.

| HTTP | When |
|---|---|
| 401 | Missing or invalid token |
| 403 | Missing capability, or browser origin not allowed |
| 404 | Missing or inaccessible resource (doesn't reveal whether it exists) |
| 409 | `idempotency_conflict`, `version_conflict`, `capture_conflict` (file changed while being captured) |
| 410 | `input_expired`: capture again |
| 413 | Size or file-count limit |
| 422 | Invalid contract (`invalid_request`, `invalid_baseline`, `public_sources_required`, `unknown_source`, …) |
| 429 | `queue_full`, `capture_capacity` (retryable) |

Failures in a stage or provider show up in the scan's `errors` and `coverage`. They never appear as an HTTP 200 "clean"
result.

## Privacy behaviour clients can rely on

- Private bytes stay in an in-memory registry: no disk spooling, and a restart drops them. The database holds IDs,
  hashes, locations and sanitized text. Secret values are masked in evidence and never persisted.
- Public retrieval runs in a separate process. It receives only manifest entries (source ID, URL, provider). On
  macOS it is sandboxed from the data directory and workspace roots. Scan `summary.retrieval_isolation` reports the
  mode (`…_partial` means a root could not be denied because it contains the engine itself).
- The model endpoint must be loopback. Model text is scrubbed of secrets and long verbatim echoes before storage.
- None of this makes the deployment private on its own. Strict-private mode still requires an observed
  network-denial test of the private runtime and a local-model MCP host.
