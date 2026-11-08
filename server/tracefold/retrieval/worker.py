"""Isolated public retrieval worker.

Runs as a separate process (``python -I -m tracefold.retrieval.worker``) with an empty working directory, a
minimal environment carrying only provider keys, and — on macOS when available — a sandbox profile that
denies reads of the engine data directory and registered workspace roots. It never receives private text:
its request schema accepts only manifest entries (source ID, URL, provider) and limits — or, for the
distinct ``search`` operation, the rendered queries of an approved public query plan. All HTTP goes through
the gateway, and the worker returns a redacted ledger with its results.
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
EXA_SEARCH_URL = "https://api.exa.ai/search"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
REQUEST_KEYS = {"op", "sources", "limits", "deadline_seconds", "fixture_root"}
SOURCE_KEYS = {"source_id", "url", "provider", "fixture_path"}
LIMIT_KEYS = {"max_text", "max_raw", "max_requests", "concurrency"}
SEARCH_REQUEST_KEYS = {"op", "searches", "limits", "deadline_seconds"}
SEARCH_KEYS = {"query_id", "provider", "query", "num_results", "include_domains"}
SEARCH_OPTIONAL_KEYS = {"include_domains_mode", "exclude_domains", "category", "topic", "exact_match"}
EXA_CATEGORIES = {"news", "publication", "financial report", "personal site"}
TAVILY_TOPICS = {"general", "news", "finance"}
SEARCH_LIMIT_KEYS = {"max_results", "max_requests", "concurrency", "max_raw"}
MAX_SEARCHES = 8
MAX_EXCESS_RECORDED = 20


class InvalidRequest(Exception):
    pass


def validate_search_request(req: dict) -> dict:
    """Strict schema for the search operation: only rendered public queries, providers, domain filters, limits."""
    if set(req) - SEARCH_REQUEST_KEYS or not {"searches", "limits"} <= set(req):
        raise InvalidRequest("unexpected request fields")
    lim = req["limits"]
    if not isinstance(lim, dict) or set(lim) != SEARCH_LIMIT_KEYS or not all(isinstance(v, int) and v > 0 for v in lim.values()):
        raise InvalidRequest("invalid limits")
    if lim["max_results"] > 5:
        raise InvalidRequest("invalid limits")
    if not isinstance(req["searches"], list) or not 1 <= len(req["searches"]) <= MAX_SEARCHES:
        raise InvalidRequest("invalid searches")
    for q in req["searches"]:
        if not isinstance(q, dict) or not SEARCH_KEYS <= set(q) or set(q) - SEARCH_KEYS - SEARCH_OPTIONAL_KEYS:
            raise InvalidRequest("invalid search entry")
        if q["provider"] not in ("exa", "tavily"):
            raise InvalidRequest("unknown provider")
        if not isinstance(q["query"], str) or not 1 <= len(q["query"]) <= 300 or any(ord(c) < 0x20 for c in q["query"]):
            raise InvalidRequest("invalid query")
        if not isinstance(q["num_results"], int) or not 1 <= q["num_results"] <= lim["max_results"]:
            raise InvalidRequest("invalid num_results")
        for field in ("include_domains", "exclude_domains"):
            doms = q.get(field)
            if doms is not None and (not isinstance(doms, list) or not 0 < len(doms) <= 20 or not all(
                    isinstance(d, str) and 0 < len(d) <= 253 and all(c.isalnum() or c in ".-" for c in d) for d in doms)):
                raise InvalidRequest(f"invalid {field}")
        mode = q.get("include_domains_mode")
        if mode is not None and (q["provider"] != "tavily" or mode not in ("restrict", "prefer") or not q["include_domains"]):
            raise InvalidRequest("invalid include_domains_mode")
        cat = q.get("category")
        if cat is not None and (q["provider"] != "exa" or cat not in EXA_CATEGORIES):
            raise InvalidRequest("invalid category")
        topic = q.get("topic")
        if topic is not None and (q["provider"] != "tavily" or topic not in TAVILY_TOPICS):
            raise InvalidRequest("invalid topic")
        em = q.get("exact_match")
        if em is not None and (q["provider"] != "tavily" or not isinstance(em, bool)):
            raise InvalidRequest("invalid exact_match")
    return req


def validate_request(req: dict) -> dict:
    """Strict schema: anything that is not a manifest entry or a limit is rejected."""
    if isinstance(req, dict) and req.get("op") == "search":
        return validate_search_request(req)
    if isinstance(req, dict) and req.get("op", "fetch") != "fetch":
        raise InvalidRequest("unknown operation")
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


def _str(v, n: int) -> str | None:
    return v[:n] if isinstance(v, str) and v else None


class SearchWorker:
    """Runs the searches of an approved plan. Returns candidate metadata only (URL, title, rank, provider
    timestamps); snippets, generated answers and page text are never requested or returned."""

    def __init__(self, req: dict, gateway: Gateway, env: dict[str, str]):
        self.req = req
        self.gw = gateway
        self.env = env
        self.lim = req["limits"]
        self.deadline = time.monotonic() + float(req.get("deadline_seconds") or 60)

    def _call(self, q: dict) -> tuple[int, bytes, bool] | dict:
        prov = q["provider"]
        key = self.env.get("EXA_API_KEY" if prov == "exa" else "TAVILY_API_KEY")
        if not key:
            return {"status": "failed", "error": "provider_not_configured"}
        if self.gw.requests >= self.lim["max_requests"]:
            raise GatewayDenied("request_budget_exhausted")
        if prov == "exa":
            body = {"query": q["query"], "numResults": q["num_results"], "type": "auto"}
            if q["include_domains"]:
                body["includeDomains"] = q["include_domains"]
            elif q.get("exclude_domains"):
                body["excludeDomains"] = q["exclude_domains"]
            if q.get("category"):
                body["category"] = q["category"]
            url, host, headers, auth = EXA_SEARCH_URL, "api.exa.ai", {"x-api-key": key}, "x-api-key " + mask_secret(key)
        else:
            body = {"query": q["query"], "max_results": q["num_results"], "search_depth": "basic",
                    "topic": q.get("topic") or "general", "include_answer": False, "include_raw_content": False,
                    "include_images": False}
            if q.get("exact_match"):
                body["exact_match"] = True
            if q["include_domains"]:
                body["include_domains"] = q["include_domains"]
                if q.get("include_domains_mode") == "prefer":
                    body["include_domains_mode"] = "prefer"
            if q.get("exclude_domains") and q.get("include_domains_mode") != "restrict":
                body["exclude_domains"] = q["exclude_domains"]
            url, host, headers, auth = (TAVILY_SEARCH_URL, "api.tavily.com", {"Authorization": f"Bearer {key}"},
                                        "Bearer " + mask_secret(key))
        pol = Policy("provider_api", "search_approved_public_query", frozenset({host}), max_response_bytes=self.lim["max_raw"])
        r = self.gw.request("POST", url, pol, source_id=q["query_id"], headers=headers, json_body=body, deadline=self.deadline,
                            summary={"provider": prov, "op": "search", "query_id": q["query_id"], "query": q["query"],
                                     "num_results": q["num_results"], "include_domains": q["include_domains"],
                                     "exclude_domains": q.get("exclude_domains"), "category": q.get("category"),
                                     "topic": q.get("topic"), "exact_match": q.get("exact_match"), "auth": auth})
        return r.status, r.body, r.truncated

    def one(self, q: dict) -> dict:
        base = {"query_id": q["query_id"], "provider": q["provider"], "query": q["query"], "results": [], "excess": [],
                "returned": 0, "truncated": False}
        if time.monotonic() >= self.deadline:
            return {**base, "status": "failed", "error": "deadline_exceeded", "searched_at": iso(now())}
        try:
            out = self._call(q)
        except GatewayDenied as ex:
            return {**base, "status": "failed", "error": ex.reason, "searched_at": iso(now())}
        except Exception as ex:
            return {**base, "status": "failed", "error": f"worker_error:{type(ex).__name__}", "searched_at": iso(now())}
        if isinstance(out, dict):
            return {**base, **out, "searched_at": iso(now())}
        status, raw, cut = out
        if status != 200:
            return {**base, "status": "failed", "error": f"provider_http_{status}", "searched_at": iso(now())}
        if cut:
            return {**base, "status": "failed", "error": "provider_response_too_large", "searched_at": iso(now())}
        try:
            data = json.loads(raw)
            items = data["results"]
            if not isinstance(items, list):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return {**base, "status": "failed", "error": "provider_response_invalid", "searched_at": iso(now())}
        results, excess = [], []
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            rec = {"rank": i + 1, "url": _str(it.get("url"), 4096), "title": _str(it.get("title"), 300),
                   "provider_published_at": _str(it.get("publishedDate") or it.get("published_date"), 64)}
            if len(results) < q["num_results"]:
                results.append(rec)
            elif len(excess) < MAX_EXCESS_RECORDED:
                excess.append(rec)
        truncated = len(items) > q["num_results"]
        return {**base, "status": "ok", "error": None, "results": results, "excess": excess, "returned": len(items),
                "truncated": truncated, "searched_at": iso(now())}

    def run(self) -> dict:
        with ThreadPoolExecutor(max_workers=max(1, min(self.lim["concurrency"], 2))) as ex:
            out = list(ex.map(self.one, self.req["searches"]))
        return {"searches": out, "ledger": self.gw.ledger, "requests": self.gw.requests}


def run_request(req: dict, transport=None, resolver=None, env: dict[str, str] | None = None) -> dict:
    validate_request(req)
    gw = Gateway(transport=transport, resolver=resolver)
    env = env if env is not None else dict(os.environ)
    if req.get("op") == "search":
        return SearchWorker(req, gw, env).run()
    return Worker(req, gw, env).run()


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
            if req.get("op") == "search":
                return {"searches": [{"query_id": q["query_id"], "provider": q["provider"], "query": q["query"],
                                      "status": "failed", "error": "worker_timeout", "results": [], "excess": [],
                                      "returned": 0, "truncated": False, "searched_at": iso(now())}
                                     for q in req["searches"]], "ledger": [], "requests": 0}
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
