"""A tiny loopback HTTP server that imitates the Ollama endpoints Tracefold uses."""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "tracefold-test:latest"
DIGEST = "sha256:" + "ab12" * 16


class FakeOllama:
    def __init__(self, scenario: str = "good", installed: bool = True):
        self.scenario = scenario
        self.installed = installed
        self.requests: list[dict] = []
        self.counts: dict[str, int] = {}
        self.secret_to_echo: str | None = None
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj, status=200):
                body = json.dumps(obj).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/tags":
                    models = [{"name": MODEL, "model": MODEL, "digest": DIGEST}] if outer.installed else []
                    return self._send({"models": models})
                self._send({}, 404)

            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["content-length"])))
                outer.requests.append(data)
                content = outer.respond(data)
                if content is None:
                    return
                self._send({"message": {"role": "assistant", "content": content}, "prompt_eval_count": 321, "eval_count": 54})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()

    def respond(self, data: dict) -> str | None:
        user = data["messages"][1]["content"]
        evid = (re.search(r"Evidence ID: (ev_[0-9a-f]+)", user) or [None, None])[1]
        lines = re.search(r"Evidence lines: (\d+)-(\d+)", user)
        first = int(lines.group(1)) if lines else 1
        sc = self.scenario
        if user.startswith("TASK: investigate"):
            n = self.counts["context"] = self.counts.get("context", 0) + 1
            if sc == "slow":
                time.sleep(3)
            if sc == "fabricate":
                return json.dumps({"evidence_id": "ev_invented", "conditions": "x", "missing_context": "y",
                                   "suggested_fix": "z", "severity": "high", "severity_rationale": "r", "cited_lines": [9999]})
            if sc == "repair" and n == 1:
                return "this is not json"
            fix = "Log a masked value instead of the raw field."
            if sc == "echo_secret" and self.secret_to_echo:
                fix = f"Rotate {self.secret_to_echo} and move it to the vault."
            if sc == "echo_source":
                fix = "Replace the line logger.info login attempt user s password s username password with a masked call."
            return json.dumps({"evidence_id": evid, "conditions": "If production logs are shipped to a shared log service.",
                               "missing_context": "Log retention and access policy.", "suggested_fix": fix,
                               "severity": "high", "severity_rationale": "Credentials in logs are widely readable.",
                               "cited_lines": [first]})
        if user.startswith("TASK: act as a skeptical"):
            verdict = "supported"
            if sc == "dismiss" and "session_token" in user.split("Claim under review:")[1].split("\n")[0]:
                verdict = "dismissed"
            return json.dumps({"evidence_id": evid, "verdict": verdict,
                               "counterevidence": "No masking step is visible before the call." if verdict == "supported"
                               else "The token is a short-lived nonce in this code.",
                               "reason": "Judged from the lines shown.", "cited_lines": [first]})
        if user.startswith("TASK: list up to 3"):
            if sc == "discover" and "DATABASE_URL" in user:
                line = next(int(m.group(1)) for m in re.finditer(r"^\s*(\d+) \| (.*)$", user, re.M) if "DATABASE_URL" in m.group(2))
                return json.dumps({"concerns": [{"line": line, "quote": "postgres://app@db.internal:5432/app",
                                                 "category": "unsafe_sharing_configuration",
                                                 "claim": "An internal database hostname is hardcoded in configuration."}]})
            if sc == "discover_fabricated":
                return json.dumps({"concerns": [{"line": 1, "quote": "this text is not in the file",
                                                 "category": "secret_exposure", "claim": "invented"}]})
            return json.dumps({"concerns": []})
        return json.dumps({})
