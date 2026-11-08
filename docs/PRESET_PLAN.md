# Discovery presets v3: plan

Status: steps 1–6 implemented (`server/tracefold/discovery/presets.py`, benchmark in `docs/benchmark/`). Live benchmark (7 cases, 30 scans): 4 of 14 presets benchmarked; see docs/benchmark/README.md. Builds on [COMPANY_DISCOVERY_PLAN.md](COMPANY_DISCOVERY_PLAN.md) and the five live runs in
[demo-pairs/DISCOVERY_RESULTS.md](demo-pairs/DISCOVERY_RESULTS.md).

Goal: at least 10 fixed presets that reliably return third-party public copies of a company's material, measured
against a benchmark, without weakening the privacy rule that queries come only from the approved public identity.

## 1. What the live runs showed

| Observation | Evidence | Consequence for presets |
|---|---|---|
| Identity queries return the company's own footprint | Homepages, LinkedIn, Wikipedia, Tavily company pages, Companies House in every identity run | Exclude the official domain and a fixed list of profile/aggregator sites by default |
| Generic words drift off-topic for big or generic names | GitLab "internal memo document" → Merriam-Webster, IRS, Microsoft C# docs; "Nothing" is an English word | Use Tavily `exact_match`; phrase Exa queries as descriptions of the page wanted |
| Leak-focused wording works | `"Nothing Phone" leaked internal memo` found the PhoneArena copy at rank 2 on both providers | Keep leak-report presets; add variants by document type |
| Copies live on code hosts | CivicActions match came from `github.com/CivicActions/security-policy`; GitLab results included a handbook blob on gitlab.com | Add code-host presets that search for the name and the official domain |
| Known public pages can be missed | GitLab's security handbook and CivicActions' guidebook page were never returned | Add a policy/handbook preset; measure recall instead of assuming it |
| The same article appears twice | Twitch: GitGuardian URL with and without a trailing slash | Out of scope for presets; handle in canonicalization separately |

## 2. Rules every preset must follow (unchanged)

- Inputs are only `display_name`, `official_domain`, `public_aliases` and the user's scope choice. No document text,
  filenames, hashes, model output or follow-up queries derived from results.
- Fixed, versioned templates (`company_queries_v3`). A plan stores the exact rendered requests, so a preview shows
  precisely what leaves the machine.
- Results are candidates only. Findings still come only from local matching over fully extracted text.
- Presets express search intent. They never guarantee coverage; a no-match is still "no match among the pages returned".

## 3. Engine changes the presets need

Today a planned search has one query string and `include_domains`. To build good presets, a template must be able to set:

| Field | Exa `/search` | Tavily `/search` | Why |
|---|---|---|---|
| Per-provider query text | `query` (Exa is neural: describe the page) | `query` (keyword) | One wording does not suit both providers |
| Exact phrase | not available (`includeText` is deprecated and approximate) | `exact_match: true` | Stops "Nothing"/"Twitch"/"Square" matching the common word |
| Exclude domains | `excludeDomains` | `exclude_domains` (max 150) | Drop the company's own site and known noise |
| Include domains | `includeDomains` | `include_domains` + `include_domains_mode` (`restrict` or `prefer`) | Code hosts, document sites, forums |
| Category | `category` (`news`, `publication`, `financial report`, …) | `topic` (`general`, `news`) | Leak coverage is mostly news |
| Date window | `startPublishedDate` | `time_range` or `start_date` | Optional "recent only" packs for monitoring |

Changes:

1. **Template schema v3.** Each preset defines `exa` and `tavily` renderings (`query`, `category`/`topic`,
   `exact_match`, `include_domains`, `include_domains_mode`, `exclude_official_domain`, `exclude_noise`). Rendering stays
   deterministic and is stored in the plan.
2. **Worker validation.** Extend the strict search schema to accept only these fields with bounded values: category and
   topic from fixed enums, ≤ 20 domains per list, booleans only. `category: "company"` is never used (it rejects date
   filters and returns profile pages).
