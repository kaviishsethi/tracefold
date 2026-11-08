# Company-name discovery for Tracefold

Status: steps 1–5 implemented in `server/tracefold/discovery/` (tests: `server/tests/test_m8_discovery.py`); step 6 ran twice (see `docs/sample-documents/nothing-memo/README.md`): run 1 missed the target, run 2 with revised generic presets found and matched it. Builds on the existing shared engine. User-approved scope: search using a public company name/domain, retrieve public pages, then compare uploaded documents locally. Preset searches are allowed; predetermined findings are not.

## Product flow

1. User selects a workspace, enters the public company name and optional official domain, and confirms these may be sent to the selected search providers.
2. The platform displays the exact public queries and source scope. The user uploads company documents separately.
3. The isolated worker searches Exa and/or Tavily using only the approved public identity and fixed query templates.
4. The worker returns candidate URLs; the engine validates, deduplicates and attempts to fetch all eligible candidates within the declared limits.
5. Existing local matching compares the captured private documents against the fetched public text. Local Ollama explains evidence and reviews private risks without generating external queries.
6. The app and MCP expose findings and the complete source trail. A successful search with no results, a failed search and failed extraction are distinct states.

Privacy wording: “Search providers see the public company identity and approved queries. They do not receive uploaded document contents.” Public names and search intent still leave the environment. A name/domain is approved by the user, not cryptographically proven public by validation.

## Existing implementation and changes needed

Inspection of this checkout found:

- `contracts/models.py`: `PublicSourcesIn` currently requires a manifest ID and supports refresh/snapshot behavior. No company-discovery request exists.
- `retrieval/worker.py`: Exa `/contents` and Tavily `/extract` adapters exist; no `/search` adapter is present. The worker's strict request allowlist should remain strict.
- `retrieval/service.py`: resolves approved seeded manifests, fetches pages, persists snapshots and invokes existing coverage handling. Live snapshot entries currently set `mode` to `seeded`.
- `jobs/stages.py`: public matching already consumes fetched text and generates span evidence. Preserve this matching logic; search scores or summaries must never become findings.
- Existing snapshots, gateway accounting and evidence records can be reused. Add search provenance and a source-list endpoint rather than creating a second search database.

## 1. Approved company profile and query plan

Add workspace-scoped `PublicCompanyProfile` records:

```text
id, workspace_id, version, display_name, official_domain?, public_aliases[],
approved_by, approved_at, privacy_notice_version
```

Only an explicitly authorized configuration action can create/revise the profile. A model or uploaded document cannot change it. Validate bounded lengths, control characters, URL/domain shape and query-operator escaping. Limit initial aliases to two. Accept a hostname for the official domain, not a path/query-string field that could hide document text. UI must make clear that secret project names and private context do not belong here. Rejecting emails or obvious key patterns is defense in depth, not proof that an arbitrary name is nonsensitive.

Use a deterministic, versioned query builder. Initial templates:

- Company name plus official domain, where supplied, to disambiguate public mentions.
- Company name plus generic terms such as `internal memo document`.
- Company name plus generic terms such as `source code configuration`.
- Company name with a selected public-site restriction, such as GitHub/Gist, Reddit or paste sites.

These templates are search intent, not guarantees that a site's search syntax supports Boolean operators. Translate supported domain restrictions into each provider's documented fields. The official company domain is an identity hint; do not restrict every search to that domain, which would miss third-party copies. Let the user choose broad web search or selected public domains.

Prepare a bounded query plan independently of document parsing. Store its exact rendered queries, profile/template versions, provider choices and limits. The scan references its ID. Switching the uploaded document while keeping the same approved plan must leave outbound search inputs unchanged. No automatic keyword extraction, document summarization, private filenames, embeddings, hashes or model-generated query follow-ups.

Preset queries may be rehearsed for the hackathon. Persist and show returned results from actual execution; never insert the desired URL if search fails to return it. Seeded URL mode remains separate and explicitly labeled.

## 2. Search → candidate validation → extraction

Extend the worker with a distinct `search` operation whose schema accepts a validated public plan, not a scan document or general prompt. Keep existing `fetch` behavior. The parent service selects the operation and supplies only approved fields; model outputs cannot populate this request.

