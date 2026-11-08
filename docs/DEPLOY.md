# Running Tracefold in your own network (VPC)

Tracefold runs entirely inside your network: the web app, the engine and the local model. Nothing is hosted by us.
Outbound traffic is only what the engine's gateway allows (search and page fetches for public checks, and optional
email or AWS calls you turn on), and every request is logged per scan.

## What runs

| Service | What it does | Port |
|---|---|---|
| `web` | The web app. The only port you publish, behind your own load balancer or VPN. | 3000 |
| `engine` | Scans, findings, approvals, schedules. Needs a client token on every request. | 8787, private |
| `ollama` | The local model that reviews flagged text. The engine shares its network so the model stays at 127.0.0.1, which the engine requires before sending file text to a model. | private |

State lives in one volume (`tracefold-data`): the SQLite database, page memory, the outbox, and private copies of
files you schedule. Uploaded files are otherwise kept in memory only.

## Steps

On a VM in your VPC with Docker:

```bash
git clone https://github.com/kaviishsethi/tracefold && cd tracefold
```

```bash
docker compose up -d ollama engine
```

```bash
docker compose exec ollama ollama pull qwen2.5:7b-instruct
```

Create the workspace and a token for the web app. The token is printed once:

```bash
docker compose run --rm engine tracefold add-workspace ws_main --name "Your company"
```

```bash
docker compose run --rm engine tracefold add-client web-app --workspace ws_main
```

Put that token in a `.env` file next to `docker-compose.yml` as `TRACEFOLD_APP_TOKEN=...`, then start the web app:

```bash
docker compose up -d web
```

Search keys and optional settings go in the engine's data volume as `/data/.env`, for example `TAVILY_API_KEY=...`.
To turn off leaked AWS keys, run `tracefold connect-aws` on a machine with your AWS CLI login and copy the two
`TRACEFOLD_AWS_REMEDIATION_*` lines into `/data/.env`.

## Coding assistants

Point the MCP adapter at the engine's private address with its own token (no `approve` capability):

```bash
docker compose run --rm engine tracefold add-client coding-assistant --workspace ws_main --caps submit,read,read_evidence,recheck,cancel
```

## Limits

- One engine instance per database (SQLite). Run it on one VM with a persistent volume; multiple engines behind a
  load balancer would need Postgres, which isn't built.
- On Linux the page-fetch worker runs without the macOS sandbox; the container is the isolation boundary. Keep the
  engine off the public internet.
- The web app has no login of its own yet: put it behind your SSO, VPN or an authenticating proxy.
