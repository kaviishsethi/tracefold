# Gitleaks secret leads

Tracefold uses [Gitleaks](https://github.com/gitleaks/gitleaks) as an extra source of secret leads alongside its own `secret_literal` rule. Gitleaks has a much larger rule set (hundreds of provider formats). Tracefold keeps its own job: evidence locations, masking, model review, fix-and-recheck and shared findings across the app and MCP.

A Gitleaks hit is a format- and entropy-based lead, not proof that a credential is real or active. Tracefold never tests credentials.

## Why Gitleaks and not TruffleHog

TruffleHog's default "verification" sends each candidate secret to the provider's API to see if it works. That puts the secret itself on the network, which breaks the strict-private boundary. Gitleaks works offline. Tracefold also enforces offline operation with a sandbox rather than trusting the tool to stay offline.

## Privacy contract

| Concern | What the adapter does |
|---|---|
| Private text on disk | Text goes to Gitleaks through stdin only. No temporary copy of a document is written. |
| Network | macOS: `sandbox-exec` denies all network access, including loopback. Linux: `unshare --net` runs it in an empty network namespace. If neither works, Gitleaks does not run (unless `TRACEFOLD_GITLEAKS_ALLOW_UNSANDBOXED=1`). |
| File writes and reads | macOS: the sandbox denies all writes and denies reads of the home directory, the Tracefold data directory and `server/`, which holds `.env`. |
| Provider keys | The process starts with an empty environment (only `PATH`), so Exa/Tavily keys are not inherited. |
| Config injection | Gitleaks runs in an empty temporary working directory with its built-in rules, so a `.gitleaks.toml` or `.gitleaksignore` in the scanned material is never honoured. |
| Tool output | stdout (which contains the matched secret) is parsed in memory only. stderr is discarded and never logged. |
| Storage | Secret values travel only in `secret_values`, which is never persisted. Findings carry a masked preview (`AKIA…(20 chars)`). Model input is masked and model output is scrubbed, as for built-in rules. A test scans the data directory to confirm the raw value never lands there. |
| Binary integrity | The binary's SHA-256 is recorded. Set `TRACEFOLD_GITLEAKS_SHA256` to pin it; on a mismatch Gitleaks does not run. |
| Versioning | Check versions include the Gitleaks version, for example `rules_v1/gitleaks_secret@1+gitleaks-8.30.1+adapter1`. After an upgrade, older findings recheck as `inconclusive` (`check_version_changed`) instead of being cleared by different rules. |

Gitleaks' reported columns are byte-based and inconsistent between lines, so Tracefold doesn't use them. It finds each secret again in its own in-memory text, within the reported lines. A lead that can't be found there is reported as `gitleaks_lead_not_located`, never invented.

## Duplicates

When a Gitleaks hit overlaps a built-in `secret_literal` hit, the two are merged into one finding. The built-in finding keeps its identity, and its masking widens to cover the Gitleaks span; for example, the whole private-key body rather than only the `BEGIN` line. The Gitleaks rule name is recorded in `meta.gitleaks_rules`. Only hits the built-in rules miss become `gitleaks_secret` findings.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `TRACEFOLD_GITLEAKS` | `auto` | `auto`: use Gitleaks if installed, otherwise report `gitleaks_secret` coverage as partial. `required`: missing or failing Gitleaks makes the `local_risk` check `partial` (`secret_scanner_incomplete`). `off`: rule coverage `not_requested`. |
| `TRACEFOLD_GITLEAKS_PATH` | `PATH`, then Homebrew/`/usr/local`/`/usr/bin` | Explicit binary path. |
| `TRACEFOLD_GITLEAKS_SHA256` | unset | Pin the binary. |
| `TRACEFOLD_GITLEAKS_ALLOW_UNSANDBOXED` | unset | Set to `1` to run without a network sandbox. This weakens the strict-private claim. |

Each scan records `versions.secret_scanner` and `summary.secret_scanner` (mode, version, files scanned, leads, unlocated leads).

Install on macOS with `brew install gitleaks`. Tests: `uv run pytest -q tests/test_m9_gitleaks.py`. The real-binary and sandbox tests run when Gitleaks is installed.

## Limits

- On Linux, `unshare` isolates the network but does not restrict file access. Run the engine under a dedicated user or a container if that matters.
- Only built-in Gitleaks rules are used. Custom organisation rules would need a reviewed, pinned config file added to the adapter.
- Git history is not scanned. Only the captured file versions are.
- No encryption at rest is added by this change. The findings store remains plaintext SQLite, without raw secret values.