Use REST through the existing gateway:

- Exa search: `POST https://api.exa.ai/search`, with bounded `numResults`, query and supported domain filters. Fetch returned candidates through the existing `/contents` adapter.
- Tavily search: `POST https://api.tavily.com/search`, with bounded `max_results`, `include_answer=false`, `include_raw_content=false`, and supported domain filters. Fetch through the existing `/extract` adapter.

Do not request generated answers or treat search snippets/highlights as complete document evidence. Even if a search result contains text, the first implementation performs an explicit extraction step so it has a clear per-source retrieval record. Later optimization may combine operations only if equivalent full-content/provenance requirements are met.

Retain provider/query/rank/title/returned URL for every candidate, including duplicates. Canonicalize conservatively: normalize scheme/host and remove fragments; preserve meaningful query parameters and paths. Keep original and final URLs. Avoid collapsing different files or versions into one URL. Map duplicate candidates to one fetch target while retaining each discovery origin.

Treat URLs as untrusted. Apply gateway policy before fetching: no credentials, private/loopback/link-local destinations, prohibited schemes, or redirects to disallowed targets. Validate DNS and redirect destinations at connection time for direct fetches. Provider-side extraction also receives only validated public URLs; it must not be used to bypass URL restrictions. Approved source scope applies to dynamically discovered URLs without requiring a separate manual approval for each safe page. Do not recursively follow links in fetched text in the first version.

Fetch every eligible unique returned candidate. Invalid URLs, duplicates, timeouts and budget/deadline skips remain visible with a reason. If a provider returns more than requested, record rejected excess metadata within a defensive response bound and mark the search response truncated. Never promise every returned URL was successfully read.

## 3. Provenance and result model

Add a `DiscoveryRun` linked to the scan:

```text
id, workspace_id, query_plan_id, profile_version, started_at, finished_at,
provider_queries[], search_errors[], returned_count, unique_count,
fetch_attempted_count, fetched_count, skipped_count, truncated
```

Each candidate/source record retains:

```text
source_id, original_url, final_url?, title?, discovery_origins[],
mode=discovered, discovery_provider, extraction_provider,
search_rank, fetch_status, failure_reason?, retrieved_at?,
provider_content_timestamp?, content_hash?, truncated,
comparison_status, match_count
```

Suggested fetch states: `pending`, `fetched`, `failed`, `blocked`, `skipped_limit`, `duplicate`. Comparison states: `matched`, `no_match`, `incomplete`, `not_compared`. A truncated source cannot receive an unqualified “no match”; say no match in the retrieved portion. Preserve search-query provenance when one URL appears through both providers. Do not count it as two independent exposures.

Persist dynamic results as a scan-owned discovered manifest/snapshot compatible with current matching. Generate source IDs from workspace + canonical URL consistently across runs; do not change IDs just because provider rank changes. Save immutable query-plan and profile versions for replay. A changed live search result list must not resolve an old finding: omission from search is not evidence that the public copy disappeared. Existing exposure rechecks must fetch the previously cited URL explicitly and keep that recheck provenance separate from current discovery.

Freshness wording: record “API retrieval during this scan” separately from origin publication/crawl time. Provider caches are possible. Never invent origin freshness, or silently reuse a previous snapshot following a failed refresh.

## 4. API and app/MCP integration

Proposed additive endpoints, subject to contract review before coding:

| Endpoint | Use |
|---|---|
| `POST /v1/workspaces/{id}/company-profiles` | Approve public company identity; scoped configuration permission required. |
| `POST /v1/workspaces/{id}/query-plans` | Create immutable plan from profile ID, preset IDs, provider selection and public-domain scope. |
| `GET /v1/workspaces/{id}/query-plans/{plan_id}` | Preview exact outbound queries and budget. |
| `GET /v1/workspaces/{id}/scans/{scan_id}/sources` | Paginated complete source list, including no-match/failed/skipped candidates and discovery provenance. |

Extend the existing scan DTO with an optional `public_discovery` object containing `query_plan_id` and `mode=live`. Enforce exactly one of existing `public_sources` or `public_discovery` when public matching is requested. Preserve existing seeded/snapshot request behavior. No arbitrary query or company name fields in scan submission. Snapshot replay uses the saved manifest/snapshot and retains discovered origins while labeling all content cached.

