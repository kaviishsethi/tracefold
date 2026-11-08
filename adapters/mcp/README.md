# Tracefold MCP adapter

A thin stdio MCP server that maps tool calls to the [engine HTTP API](../../docs/ENGINE_API.md). It holds no
findings, parses no files and calls no model: everything it returns comes from the engine, under the engine's
per-client disclosure policy. Architecture: [HTTP API and MCP mapping](../../docs/ARCHITECTURE.md#http-api-and-mcp-mapping).

## Tools

| Tool | Engine calls | Notes |
|---|---|---|
| `get_capabilities` | `GET /capabilities` | Read-only |
| `list_workspaces` | `GET /workspaces` | Also returns the configured default workspace |
| `scan_changes` | `POST /captures` + `POST /scans`, then polls `GET /scans/{id}` | `mode=changes` (Git baseline, untracked optional) or `mode=files`; `check_public_sources=<manifest_id>` adds public matching. Waits at most `wait_seconds` (≤25); long scans keep running |
| `get_scan` | `GET /scans/{id}` | Optional short `wait_seconds` |
| `cancel_scan` | `POST /scans/{id}/cancel` | Cooperative |
| `get_findings` | `GET /findings?scan_id=` (+ `GET /scans/{id}`) | Split into `public_exposure` / `local_risk`; `coverage_notes` states empty or incomplete sections in the engine's terms ("No match in N checked sources", "not requested", …) |
| `explain_finding` | `GET /findings/{id}` (+ `GET /evidence/{id}`) | Returns the stored explanation, never a new one. Evidence only if the grant allows it |
| `recheck_fix` | `GET /findings/{id}` + `POST /captures` + `POST /findings/{id}/rechecks` | Captures the finding's file (or `paths` when the path is withheld) and returns `still_detected` / `not_detected_in_checked_version` / `inconclusive` |
| `list_scans` | `GET /scans` | Read-only. Recent scans from every client, with where each came from |
| `list_approvals` | `GET /actions` | Read-only. Drafted takedowns and key shut-offs; a person approves them in the web app |

Engine errors pass through as tool errors carrying the engine's `{code, message, retryable}` plus
`http_status`. If the engine can't be reached, the tool error code is `engine_unreachable` or `engine_timeout`.

The host can't supply a server URL, token or workspace root. Those come from a local config file that only
the owner can read.

## Setup

1. Start and provision the engine ([server/README.md](../../server/README.md)). Register a Git repository as the
   workspace root and create a client grant for the adapter:

   ```bash
   cd server
   MCP_TOKEN=$(uv run tracefold add-client mcp-adapter --workspace ws_main --caps submit,read,read_evidence,recheck,cancel)
   # For a cloud-backed assistant, use minimal disclosure instead (no paths, explanations or evidence text):
   # MCP_TOKEN=$(uv run tracefold add-client cloud-assistant --workspace ws_main --caps submit,read,recheck --disclosure minimal)
   uv run tracefold serve --port 8787
   ```

2. Install the adapter and write its config (`~/.config/tracefold/mcp.json`, mode 600). The token is read from
   stdin, so it stays out of your shell history and the process list:

   ```bash
   cd adapters/mcp
   uv sync
   echo "$MCP_TOKEN" | uv run tracefold-mcp configure --workspace ws_main --base-url http://127.0.0.1:8787
   uv run tracefold-mcp check
   ```

3. Register it with the MCP host. Claude Code, for example (`.mcp.json` in the project, or `claude mcp add`):

   ```json
   {
     "mcpServers": {
       "tracefold": {
         "command": "uv",
         "args": ["run", "--directory", "/absolute/path/to/tracefold/adapters/mcp", "tracefold-mcp"]
       }
     }
   }
   ```

   Use `--config <path>` or `TRACEFOLD_MCP_CONFIG` for a non-default config location.

4. Add the [assistant working instructions](examples/assistant-instructions.md) to the project (for example in
   `CLAUDE.md` or `AGENTS.md`) so the assistant scans before it reports work as complete. Those instructions only
   help with usability. The engine's grants and disclosure policy are what enforce access.

## Privacy boundary

Tool results go to whatever model the MCP host uses. For a strict-private setup, the host must run a local model,
and an operator has to set that up and verify it. Running this adapter locally doesn't make a cloud-backed host
private. For a cloud-backed host, give the adapter a `--disclosure minimal` grant and don't claim that nothing
private leaves the machine: finding titles, rule IDs and coverage still do.

## Tests

```bash
uv sync
uv run pytest -q
```

The tests start a real `tracefold serve` process, provisioned through its CLI with a temporary Git workspace. They
drive the adapter through an MCP client, both in-process and over stdio. They cover: change scan → findings →
explanation → fix → recheck, with the same finding seen by the upload-app client; public matching through a
fixture manifest; minimal-disclosure and missing-capability behaviour; preservation of engine error codes; and
config safety.
