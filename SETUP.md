# Set up Tracefold

For a person or a coding agent. Run these from the repository root, in order. Each step says how to check it worked.
Needs Python 3.11+ with [uv](https://docs.astral.sh/uv/), Node 20+, and Git.

## 1. Configure everything

```bash
cd server && uv sync && uv run tracefold quickstart --root /path/to/the/folder/to/protect \
  --company "Your Company, Inc." --domain yourcompany.com --reply-to legal@yourcompany.com
```

`--company` signs takedown requests (with `--reply-to`) and approves the company's public name for discovery; with an
`EXA_API_KEY` or `TAVILY_API_KEY` in `server/.env` it also creates a first discovery plan. Add `--public-url https://...`
(repeatable) for specific public pages to check. Re-running is safe: it keeps the workspace, identity and plan, and
issues new tokens.

Check: the output ends with "Next, each in its own terminal". It wrote `frontend/.env.local` and
`~/.config/tracefold/mcp.json`. It never prints tokens; don't print those files.

## 2. Start the engine (leave it running)

```bash
cd server && uv run tracefold serve --port 8787
```

Check: `curl -s http://127.0.0.1:8787/v1/health` prints `{"status":"ok"}`.

## 3. Start the web app (leave it running)

```bash
cd frontend && npm install && npm run dev
```

Check: open http://localhost:3000/scan. It shows "Drop files to check" with no setup warning. If port 3000 is taken,
use `npm run dev -- --port 3100`.

## 4. Connect your coding assistant (optional)

```bash
cd adapters/mcp && uv sync && uv run tracefold-mcp check
claude mcp add tracefold -- uv run --directory "$PWD" tracefold-mcp
```

Check: `tracefold-mcp check` prints "engine reachable". In the assistant, the `tracefold` tools appear
(`scan_changes`, `get_findings`, `explain_finding`, `recheck_fix`, `list_scans`, `list_approvals`). The assistant can
scan, fix and recheck, and see what's waiting for approval, but can't approve takedowns or key changes; people do that
in the web app.

## Optional: takedowns and leaked keys

Approved takedown emails go to `server/data/outbox/` as `.eml` files until you configure sending. To set who signs them
and where they go:

```bash
cd server
uv run tracefold set-remediation-profile <workspace> --company "Your Company, Inc." --reply-to legal@yourcompany.com
uv run tracefold add-takedown-contact <workspace> forum.example --email abuse@forum.example
```

To disable leaked AWS keys after approval, put credentials for an IAM user allowed only `iam:GetAccessKeyLastUsed` and
`iam:UpdateAccessKey` in `server/.env` as `TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID` and
`TRACEFOLD_AWS_REMEDIATION_SECRET_ACCESS_KEY`, then restart the engine.

The workspace id is printed by step 1.