Add `public_discovery` before `public_retrieval` and `public_match` in job state. Return search progress and errors separately from extraction progress. The same scan ID and persisted results power the upload app and MCP tools. Proposed MCP extensions: selecting an already approved query plan and `get_sources(scan_id)`. MCP cannot approve new public identity silently or broaden a plan based on private workspace content. Proactive code-risk scans do not automatically run company discovery on every edit.

App display order: company identity → exact queries/scope → search progress → source table → match evidence. Include all sources, not just alarming ones. Exact queries and public-result metadata still disclose investigation interest, so enforce the existing workspace and host-response policies on these endpoints too.

## 5. Bounded pilot and failure behavior

Initial discovery budget within existing engine limits:

- At most four search requests across all providers, five results per request: at most 20 returned candidates before deduplication.
- At most 20 unique pages; 200 KB extracted text per page; existing 50 MB public cache.
- Keep 40 total provider requests per scan, counting search, extraction and retries together. Reserve extraction capacity before issuing additional searches. Maximum one bounded retry/fallback per failed source while capacity remains; no retry tree.
- Two concurrent external requests, one active scan, existing five-minute scan deadline. Stop and expose partial coverage on budget exhaustion; never bypass limits to fetch everything.
- One shared content-addressed public blob per version and compact per-run metadata. No per-query copies of documents or databases. Measure the first live run's time, bytes and provider usage before increasing scope.

Search failed: show the provider error and inconclusive discovery. Search succeeded with zero results: show no candidate sources found, not “no leak.” Some sources fetched: compare them and show partial coverage. Local risk review can complete even when discovery fails. Offline replay works only for an already saved public snapshot and is labeled accordingly.

No new dependency/CVE search or takedown submission is introduced by this feature.

## 6. Implementation order and acceptance tests

1. **Profile/plan contracts and authorization.** Add immutable plan storage, query preview, and strict scan-input validation. Test identical queries for different private uploads, refusal of document-derived fields and cross-workspace access.
2. **Provider search adapters.** Add bounded Exa/Tavily calls through the gateway. Test provider errors, malformed responses, limits, accurate request accounting and no generated-answer use.
3. **Candidate normalization and full fetching.** Create discovered manifests, preserve provenance, reject unsafe URLs, deduplicate fetches and retain every candidate's status. Reuse current extraction and snapshot code.
4. **Job and evidence integration.** Add search stage and discovered provenance to citations. Test search omission cannot clear an existing exposure, partial failures remain incomplete and matching stays computed from fetched text.
5. **Source-list endpoint and clients.** Expose no-match and failed sources to both app and MCP; regenerate OpenAPI and update client contracts together. Keep seeded/snapshot regression coverage.
6. **One bounded live rehearsal.** Use approved public identity plus preset queries, real returned URLs, successful extraction and local positive/negative comparison. Save exact queries, timestamps, counts and evidence. No precomputed findings or fallback injected target URL. If the expected page is absent, show that outcome and revise the public query plan before—not during—the recorded claim.

Privacy acceptance: place a unique synthetic secret in an upload; prove no document text, marker, filename or hash enters search/extraction requests. Inspect construction and ledger plus runtime isolation, not substring checks alone. Retrieved text with instructions to change queries must remain inert. Model failure cannot produce a fabricated finding or cloud fallback.

Walkthrough dataset status is independent: a public policy proves public availability, not an unauthorized leak; the existing Nothing excerpt is only a short reported-leak reference. Discovery success must be tested separately from prior successful direct-URL extraction. Do not claim those pairs are search-discoverable until the chosen queries actually return them.

## References

- [Exa Search](https://exa.ai/docs/reference/search): REST search, result limits and domain filters.
- [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search): REST search, result limits, domain filters and generated-answer/content switches.
- [Shared engine plan](SHARED_ENGINE_PLAN.md): workspace permissions, jobs, input retention and existing resource limits.

Provider request fields must be checked against the implementation-time documentation. The architecture and scope above are our design decisions; neither provider guarantees exhaustive coverage or accurate company attribution.
