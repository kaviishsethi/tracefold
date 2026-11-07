"""Isolated public retrieval worker.

Runs as a separate process (``python -I -m tracefold.retrieval.worker``) with an empty working directory, a
minimal environment carrying only provider keys, and — on macOS when available — a sandbox profile that
denies reads of the engine data directory and registered workspace roots. It never receives private text:
its request schema accepts only manifest entries (source ID, URL, provider) and limits. All HTTP goes
through the gateway, and the worker returns a redacted ledger with its results.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

from ..gateway.gateway import Gateway, GatewayDenied, Policy, mask_secret
from ..util import iso, now
from .html import html_to_text

EXA_URL = "https://api.exa.ai/contents"
TAVILY_URL = "https://api.tavily.com/extract"
REQUEST_KEYS = {"sources", "limits", "deadline_seconds", "fixture_root"}
SOURCE_KEYS = {"source_id", "url", "provider", "fixture_path"}
LIMIT_KEYS = {"max_text", "max_raw", "max_requests", "concurrency"}


class InvalidRequest(Exception):
    pass


def validate_request(req: dict) -> dict:
    """Strict schema: anything that is not a manifest entry or a limit is rejected."""
    if not isinstance(req, dict) or set(req) - REQUEST_KEYS or "sources" not in req or "limits" not in req:
        raise InvalidRequest("unexpected request fields")
    if set(req["limits"]) != LIMIT_KEYS or not all(isinstance(v, int) and v > 0 for v in req["limits"].values()):
        raise InvalidRequest("invalid limits")
    if not isinstance(req["sources"], list) or len(req["sources"]) > 50:
        raise InvalidRequest("invalid sources")
    for s in req["sources"]:
        if not isinstance(s, dict) or set(s) - SOURCE_KEYS or not {"source_id", "url", "provider"} <= set(s):
            raise InvalidRequest("invalid source entry")
        if s["provider"] not in ("fixture", "direct", "exa", "tavily"):
            raise InvalidRequest("unknown provider")
        parts = urlsplit(s["url"])
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise InvalidRequest("invalid url")
    return req


def _text_from(resp_body: bytes, content_type: str) -> str:
    text = resp_body.decode("utf-8", "replace")
    if "html" in content_type or text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        return html_to_text(text)
    return text


class Worker:
    def __init__(self, req: dict, gateway: Gateway, env: dict[str, str]):
        self.req = req
        self.gw = gateway
        self.env = env
        self.lim = req["limits"]
        self.deadline = time.monotonic() + float(req.get("deadline_seconds") or 60)

    def _budget(self) -> None:
        if self.gw.requests >= self.lim["max_requests"]:
            raise GatewayDenied("request_budget_exhausted")

    def _finish(self, text: str, truncated: bool) -> dict:
        over = len(text) > self.lim["max_text"]
        return {"status": "ok", "text": text[: self.lim["max_text"]], "truncated": truncated or over}

    def fixture(self, s: dict) -> dict:
        root = self.req.get("fixture_root")
        if not root or not s.get("fixture_path"):
            return {"status": "failed", "error": "fixture_root_not_configured"}
        rootp = Path(root).resolve()
        p = (rootp / s["fixture_path"]).resolve()
        if rootp not in p.parents or not p.is_file():
            return {"status": "failed", "error": "fixture_not_found"}
        raw = p.read_bytes()
        truncated = len(raw) > self.lim["max_raw"]
        return self._finish(_text_from(raw[: self.lim["max_raw"]], "text/html" if p.suffix in (".html", ".htm") else "text/plain"),
                            truncated)

    def direct(self, s: dict) -> dict:
        self._budget()
        host = urlsplit(s["url"]).hostname.lower()
        pol = Policy("public_retrieval", "fetch_approved_public_url", frozenset({host}), allow_http=False,
                     max_response_bytes=self.lim["max_raw"])
        r = self.gw.request("GET", s["url"], pol, source_id=s["source_id"], deadline=self.deadline,
                            summary={"url": s["url"], "provider": "direct"})
        if r.status != 200:
            return {"status": "failed", "error": f"http_{r.status}", "final_url": r.final_url}
        ctype = r.headers.get("content-type", "")
        if not any(t in ctype for t in ("text/html", "text/plain", "application/xhtml", "text/markdown")) and ctype:
            return {"status": "failed", "error": "unsupported_content_type"}
        out = self._finish(_text_from(r.body, ctype), r.truncated)
        out["final_url"] = r.final_url
        return out

    def exa(self, s: dict) -> dict:
        key = self.env.get("EXA_API_KEY")
        if not key:
            return {"status": "failed", "error": "provider_not_configured"}
        self._budget()
        pol = Policy("provider_api", "extract_approved_public_url", frozenset({"api.exa.ai"}), max_response_bytes=self.lim["max_raw"] * 2)
        body = {"urls": [s["url"]], "text": {"maxCharacters": self.lim["max_text"]}}
        r = self.gw.request("POST", EXA_URL, pol, source_id=s["source_id"], headers={"x-api-key": key}, json_body=body,
                            deadline=self.deadline,
                            summary={"provider": "exa", "urls": [s["url"]], "auth": "x-api-key " + mask_secret(key)})
        if r.status != 200:
            return {"status": "failed", "error": f"provider_http_{r.status}"}
        try:
            data = json.loads(r.body)
            res = next((x for x in data.get("results", []) if x.get("text")), None)
        except (ValueError, AttributeError):
            return {"status": "failed", "error": "provider_response_invalid"}
        if res is None:
            return {"status": "failed", "error": "provider_no_content"}
        return self._finish(str(res["text"]), r.truncated)

    def tavily(self, s: dict) -> dict:
        key = self.env.get("TAVILY_API_KEY")
        if not key:
            return {"status": "failed", "error": "provider_not_configured"}
        self._budget()
        pol = Policy("provider_api", "extract_approved_public_url", frozenset({"api.tavily.com"}), max_response_bytes=self.lim["max_raw"] * 2)
        body = {"urls": [s["url"]], "extract_depth": "basic", "format": "text"}
        r = self.gw.request("POST", TAVILY_URL, pol, source_id=s["source_id"], headers={"Authorization": f"Bearer {key}"},
                            json_body=body, deadline=self.deadline,
                            summary={"provider": "tavily", "urls": [s["url"]], "auth": "Bearer " + mask_secret(key)})
        if r.status != 200:
            return {"status": "failed", "error": f"provider_http_{r.status}"}
        try:
            data = json.loads(r.body)
            res = next((x for x in data.get("results", []) if x.get("raw_content")), None)
        except (ValueError, AttributeError):
            return {"status": "failed", "error": "provider_response_invalid"}
        if res is None:
            return {"status": "failed", "error": "provider_no_content"}
        return self._finish(str(res["raw_content"]), r.truncated)

    def one(self, s: dict) -> dict:
        base = {"source_id": s["source_id"], "url": s["url"], "provider": s["provider"]}
        if time.monotonic() >= self.deadline:
            return {**base, "status": "failed", "error": "deadline_exceeded", "retrieved_at": iso(now())}
        try:
            r = getattr(self, s["provider"])(s)
        except GatewayDenied as ex:
            r = {"status": "failed", "error": ex.reason}
        except Exception as ex:  # never let one source break the batch
            r = {"status": "failed", "error": f"worker_error:{type(ex).__name__}"}
        return {**base, **r, "retrieved_at": iso(now())}

    def run(self) -> dict:
        with ThreadPoolExecutor(max_workers=max(1, min(self.lim["concurrency"], 2))) as ex:
            results = list(ex.map(self.one, self.req["sources"]))
        return {"results": results, "ledger": self.gw.ledger, "requests": self.gw.requests}


def run_request(req: dict, transport=None, resolver=None, env: dict[str, str] | None = None) -> dict:
    validate_request(req)
    return Worker(req, Gateway(transport=transport, resolver=resolver), env if env is not None else dict(os.environ)).run()


# ---------------- process isolation ----------------
def sandbox_profile(deny_read: list[str], tmpdir: str) -> str:
    rules = "\n".join(f'(deny file-read* (subpath "{p}"))' for p in deny_read)
    return f"""(version 1)
