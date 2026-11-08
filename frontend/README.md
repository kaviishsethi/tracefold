# Tracefold web app

The upload platform and marketing site for Tracefold. It's a thin client of the engine in [`server/`](../server/README.md):
it never parses files, calls a model or keeps its own findings. The UI was carried over from Spillway (same components
and design tokens) with Tracefold content.

## Run it

1. Start and provision the engine (see `server/README.md`), and create a token for this app:

   ```bash
   cd server
   uv run tracefold add-client upload-app --workspace ws_main
   uv run tracefold serve --port 8787
   ```

2. Point the app at it in `frontend/.env.local` (git-ignored):

   ```bash
   TRACEFOLD_ENGINE_URL=http://127.0.0.1:8787
   TRACEFOLD_APP_TOKEN=tf_...
   ```

3. Run the app:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Open http://localhost:3000 for the site and http://localhost:3000/overview for the app.

## How it talks to the engine

The browser calls `/api/engine/*`, a same-origin route (`app/api/engine/[...path]/route.ts`) that adds the engine token
server-side and forwards to the engine's `/v1` API. The token never reaches the browser. Types and helpers for every
engine endpoint are in `lib/api.ts`.

## Pages

- Site: `/`, `/manifesto`, `/pricing`, `/enterprise`, `/security`, `/contact`
- App: `/overview`, `/scan` (upload or capture, then scan), `/scan/[id]`, `/findings`, `/findings/[id]` (evidence,
  recheck, review), `/actions` (approve takedowns and AWS key disables), `/egress` (outbound ledger per scan),
  `/discovery` (approve a public company identity, create query plans and preview the exact searches; needs the
  `configure` capability), `/sources`, `/settings`, `/onboarding`. `/scan` can use a source list or a discovery plan;
  `/scan/[id]` lists every page found, fetched and compared.

## Known gaps

- The engine has no list-scans endpoint, so recent scans are remembered per browser.
- Pricing figures were carried over from Spillway and need confirming.
