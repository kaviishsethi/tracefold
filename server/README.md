# Tracefold engine (server)

The shared private scan engine behind the Tracefold upload app and MCP adapter. Both are thin HTTP clients
of this server; neither parses files, calls the model or keeps its own findings. Design:
[`docs/SHARED_ENGINE_PLAN.md`](../docs/SHARED_ENGINE_PLAN.md). Client guide: [`docs/ENGINE_API.md`](../docs/ENGINE_API.md).

## Quickstart (local, loopback only)

```bash
cd server
uv sync
export TRACEFOLD_DATA=$PWD/data TRACEFOLD_FIXTURES=$PWD/fixtures
uv run tracefold init
uv run tracefold add-workspace ws_main --name "Main" --root /path/to/a/local/folder
APP_TOKEN=$(uv run tracefold add-client upload-app --workspace ws_main)
MCP_TOKEN=$(uv run tracefold add-client mcp-adapter --workspace ws_main --caps submit,read,read_evidence,recheck,cancel)
uv run tracefold add-manifest ws_main sources_main examples/manifest.fixture.json
uv run tracefold serve --port 8787
```

Then, in another shell, run the documented flow that exercises every endpoint:

```bash
uv run python examples/walkthrough_flow.py --workspace ws_main --app-token "$APP_TOKEN" --mcp-token "$MCP_TOKEN" --workspace-root /path/to/a/local/folder
```

Tokens are printed once; only their SHA-256 hashes are stored. The server binds 127.0.0.1 and rejects
unexpected `Host`/`Origin` headers.

## Optional services

| Service | How to enable | Without it |
|---|---|---|
| Gitleaks secret leads | `brew install gitleaks`. Runs offline inside a network/write sandbox with an empty environment; `TRACEFOLD_GITLEAKS` (`auto`, `required` or `off`). See [`docs/GITLEAKS.md`](../docs/GITLEAKS.md). | Built-in secret rules only; `gitleaks_secret` rule coverage reports `gitleaks_not_installed`. |
| Local model review | Install Ollama, pull a model, set `TRACEFOLD_OLLAMA_MODEL` (default `qwen2.5:7b-instruct`) and optionally `TRACEFOLD_OLLAMA_URL` (must be loopback). Set `OLLAMA_NO_CLOUD=1` for the Ollama service. | Rule findings are published with `risk_review: unavailable`. |
| Company-name discovery | Same Exa/Tavily keys. Approve an identity (`POST company-profiles`) and a query plan (`POST query-plans`) with a client that has the `configure` capability, then scan with `public_discovery`. See `docs/ENGINE_API.md`. | Searches report `provider_not_configured`; discovery is inconclusive. |
| Exa / Tavily extraction | `EXA_API_KEY` / `TAVILY_API_KEY` in the environment or in `server/.env` (gitignored, loaded by `tracefold` commands); manifest entries with `"provider": "exa"` or `"tavily"` — see `examples/manifest.live.example.json`. | Those sources report `provider_not_configured`. `direct` and `fixture` providers still work. |
| Takedown email | Default `TRACEFOLD_MAIL_TRANSPORT=outbox` writes approved requests to `$TRACEFOLD_DATA/outbox/*.eml` and sends nothing. For real sending set `TRACEFOLD_MAIL_TRANSPORT=resend`, `RESEND_API_KEY` and `TRACEFOLD_MAIL_FROM` (a sender on a domain verified with Resend). | Approved takedowns land in the outbox. |
| AWS key disabling | `TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID` / `TRACEFOLD_AWS_REMEDIATION_SECRET_ACCESS_KEY` (optional `TRACEFOLD_AWS_REMEDIATION_SESSION_TOKEN`) for an IAM principal allowed only `iam:GetAccessKeyLastUsed` and `iam:UpdateAccessKey`. | Approving `disable_aws_key` returns 409 `aws_remediation_not_configured`. |

## Tests

```bash
uv run pytest -q                                   # offline suite (fixtures, fake loopback model, mock transports)
TRACEFOLD_LIVE=1 uv run pytest -q -m live          # real public fetch (+ Exa/Tavily if keys are set)
TRACEFOLD_OLLAMA=1 uv run pytest -q -m ollama -s   # real local model
```

Minimal IAM policy for the remediation principal:

```json
{"Version": "2012-10-17", "Statement": [{"Effect": "Allow",
  "Action": ["iam:GetAccessKeyLastUsed", "iam:UpdateAccessKey"], "Resource": "*"}]}
```

## Layout

```text
tracefold/
  api/        routes, auth, host/origin checks, error envelope (no detection logic)
  contracts/  Pydantic DTOs and enums (exported as openapi.json)
  services/   inputs, scans, findings, rechecks, versioned findings store
  jobs/       single runner, pipeline, stages
  inputs/     upload parsing, safe filesystem reader, Git change capture, in-memory capture registry
  parsing/    text/code and DOCX extraction with stable locations
  checks/     exact matcher, deterministic rules, sandboxed Gitleaks adapter
  analysis/   Ollama client, model review, evidence validation, output scrubbing
  discovery/  approved company identity, fixed query builder, search → validate → extract → compare
  retrieval/  isolated worker (direct/Exa/Tavily/fixture), snapshots, blob store
  gateway/    the only outbound HTTP path, with a redacted ledger
  storage/    SQLite migrations and repositories (the only SQL)
  policy/     tokens, grants, workspace authorization
  remediation/ approval-gated takedown requests and AWS key disabling (SigV4 via the gateway)
fixtures/     synthetic public/private test material
examples/     walkthrough flow and example manifest
```
