# Demo clip recorder

Records the web-app shots in `docs/DEMO_VIDEO.md` by driving the running app in a browser. Each clip is laid out at
1280×720 (so the interface reads large), scaled to 1080p, with a visible cursor. Output goes to `out/` (git-ignored).

```bash
npm install && npx playwright install chromium
node record.mjs --fresh        # all clips; --fresh deletes finished scans so clip 03 searches for real
node record.mjs 03 05          # only some clips
```

Needs the engine, web app and Ollama running, and an Exa or Tavily key. Clip 04 prepares a takedown draft from the
sample page list and clicks Save email, which writes the request to the local outbox (email sending stays off).
The Claude Code (MCP) and Wi-Fi-off shots are recorded by hand.