(allow default)
{rules}
(deny file-write* (subpath "/"))
(allow file-write* (subpath "{tmpdir}") (literal "/dev/null") (literal "/dev/stdout") (literal "/dev/stderr"))
"""


def run_subprocess(req: dict, timeout: float, deny_read: list[str] | None = None, sandbox: bool = True) -> dict:
    validate_request(req)
    with tempfile.TemporaryDirectory(prefix="tf-retrieval-") as tmp:
        tmp = os.path.realpath(tmp)
        env = {"PATH": "/usr/bin:/bin", "HOME": tmp, "TMPDIR": tmp, "PYTHONDONTWRITEBYTECODE": "1",
               "LANG": "C.UTF-8"}
        for k in ("EXA_API_KEY", "TAVILY_API_KEY", "SSL_CERT_FILE", "SSL_CERT_DIR"):
            if os.environ.get(k):
                env[k] = os.environ[k]
        cmd = [sys.executable, "-I", "-m", "tracefold.retrieval.worker"]
        if sandbox and sys.platform == "darwin" and shutil.which("sandbox-exec") and deny_read:
            prof = Path(tmp) / "worker.sb"
            prof.write_text(sandbox_profile([os.path.realpath(p) for p in deny_read], tmp))
            cmd = ["sandbox-exec", "-f", str(prof), *cmd]
        try:
            r = subprocess.run(cmd, input=json.dumps(req).encode(), capture_output=True, timeout=timeout, cwd=tmp, env=env,
                               check=False)
        except subprocess.TimeoutExpired:
            return {"results": [{"source_id": s["source_id"], "url": s["url"], "provider": s["provider"], "status": "failed",
                                 "error": "worker_timeout", "retrieved_at": iso(now())} for s in req["sources"]],
                    "ledger": [], "requests": 0}
    if r.returncode != 0:
        raise RuntimeError(f"retrieval worker failed ({r.returncode})")
    return json.loads(r.stdout)


def main() -> None:  # pragma: no cover - exercised through run_subprocess
    req = json.loads(sys.stdin.buffer.read())
    out = run_request(req)
    sys.stdout.write(json.dumps(out))


if __name__ == "__main__":  # pragma: no cover
    main()
