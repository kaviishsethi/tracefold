# Company-name discovery

Company-name discovery finds public copies of a company's material without sending that material anywhere. Search
providers (Exa and Tavily) receive only an approved public company identity and fixed query templates. They return
candidate URLs; Tracefold fetches those pages and compares them against uploaded documents locally. Findings come only
from that local comparison.

Code: `server/tracefold/discovery/`. Endpoints, request shapes and display guidance:
[ENGINE_API.md, "Company-name discovery"](ENGINE_API.md#company-name-discovery).

Privacy notice shown before approval: "Search providers see the public company identity and approved queries. They do
not receive uploaded document contents." Public names and search intent still leave the environment. Validation cannot
prove a name is public; the person approving it is responsible for that.

## Flow

1. A client with the `configure` capability approves a public company profile.
2. It creates a query plan from that profile: presets or a pack, providers and a site scope. The plan stores every
   outbound search exactly as it will be sent, so the preview is what leaves the machine.
3. A scan references the query plan by ID. The scan request carries no company name, query or document-derived field.
4. Stages run `public_discovery` (search) → `public_retrieval` (extract) → `public_match` (local comparison).
5. The app and MCP read the same scan: search progress, the complete source list and match evidence.

## Company profile

`identity.py`. A profile is versioned workspace configuration:

```text
id, workspace_id, version, display_name, official_domain?, public_aliases[≤2],
approved_by, approved_at, privacy_notice_version
```

- Only an authorized configuration action creates or revises a profile. Models and uploaded documents cannot.
- Names are 2–80 characters, without control characters, quotes or search operators. A word may not start with `-`
  and a name may not begin with `OR`, `AND` or `NOT`. Values that look like an email address or credential are
  rejected. This is defense in depth, not proof that a name is non-sensitive.
- `official_domain` must be a bare public hostname: no scheme, port, path, query or IP address, and no internal suffix
  such as `.local`, `.corp` or `.internal`.
- At most two aliases; duplicates of the display name are dropped.

## Query plans

`presets.py`. A query plan is immutable and deterministic: the same profile, presets, providers and scope always
render the same searches. Inputs are limited to `display_name`, `official_domain`, `public_aliases` and the scope
choice. No template reads documents, filenames, hashes, embeddings, search results or model output, and there are no
model-generated follow-up queries. Changing the uploaded document never changes a query plan's outbound searches.

Each rendered search records `query`, `num_results`, `include_domains` (with Tavily `include_domains_mode`),
`exclude_domains`, Exa `category`, Tavily `topic` and `exact_match`, plus the template version
(`company_queries_v3`), noise-list version (`noise_v1`) and budget shape.

**Scope.** `broad` searches the open web; `selected` restricts every search to chosen site groups. When a preset has its
own site list and the scope is `selected`, the two are intersected; an empty intersection rejects the preset with a
422. Two exclusions are on by default and shown in the preview:

- `exclude_official_domain`: the company's own site is excluded from results, since third-party copies are the point.
  The domain still appears in query text as an identity hint, and searches are never restricted to it.
- `exclude_noise`: a fixed list of profile, social and dictionary sites (`linkedin.com`, `wikipedia.org`,
  `tavily.com`, `crunchbase.com`, `trustpilot.com`, `glassdoor.com`, `merriam-webster.com`, `dictionary.com`,
  `youtube.com`, `facebook.com`, `instagram.com`, `x.com`, `twitter.com`). A domain is added only after it appears as
  noise in at least two benchmark cases and never hosts a known copy.

Exclusions do not apply to searches restricted to a site list. Exa has no "prefer" mode, so a preferred site list on Exa
becomes an open-web search with exclusions.

**Site groups.**

| Group | Domains |
|---|---|
| `github` | github.com, gist.github.com |
| `reddit` | reddit.com |
| `paste` | pastebin.com, paste.ee, rentry.co, ghostbin.cloud |
| `code` | github.com, gist.github.com, gitlab.com, bitbucket.org |
| `documents` | scribd.com, issuu.com, docdroid.net, yumpu.com, slideshare.net, speakerdeck.com |
| `forums` | reddit.com, teamblind.com, news.ycombinator.com |

**Budget shapes.** A query plan uses one of two shapes: up to 4 searches × 5 results, or 8 searches × 3 results. Both
fit the 40-request scan cap with extraction reserved (4 + 20 + 16 fallbacks, or 8 + 20 + 12).

## Presets and packs

A preset is search intent rendered separately for each provider: Exa queries describe the page wanted (neural search);
Tavily queries are keyword phrases, usually with `exact_match` so a company name that is also a common word is not
matched loosely. No template uses Boolean operators, because providers do not guarantee support for them.
`{name}` is the display name, `{alias}` the first public alias, `{domain}` the official domain.

| Preset | Finds | Exa | Tavily | Sites | Needs | Status |
|---|---|---|---|---|---|---|
| `leak_news` | News quoting a leaked internal document | `news article quoting a leaked internal memo from {name}`, category `news` | `"{name}" leaked internal memo`, topic `news` | | | benchmarked |
| `leak_news_alias` | Same, under the first alias | as above with `{alias}` | as above with `{alias}` | | alias | benchmarked |
| `leaked_email` | Published CEO or all-hands emails | `full text of an internal email sent to {name} employees`, category `news` | `"{name}" email to employees full text` | | | benchmarked |
| `leaked_roadmap` | Reported roadmaps and strategy documents | `leaked {name} product roadmap or strategy document`, category `news` | `"{name}" leaked roadmap` | | | experimental |
| `product_leaks` | Leaked specifications of upcoming products | `leaked specifications of an upcoming {alias} product`, category `news` | `"{alias}" leaked specs`, topic `news` | | alias | experimental |
| `leaked_deck` | Internal, investor or board slides | `internal presentation slides from {name}` | `"{name}" internal presentation slides` | `documents` (prefer) | | experimental |
| `doc_sharing` | Documents on sharing sites | `document published by {name}` | `"{name}"` | `documents` | | experimental |
| `code_hosts_name` | Repositories, gists and issues naming the company | `source code repository from {name}` | `"{name}"` | `code` | | experimental |
| `code_hosts_domain` | Code and config mentioning the official domain | `configuration file referencing {domain}` | `"{domain}" config` (no exact match) | `code` | domain | experimental |
| `paste_sites` | Pastes naming the company or domain | `{name} {domain}` | `"{name}" {domain}` (no exact match) | `paste` | domain | experimental |
| `policy_copies` | Republished policies, handbooks and procedures | `{name} employee handbook or company policy document` | `"{name}" policy handbook procedure` | | | benchmarked |
| `security_docs` | Security policies and incident-response documents | `{name} security policy or incident response plan document` | `"{name}" security policy incident response` | | | benchmarked |
| `breach_coverage` | Reporting on breaches and source-code leaks | `report on a data breach or source code leak at {name}`, category `news` | `"{name}" breach source code leak`, topic `news` | | | experimental |
| `employee_forums` | Employee posts about internal material | `{name} employee discussion about internal documents` | `"{name}" employees internal` | `forums` | | experimental |
| `financial_filings` | Filings quoting internal documents | `{name} financial report`, category `financial report` | `"{name}" annual report internal`, topic `finance` | | | experimental |

Site lists restrict results unless marked "prefer". Status meanings:

- **benchmarked**: on at least one provider, returned a page outside the company's own domain that matched a benchmark
  reference document locally (at least 12 normalized tokens), with no negative-control match. Evidence per preset is in
  `BENCHMARK` (`BENCHMARK_VERSION = "v3-2026-11-08c"`) and returned by `GET /v1/query-presets`.
- **experimental**: no benchmark target found yet. Usable when named directly; included in packs only with
  `include_experimental: true`.
- **legacy**: earlier wording (`identity`, `internal_docs`, `source_config`, `leak_reports`, `alias_leak_reports`,
  `public_sites`), kept so stored query plans replay. In no pack.

A pack is a named bundle of presets with a fixed budget shape, run on each selected provider. Packs are a convenience;
the query plan still stores every rendered search. Experimental presets in a pack are skipped and listed in
`omitted_presets` unless `include_experimental` is set.

| Pack | Shape | Presets | Use |
|---|---|---|---|
| `leak_watch` | 4×5 | `leak_news`, `leak_news_alias` | Reported leaks of internal documents |
| `document_copies` | 8×3 | `leaked_deck`, `doc_sharing`, `policy_copies`, `security_docs` | Republished documents |
| `code_exposure` | 8×3 | `code_hosts_name`, `code_hosts_domain`, `paste_sites`, `breach_coverage` | Source code, configuration and pastes |
| `broad_triage` | 8×3 | `leak_news`, `leaked_email`, `policy_copies`, `code_hosts_name` | A first run for a new company |

Creating a query plan from a pack requires `configure`, like any query plan. The MCP adapter can only select an already
approved query plan; it cannot approve an identity or widen a query plan. Nothing runs automatically on edits or on a
schedule.

### Automatic discovery on upload

`automatic.py`. For upload-and-scan without an approved query plan, a local model reads a bounded sample of the uploaded
files (up to 16K characters) and returns at most two company names and a document kind (`policy`, `memo`, `other`). A
name is kept only if it passes profile validation and appears verbatim in the text. If the workspace has an approved
identity for its own company, that name is always searched first. Presets are chosen by kind (`memo`: `leak_news`,
`leaked_email`, or `leak_news` + `leak_news_alias` when an alias is configured; `policy`: `security_docs`,
`policy_copies`; otherwise `policy_copies`, `leak_news`). Only the company names and fixed templates reach providers;
passages and filenames do not. If no company can be identified, public matching is reported as failed and local checks
still run.

## Search, candidate validation and extraction

`service.py`, `urls.py`.

**Search.** The isolated worker accepts a distinct `search` operation containing only the stored, rendered fields of
each search. Exa uses `POST /search`; Tavily uses `POST /search` without generated answers or raw content. Search
snippets and titles are never evidence. Extraction capacity is reserved before searches run: searches that would leave
fewer requests than the page limit are skipped as `budget_reserved_for_extraction`.

**Candidates.** For every returned result Tracefold records the query, provider, rank, title and returned URL,
including duplicates. URLs are untrusted:

- Refused before any fetch (`blocked`, never sent anywhere): non-HTTP(S) schemes, credentials in the URL, IP literals
  including shorthand forms, `localhost` and internal suffixes, non-default ports, control characters, URLs over 2,048
  characters, and hosts on the workspace's never-fetch list.
- Canonicalization only lowercases scheme and host, drops default ports and fragments. Paths and query strings are kept,
  so different files or versions are never merged.
- Source IDs derive from workspace + canonical URL, so they are stable across runs and independent of rank. A URL
  returned by several queries or both providers is one source with several `discovery_origins`, not two exposures.
- DNS and redirect targets are checked again by the gateway at connection time for direct fetches.

Two kinds of page are added alongside search results and fetched directly: pages on the workspace's always-check list,
and pages that matched the same set of files in an earlier scan, so a known exposure is still checked if search stops
returning it. When the same files were scanned within the last 24 hours (`TRACEFOLD_SEARCH_REUSE_HOURS`), search is
skipped and those remembered pages are rechecked instead.

**Extraction.** Every eligible unique candidate is fetched, up to 20 pages and 200 KB of text per page, through the
discovering provider's extraction endpoint (Exa `/contents`, Tavily `/extract`) or directly. A failed source gets at
most one fallback attempt with the other provider; there is no retry tree. Links inside fetched text are not followed.
Budget or deadline exhaustion stops fetching and marks the remaining sources `skipped_limit`.

**Comparison.** The existing local matcher compares uploaded documents against the fetched text and produces
span-level evidence.

## Provenance and results

Each scan with discovery has a discovery run:

```text
id, query_plan_id, profile_version, started_at, finished_at, provider_queries[], search_errors[],
returned_count, unique_count, fetch_attempted_count, fetched_count, skipped_count, truncated, outcome
```

Each source records:

```text
source_id, original_url, canonical_url, final_url?, title?, mode=discovered, discovery_origins[],
discovery_provider, extraction_provider, search_rank, fetch_status, failure_reason?, retrieved_at?,
provider_content_timestamp?, content_hash?, truncated, comparison_status, match_count
```

- `fetch_status`: `fetched`, `failed`, `blocked`, `skipped_limit`.
- `comparison_status`: `matched`, `no_match`, `incomplete` (truncated page: "no match in the retrieved portion"),
  `not_compared`.
- `retrieved_at` is API retrieval during this scan, not the origin's publication or crawl time; provider caches are
  possible. `provider_content_timestamp` is the provider-reported date.
- Fetched text is stored once per content hash. Results are persisted as a discovery snapshot that can be replayed
  offline (`mode: "snapshot"`); replayed content is labeled cached and no search runs.
- A discovered exposure is never resolved because a later search omits it. Its recheck fetches the cited URL directly.

## Failure behaviour

| Outcome | Meaning | Coverage |
|---|---|---|
| `search_failed` | Every search failed. Discovery is inconclusive. | `discovery_search_failed` |
| `no_candidates` | Searches succeeded but returned nothing fetchable. Shown as "no candidate sources found", never "no leak". | `no_candidate_sources_found` |
| `partial_search` | Some searches failed. Fetched sources are compared; coverage is partial. | `some_searches_failed` |
| `candidates_found` | All searches succeeded. | per source |
| `budget_exhausted` | No search could run within the request budget. | `discovery_budget_exhausted` |
| `reused_recent_results` | The same files were scanned recently; remembered pages were rechecked without searching. | per source |

Provider errors are shown with the query that failed. Local risk review completes even when discovery fails.

## Benchmarking

Presets are measured, not assumed. A benchmark case is an approved public identity, a reference document that may be
stored, known public URLs containing it, and a negative control. `server/examples/preset_benchmark.py record` runs one
live scan per case × pack through the API and the isolated worker, saving search metadata, per-source status and
locally computed facts (whether a page mentions the company, which uploads matched), never page text. `score`
recomputes metrics offline:

- target recall: share of known copies returned;
- match yield: matching pages per page fetched;
- noise rate: fetched pages that never mention the display name, alias or domain;
- cost: provider requests and elapsed time.

Known copies are used only for scoring; they are never sent to a provider or injected into results. Template wording
may not contain words taken from a reference document or target URL. A case counts as search-discoverable only after a
recorded run returned it. Cases, results and per-scan records: [benchmark/README.md](benchmark/README.md).

## Limitations

- Discovery shows what the approved queries returned at search time. It is not exhaustive and does not prove company
  attribution.
- For companies with heavy leak coverage, identity-only queries return the company's leak coverage in general, not a
  specific leak. Narrowing further would require words from the document, which is not allowed. Aliases (for example
  product names) are the available lever.
- Search providers index few GitHub forks; copies held only in forks are rarely returned.
- Tavily `exact_match` on a formal name can filter out articles that use the everyday name. Exa has no exact-phrase
  option.
- Newly published pages are not returned until providers index them.
- Ten of the fifteen v3 presets are experimental.