3. **Noise list.** A versioned `NOISE_DOMAINS` list, excluded by default: `linkedin.com`, `wikipedia.org`,
   `tavily.com`, `crunchbase.com`, `trustpilot.com`, `glassdoor.com`, `merriam-webster.com`, `dictionary.com`,
   `youtube.com`, `facebook.com`, `instagram.com`, `x.com`, `twitter.com`. Extended only through measured noise (§6).
   The `employee_forums` preset is exempt from excluding forum hosts it targets.
4. **Official domain excluded by default, as a visible scope choice.** Third-party copies are what discovery is for;
   the official domain stays an identity hint inside queries, and searches are never restricted to it. Exclusion is a
   plan-level scope option (`exclude_official_domain`, default on) shown in the preview, so the user still chooses what
   is searched. `NOISE_DOMAINS` exclusion is shown the same way.
5. **Budget.** Today a plan allows 4 searches × 5 results. Ten presets don't fit, so add a second shape: up to
   **8 searches × 3 results** (24 candidates, ≤ 20 unique pages fetched). The discovery plan asked for the first live
   runs to be measured before scope grows; five runs used 19–24 provider requests, 5.6–16.2 s and 126–344 KB of
   responses, so the 8×3 shape fits the existing limits with headroom. Worst case stays within the 40-request cap:
   8 searches + 20 extractions + 12 fallbacks. Keep "extraction capacity is reserved before searching". Plans pick one
   shape; the preview shows which.
6. **Packs.** Named, versioned bundles of presets × providers that fit a budget shape, so users choose an intent
   instead of assembling searches. Packs are presentation only; the plan still stores every rendered search. Creating a
   plan from a pack needs the `configure` capability like any plan; MCP can only select an already approved plan and
   cannot widen it based on workspace content. No pack runs automatically on edits or on a schedule unless a user
   approves that separately.
7. **User scope still applies.** If the user picks `selected` scope, every preset is limited to the chosen site groups.
   A preset with its own site list (6, 7, 8, 9, 13) is intersected with that choice; an empty intersection rejects the
   preset at plan creation with a clear error. New site groups are added for the presets: `code` (github.com,
   gist.github.com, gitlab.com, bitbucket.org), `documents` (scribd.com, issuu.com, docdroid.net, yumpu.com,
   slideshare.net, speakerdeck.com) and `forums` (reddit.com, teamblind.com, news.ycombinator.com), alongside the
   existing `github`, `reddit` and `paste`.

## 4. Preset catalog (14)

`{name}` = display name, `{alias}` = first public alias, `{domain}` = official domain. Tavily queries use
`exact_match: true` unless noted. "Excl." = official domain + noise list excluded.

