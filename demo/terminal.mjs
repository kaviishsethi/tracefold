// A real terminal in a browser page (xterm.js over a WebSocket to node-pty), so a command-line session can be
// recorded like any other clip. Everything stays on this machine (127.0.0.1).
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import pty from "node-pty";
import { WebSocketServer } from "ws";

const require = createRequire(import.meta.url);
const XTERM_JS = readFileSync(require.resolve("@xterm/xterm/lib/xterm.js"));
const XTERM_CSS = readFileSync(require.resolve("@xterm/xterm/css/xterm.css"));

const PAGE = (cols, rows) => `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/xterm.css"><script src="/xterm.js"></script>
<style>html,body{margin:0;height:100%;background:#0a0c0c}#wrap{height:100%;display:flex;align-items:center;justify-content:center}
#win{background:#111414;border:1px solid #262b2a;border-radius:12px;padding:16px 18px 18px;box-shadow:0 20px 60px rgba(0,0,0,.6)}
#bar{display:flex;gap:7px;margin:0 0 12px 2px}#bar i{width:11px;height:11px;border-radius:50%;background:#2c3231;display:block}</style>
</head><body><div id="wrap"><div id="win"><div id="bar"><i></i><i></i><i></i></div><div id="term"></div></div></div>
<script>
  const term = new Terminal({ cols: ${cols}, rows: ${rows}, fontSize: 14, lineHeight: 1.15, cursorBlink: true, allowProposedApi: true,
    fontFamily: "Menlo, Monaco, 'SF Mono', monospace", theme: { background: "#111414", foreground: "#e8eceb" } });
  term.open(document.getElementById("term"));
  const ws = new WebSocket("ws://" + location.host + "/pty");
  ws.onmessage = (e) => term.write(e.data);
  term.onData((d) => ws.readyState === 1 && ws.send(d));
  window.__term = term;
  window.__text = () => { const b = term.buffer.active; let s = ""; for (let i = 0; i < b.length; i++) s += (b.getLine(i)?.translateToString(true) ?? "") + "\\n"; return s; };
</script></body></html>`;

/** The environment without settings inherited from a parent Claude Code session. */
function cleanEnv() {
  return Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(CLAUDECODE|CLAUDE_CODE_|CLAUDE_AGENT_SDK)/.test(k)));
}

export function startTerminal({ cmd, args, cwd, env = {}, cols = 108, rows = 30, port = 4319 }) {
  const server = createServer((req, res) => {
    if (req.url === "/xterm.js") return res.writeHead(200, { "content-type": "text/javascript" }).end(XTERM_JS);
    if (req.url === "/xterm.css") return res.writeHead(200, { "content-type": "text/css" }).end(XTERM_CSS);
    res.writeHead(200, { "content-type": "text/html" }).end(PAGE(cols, rows));
  });
  const wss = new WebSocketServer({ server, path: "/pty" });
  let proc = null;
  wss.on("connection", (socket) => {
    proc = pty.spawn(cmd, args, { name: "xterm-256color", cols, rows, cwd,
      env: { ...cleanEnv(), TERM: "xterm-256color", COLORTERM: "truecolor", ...env } });
    proc.onData((d) => socket.readyState === 1 && socket.send(d));
    proc.onExit(() => socket.close());
    socket.on("message", (m) => proc?.write(m.toString()));
    socket.on("close", () => { try { proc?.kill(); } catch {} });
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve({
    url: `http://127.0.0.1:${port}/`,
    close: () => { try { proc?.kill(); } catch {} ; wss.close(); server.close(); },
  })));
}
