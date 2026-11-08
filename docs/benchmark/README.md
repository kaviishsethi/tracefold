# Preset benchmark

Cases: [cases.json](cases.json). Script: [server/examples/preset_benchmark.py](../../server/examples/preset_benchmark.py)
(`record` runs live scans once and skips runs that already have a record; `score` recomputes metrics offline). Plan:
[PRESET_PLAN.md](../PRESET_PLAN.md).

## v3 results (live, November 8, 2026 UTC)

30 scans over 7 cases, each case × 4 packs, plus an `untested` group (`leaked_email`, `leaked_roadmap`,
`employee_forums`, `financial_filings`) on 4 cases, all with experimental presets included. Every scan used the real Exa
and Tavily APIs through the isolated worker. Full tables: [v3/scores.md](v3/scores.md). Per-scan records:
`v3/<case>__<pack>.json` (search metadata, per-source status, a locally computed "mentions the company" flag and which
uploads matched; no page text, no API keys).

| Case | Reference | Third-party copy found? | By |
|---|---|---|---|
| Nothing | reported memo excerpt | **Yes**: PhoneArena | `leak_news`, `leak_news_alias` (Exa) |
| CivicActions | security policy | **Yes**: `github.com/CivicActions/security-policy` | `security_docs` (Exa) |
| Sourcegraph | incident-response page | **Yes**: the GitHub repository copy (1,121-token match), **plus an unlisted Notion copy** (`sourcegraph.notion.site/…`, 228 + 141 tokens) and two other handbook pages sharing 32–34-token passages | `security_docs` (Exa, Tavily), `policy_copies` (Tavily) |
| GitLab | handbook security page | No third-party copy known; first-party copies excluded by default scope | – |
| GSA TTS | handbook security page | No: forks never returned | – |
| PostHog | handbook security page | No: forks never returned | – |
| Twitch | none (noise only) | n/a | – |

Acceptance checks from the plan:

| Check | Result |
|---|---|
| Every known third-party copy returned by ≥ 1 pack | **Partial**: 3 of 5 cases with a third-party target (Nothing, CivicActions, Sourcegraph); missed for GSA TTS and PostHog forks |
| Negative controls never match | **Pass**: 0 negative matches in 30 scans |
| ≤ 40 provider requests per scan, within the deadline | **Pass**: 12–32 requests, 4.6–20.8 s |
| Each shipped preset finds a benchmark target on ≥ 1 provider | 4 presets pass and are `benchmarked`; 10 stay `experimental` |
| Pack noise rate ≤ 40% | Mostly met; fails for leak packs on companies without leak coverage (CivicActions 100%, GSA TTS untested 45%) and `financial_filings` (80%+) |

Status (in `tracefold/discovery/presets.py`, `BENCHMARK_VERSION = "v3-2026-11-08b"`). A preset is benchmarked when, on
at least one provider, it returned a page outside the company's own domain that matched a reference document locally,
with no negative-control match:

- **Benchmarked:** `leak_news`, `leak_news_alias`, `security_docs`, `policy_copies`. Packs use only these by default
  (`leak_watch` fully, `document_copies` and `broad_triage` partly; `code_exposure` needs `include_experimental`).
- **Experimental:** the other 10. All ran at least 4 searches and none returned a matching page. `financial_filings` is
  mostly noise (80%+) and is a candidate for removal. `code_hosts_name`/`code_hosts_domain` have the lowest noise (0–5%)
  but never surfaced the forks that hold copies.
- **Legacy:** `internal_docs`, `source_config` and the v1/v2 presets stay resolvable but are in no pack.

What the numbers say:

- **Policy and security-document presets carry most of the value** for republished documents. Leak presets work only
  when press coverage exists.
- **Tavily now contributes.** It found the Sourcegraph copies (`security_docs`, `policy_copies`), but none of the leak
  targets: `exact_match` on a formal name (e.g. "Nothing Technology") filters out articles that use the everyday name.
- **Forks are hard to reach by search.** GitHub forks of the GSA TTS and PostHog handbooks were never returned by any
  preset, including the code-host ones. Search providers index few forks; this is a limit of search-based discovery.
- **Discovery found copies nobody listed:** the Sourcegraph Notion page, and earlier the CivicActions GitHub copy.
- **The noise metric is approximate** (pages that never mention the display name, alias or domain).

## Mock leak cases: real companies, simulated internal docs (November 8, 2026 UTC)

Invented internal-style documents for real companies, each containing short (≤ 15 words) passages that are publicly
available, with sources in `docs/demo-pairs/mock-leaks/*/README.md`. They are simulations, never real company material.
Source pages were chosen by an independent web search before any discovery run.

> **November 8, 2026:** only the Apple memo mock is still kept (`docs/demo-pairs/mock-leaks/apple_memo`, case
> `mock_apple_memo`). The spec-sheet mocks and the Google and Samsung memo mocks never matched, so their files and cases
> were removed; the results below and the `v3/` records for them are kept as history. The GSA TTS pair (0 matches in every run) and the
> Twitch discovery-only case (no upload, so it cannot match) were removed the same day.

**Spec-sheet mocks (Apple iPhone 18 Pro, Samsung Galaxy S27 Ultra, Google Pixel 11): 0 matches in 12 scans.** Each
quoted one outlet's own prose. With the product name as alias, the new `product_leaks` preset returned exactly on-topic
leak coverage (MacRumors, Macworld, CNET, The Verge, Android Central, Android Authority; 0–5% noise), but other outlets'
articles, which use different words. Verbatim matching can only fire on text that is actually repeated.

**Memo mocks: built the realistic way.** A real leaked document spreads as its own sentences quoted across sites, so these
mocks use passages that ≥ 2 independent outlets quote word for word (found by comparing 13-word sequences across pages):

| Case | Memo | Result |
|---|---|---|
| Apple | Tim Cook's 2021 memo on leakers | **Found.** `leak_news` (Exa) returned 9to5Mac's article and `leaked_email` (Exa) returned The Verge's original report, both pages not on the known list; both mock passages matched (13–14 tokens) |
| Google | Pichai's 2024 goals memo | Not found. Search returned other leaked Google memos (layoffs, hiring slowdown, diversity goals) |
| Samsung | Jun Young-hyun's 2024 chip memo | Not found. Search returned other Samsung leak stories (ChatGPT ban memo, Q2 staff memo, trade-secret cases) |

Negative controls matched nothing. `leaked_email` is now `benchmarked` (`BENCHMARK_VERSION = "v3-2026-11-08c"`); `product_leaks`
stays experimental (on-topic, no verbatim target yet).

The limit this shows: for companies with many leaks, queries built only from the public identity return the company's
leak coverage, not the specific leak. Narrowing further would need words from the document itself, which the privacy
design forbids sending. Product names as aliases and date windows are the allowed levers.

## Planted demo copy (Northstar Demo)

A synthetic page for the fictional "Northstar Demo" (`server/fixtures/northstar/northstar-demo-public-copy.md`, labelled
as demo material) was published on 2026-11-08 as
<https://gist.github.com/kaviishsethi/a899f787988efa1f16cbb1fdb6303889>. A run minutes later
([planted/2026-11-08/](planted/2026-11-08/)) did **not** return it: providers had not indexed it yet. Re-check later
with:

```bash
cd server && uv run python examples/preset_benchmark.py record --cases ../docs/benchmark/cases.json --only northstar_planted --out ../docs/benchmark/planted/$(date -u +%F)
```

A hit proves the pipeline finds a known planted page. It is not a discovered leak and must be presented that way.