| # | Preset | Finds | Exa rendering | Tavily rendering | Scope | Needs |
|---|---|---|---|---|---|---|
| 1 | `leak_news` | News coverage quoting a leaked internal document | `news article quoting a leaked internal memo from {name}`, `category: news` | `"{name}" leaked internal memo`, `topic: news` | Excl. | name |
| 2 | `leak_news_alias` | Same, under the product or brand name | as 1 with `{alias}` | as 1 with `{alias}` | Excl. | alias |
| 3 | `leaked_email` | Published CEO/all-hands emails | `full text of an internal email sent to {name} employees`, `category: news` | `"{name}" email to employees full text` | Excl. | name |
| 4 | `leaked_roadmap` | Reported roadmaps, plans, strategy docs | `leaked {name} product roadmap or strategy document`, `category: news` | `"{name}" leaked roadmap` | Excl. | name |
| 5 | `leaked_deck` | Investor/board/internal slides posted publicly | `internal presentation slides from {name}` | `"{name}" internal presentation slides` | Excl.; Tavily `include_domains` slideshare.net, speakerdeck.com, scribd.com with `prefer` | name |
| 6 | `doc_sharing` | Documents uploaded to sharing sites | `document published by {name}` | `"{name}"` | `include_domains` scribd.com, issuu.com, docdroid.net, yumpu.com, slideshare.net (`restrict`) | name |
| 7 | `code_hosts_name` | Repos, gists and issues naming the company | `source code repository from {name}` | `"{name}"` | `include_domains` github.com, gist.github.com, gitlab.com, bitbucket.org (`restrict`) | name |
| 8 | `code_hosts_domain` | Code and config files that mention internal hostnames | `configuration file referencing {domain}` | `"{domain}" config` | code hosts as 7 (`restrict`); official domain **not** excluded from the query text | domain |
| 9 | `paste_sites` | Pastes naming the company or domain | `{name} {domain}` | `"{name}" {domain}` with `exact_match: false` (no Boolean `OR`: providers don't guarantee operator support) | `include_domains` pastebin.com, paste.ee, rentry.co, ghostbin.cloud (`restrict`) | name |
| 10 | `policy_copies` | Republished policies, handbooks, procedures | `{name} employee handbook or company policy document` | `"{name}" policy handbook procedure` | Excl. (third-party copies only) | name |
| 11 | `security_docs` | Security policies, incident-response plans, audit reports | `{name} security policy or incident response plan document` | `"{name}" security policy incident response` | Excl. | name |
| 12 | `breach_coverage` | Reporting on breaches and source-code leaks | `report on a data breach or source code leak at {name}`, `category: news` | `"{name}" breach source code leak`, `topic: news` | Excl. | name |
| 13 | `employee_forums` | Employee posts discussing internal material | `{name} employee discussion about internal documents` | `"{name}" employees internal` | `include_domains` reddit.com, teamblind.com, news.ycombinator.com (`restrict`) | name |
| 14 | `financial_filings` | Filings or reports quoting internal documents | `{name} financial report`, `category: financial report` | `"{name}" annual report internal`, `topic: finance` | Excl. | name |

Existing presets: `identity` stays (disambiguation, low yield). `internal_docs` and `source_config` are retired after
the benchmark confirms the replacements (3, 10 and 7/8) beat them. `leak_reports` and `alias_leak_reports` become 1 and 2.

Packs (budget shape in brackets):

| Pack | Presets × providers | Use |
|---|---|---|
| `leak_watch` [4×5] | `leak_news`, `leak_news_alias` × Exa + Tavily | Reported leaks (the Nothing case) |
| `document_copies` [8×3] | `leaked_deck`, `doc_sharing`, `policy_copies`, `security_docs` × both | Republished documents (CivicActions, GitLab) |
| `code_exposure` [8×3] | `code_hosts_name`, `code_hosts_domain`, `paste_sites`, `breach_coverage` × both | Source code and config |
| `broad_triage` [8×3] | `leak_news`, `leaked_email`, `policy_copies`, `code_hosts_name` × both | First run for a new company |

## 5. Benchmark

Every preset needs at least one benchmark case before it ships. A case = approved public identity + a reference document
we may store + one or more **known public URLs** containing it + a negative control.

| Case | Reference | Known public copies | Exercises |
|---|---|---|---|
| Nothing | memo excerpt (have) | phonearena.com article | 1, 2, 4 |
| CivicActions | full security policy (have) | guidebook page, `github.com/CivicActions/security-policy` | 7, 10, 11 |
| GitLab | security handbook page (have) | handbook.gitlab.com page, gitlab.com blob | 7, 8, 10, 11 |
| 3–5 more open handbooks | e.g. companies publishing handbooks under open licenses on GitHub | site + GitHub mirror | 7, 10, 11 |
| 2–3 reported leaks | short excerpts (≤ ~30 words) quoted in news, licensing reviewed | named articles | 1, 3, 4, 12 |
| Discovery-only | none (Twitch) | none | noise rate only |

Store only what the licence or fair quotation allows, with attribution, as the existing pairs do. As the discovery plan
requires, label each case honestly: an openly published handbook proves public availability, not a leak; a reported
excerpt is a short reference, not the original document. A case counts as search-discoverable only after a recorded run
actually returned it. Presets 5, 6, 9, 13 and
14 may have no reliable public case; if none can be found after a bounded search, they ship disabled by default and say so.

Metrics per preset and per pack, per provider:

- **Target recall@k**: share of known copies returned within the results requested.
- **Match yield**: unique pages that produce a ≥ 12-token match / pages fetched.
- **Noise rate**: fetched pages with no mention of the company name or domain (computed locally on fetched text).
- **Cost**: provider requests, response bytes, seconds.
- **Stability**: same query re-run 24 h later; share of URLs still returned.

Acceptance thresholds (proposed; adjust once baselines exist):

- Every known copy is returned by at least one shipped pack for its case.
- Each shipped preset finds its benchmark target on at least one provider within its result limit.
- Pack noise rate ≤ 40% (current identity/internal_docs runs are well above this on GitLab).
- No pack exceeds 40 provider requests or the 5-minute deadline.
- Negative controls never match.

## 6. Evaluation procedure

1. **Record once, replay many.** Add a benchmark script that runs each case live once per template version and saves the
   search responses (URL, title, rank, dates only) plus extracted text hashes. Template tweaks are scored offline
   against recorded responses where the query did not change; a changed query needs a new live run.
2. **Live budget.** Each live case run is ≤ 40 provider requests. A full benchmark of ~10 cases × 4 packs is ≈ 1,600
   requests at most; run it per template version, not per commit.
3. **Noise list changes need data.** A domain joins `NOISE_DOMAINS` only after it appears as noise in ≥ 2 cases and is
   never a known copy host.
4. **No tuning to targets.** Template text may not contain words taken from a reference document or target URL. Review
   every template diff against this rule; record why each wording changed.
5. **Report.** Extend `DISCOVERY_RESULTS.md` with a per-preset table (recall, yield, noise, cost) for each template
   version, including misses.

## 7. Implementation order

1. Template schema v3, per-provider rendering, exclude/noise lists, new worker fields and validation. Tests: strict schema
   rejects unknown fields and out-of-enum values; rendered requests are byte-identical across different uploads;
   `exact_match`/`category` appear only where the template sets them.
2. Budget shape 8×3 with extraction reservation. Tests: request accounting never exceeds 40; searches skipped before
   extraction capacity is lost.
3. The 14 presets and 4 packs, plus plan-preview fields showing provider-specific requests and excluded domains.
4. Benchmark cases (add 3–5 open handbooks and 2–3 reported-leak excerpts with licence notes) and the record/replay
   script.
5. Live benchmark for v3; set thresholds from results; disable presets that fail with no benchmark target.
6. Retire `internal_docs`/`source_config` if the replacements win; keep old template versions resolvable so stored plans
   replay.
7. Update `ENGINE_API.md`, regenerate OpenAPI, and show packs first in the app with the exact queries one click away.

## 8. Consistency with the discovery plan

Checked against [COMPANY_DISCOVERY_PLAN.md](COMPANY_DISCOVERY_PLAN.md):

| Discovery-plan rule | How this plan keeps it |
|---|---|
| Templates are search intent; Boolean syntax isn't guaranteed | No `OR`/`AND` in any template (preset 9 fixed) |
| Official domain is a hint; never restrict every search to it | Used in query text; excluded from results only as a visible, user-controlled scope option |
| User chooses broad or selected public domains | User scope intersects every preset's site list (§3.7) |
| Measure live runs before increasing scope | 8×3 shape justified by the five recorded runs (§3.5) |
| ≤ 40 requests, extraction reserved first, one fallback, no retry tree | Unchanged; worst case 8 + 20 + 12 = 40 |
| MCP can't approve identity or broaden plans; no discovery on every edit | Packs need `configure`; nothing runs automatically (§3.6) |
| No document-derived terms, no model-generated follow-ups | Unchanged; plus the no-target-words rule for template wording (§6.4) |
| Never inject a desired URL; show misses | Benchmark records misses; targets are used only for scoring |
| Public policy ≠ leak; don't claim discoverability untested | Case labeling rule in §5 |
| No CVE search or takedown submission | None added; `breach_coverage` only finds reporting |

## 9. Risks

- **Over-fitting.** Wording that wins on 3 companies may fail on the next. Mitigation: the no-target-words rule, plus
  discovery-only cases (Twitch-like) to watch noise.
- **Generic names.** `exact_match` helps Tavily only. For Exa, rely on descriptive queries plus the alias and domain.
  Profiles for generic names should include a distinctive alias; the UI should warn when the display name is a common
  word.
- **Investigation footprint.** More presets mean more queries describing the user's interest (e.g. "leaked memo")
  reach providers. The plan preview and privacy notice must show this per pack.
- **Site terms.** Code, paste and forum presets only search and fetch public pages through providers; no logins, no
  scraping beyond the extraction APIs, no link following.
- **Provider drift.** Category values and filters change; re-verify fields against provider docs at implementation time.
