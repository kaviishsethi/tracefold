"""Milestone 5: isolated live retrieval and gateway."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import httpx
import pytest

from tracefold.gateway.gateway import Gateway, GatewayDenied, Policy
from tracefold.retrieval.worker import InvalidRequest, run_request, run_subprocess, sandbox_profile, validate_request

from .conftest import FIXTURES, fx

PUBLIC_IP = lambda host, port: ["93.184.215.14"]  # noqa: E731
FORUM_HTML = (FIXTURES / "public" / "forum_post.html").read_bytes()
MARKER = "TFMARKER-7d1c9a52-private-only"
LIMITS = {"max_text": 200_000, "max_raw": 2_000_000, "max_requests": 40, "concurrency": 2}


class Recorder:
    """httpx mock transport that records every outbound request in full."""

    def __init__(self, handler):
        self.handler = handler
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.seen.append(request)
        return self.handler(request)

    def transport(self):
        return httpx.MockTransport(self)

    def dump(self) -> str:
        return "\n".join(f"{r.method} {r.url}\n{dict(r.headers)}\n{r.content.decode('utf-8', 'replace')}" for r in self.seen)


def pol(*hosts, **kw):
    return Policy("public_retrieval", "test", frozenset(hosts), **kw)


# ---------------- gateway ----------------
def test_gateway_allows_approved_and_logs():
    rec = Recorder(lambda r: httpx.Response(200, text="hello", headers={"content-type": "text/plain"}))
    gw = Gateway(rec.transport(), PUBLIC_IP)
    r = gw.request("GET", "https://pages.example/a", pol("pages.example"), source_id="s1", summary={"url": "https://pages.example/a"})
    assert r.status == 200 and r.body == b"hello"
    ev = gw.ledger[0]
    assert ev["destination_host"] == "pages.example" and ev["status"] == "200" and ev["source_id"] == "s1"


@pytest.mark.parametrize("ip", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.2", "::1", "100.64.1.1", "0.0.0.0"])
def test_gateway_rejects_private_addresses(ip):
    rec = Recorder(lambda r: httpx.Response(200))
    gw = Gateway(rec.transport(), lambda h, p: [ip])
    with pytest.raises(GatewayDenied) as ei:
        gw.request("GET", "https://pages.example/", pol("pages.example"))
    assert ei.value.reason == "address_not_allowed" and rec.seen == []
    assert gw.ledger[0]["status"] == "denied:address_not_allowed"


def test_gateway_destination_scheme_port_checks():
    gw = Gateway(Recorder(lambda r: httpx.Response(200)).transport(), PUBLIC_IP)
    for url, reason in [("https://other.example/", "destination_not_allowed"), ("http://pages.example/", "scheme_not_allowed"),
                        ("https://u:p@pages.example/", "invalid_destination"), ("https://pages.example:8443/", "port_not_allowed"),
                        ("file:///etc/passwd", "scheme_not_allowed")]:
        with pytest.raises(GatewayDenied) as ei:
            gw.request("GET", url, pol("pages.example"))
        assert ei.value.reason == reason, url


def test_gateway_redirects_checked_per_hop():
    def handler(r):
        if r.url.path == "/start":
            return httpx.Response(302, headers={"location": "/next"})
        if r.url.path == "/next":
            return httpx.Response(302, headers={"location": "https://evil.example/steal"})
        return httpx.Response(200)
    rec = Recorder(handler)
    gw = Gateway(rec.transport(), PUBLIC_IP)
    with pytest.raises(GatewayDenied) as ei:
        gw.request("GET", "https://pages.example/start", pol("pages.example"))
    assert ei.value.reason == "redirect_not_allowed"
    assert [r.url.host for r in rec.seen] == ["pages.example", "pages.example"]

    loop = Recorder(lambda r: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(GatewayDenied) as ei:
        Gateway(loop.transport(), PUBLIC_IP).request("GET", "https://pages.example/x", pol("pages.example"))
    assert ei.value.reason == "too_many_redirects"


def test_gateway_response_cap_and_request_cap():
    rec = Recorder(lambda r: httpx.Response(200, content=b"x" * 5000))
    gw = Gateway(rec.transport(), PUBLIC_IP)
    r = gw.request("GET", "https://pages.example/", pol("pages.example", max_response_bytes=1000))
    assert r.truncated and len(r.body) == 1000
    with pytest.raises(GatewayDenied):
        gw.request("POST", "https://pages.example/", pol("pages.example", max_request_bytes=10), json_body={"a": "b" * 100})


def test_local_model_policy_requires_loopback():
    p = Policy("local_model", "review", frozenset({"127.0.0.1"}), require_loopback=True, allow_http=True,
               allowed_ports=frozenset({11434}))
    ok = Gateway(Recorder(lambda r: httpx.Response(200)).transport(), lambda h, port: ["127.0.0.1"])
    assert ok.request("GET", "http://127.0.0.1:11434/api/tags", p).status == 200
    bad = Gateway(Recorder(lambda r: httpx.Response(200)).transport(), lambda h, port: ["93.184.215.14"])
    with pytest.raises(GatewayDenied):
        bad.request("GET", "http://127.0.0.1:11434/api/tags", p)


# ---------------- worker ----------------
def test_worker_request_schema_is_strict():
    base = {"sources": [{"source_id": "a", "url": "https://x.example/", "provider": "direct"}], "limits": LIMITS}
    validate_request(base)
    for bad in [{**base, "query": "private words"},
                {**base, "sources": [{**base["sources"][0], "text": "private"}]},
                {**base, "sources": [{**base["sources"][0], "provider": "shell"}]},
                {**base, "limits": {**LIMITS, "extra": 1}}]:
        with pytest.raises(InvalidRequest):
            validate_request(bad)


def test_providers_send_only_manifest_urls():
    def handler(r):
        if r.url.host == "api.exa.ai":
            return httpx.Response(200, json={"results": [{"url": "https://a.example/", "text": "exa page text"}]})
        if r.url.host == "api.tavily.com":
            return httpx.Response(200, json={"results": [{"url": "https://b.example/", "raw_content": "tavily page text"}]})
        return httpx.Response(200, content=FORUM_HTML, headers={"content-type": "text/html; charset=utf-8"})
    rec = Recorder(handler)
    req = {"sources": [{"source_id": "e", "url": "https://a.example/", "provider": "exa"},
                       {"source_id": "t", "url": "https://b.example/", "provider": "tavily"},
                       {"source_id": "d", "url": "https://forum.example/t/123", "provider": "direct"},
                       {"source_id": "nokey", "url": "https://c.example/", "provider": "exa"}],
           "limits": LIMITS, "deadline_seconds": 30}
    out = run_request(req, rec.transport(), PUBLIC_IP, env={"EXA_API_KEY": "exa-test-key-123456", "TAVILY_API_KEY": "tvly-test-key-abcdef"})
    by = {r["source_id"]: r for r in out["results"]}
    assert by["e"]["text"] == "exa page text" and by["t"]["text"] == "tavily page text"
    assert "Harbor ingestion cluster" in by["d"]["text"] and "tracking" not in by["d"]["text"]
    exa_body = json.loads(next(r for r in rec.seen if r.url.host == "api.exa.ai" and b"a.example" in r.content).content)
    assert exa_body == {"urls": ["https://a.example/"], "text": {"maxCharacters": 200_000}}
    tav = next(r for r in rec.seen if r.url.host == "api.tavily.com")
    assert json.loads(tav.content) == {"urls": ["https://b.example/"], "extract_depth": "basic", "format": "text"}
    assert tav.headers["authorization"] == "Bearer tvly-test-key-abcdef"
    # keys are masked in the ledger
    led = json.dumps(out["ledger"])
    assert "exa-test-key-123456" not in led and "tvly-test-key-abcdef" not in led and "****3456" in led
    out2 = run_request({**req, "sources": req["sources"][3:]}, rec.transport(), PUBLIC_IP, env={})
    assert out2["results"][0]["error"] == "provider_not_configured"


def test_request_budget_enforced():
    rec = Recorder(lambda r: httpx.Response(200, text="t", headers={"content-type": "text/plain"}))
    srcs = [{"source_id": f"s{i}", "url": f"https://p{i}.example/", "provider": "direct"} for i in range(5)]
    out = run_request({"sources": srcs, "limits": {**LIMITS, "max_requests": 2}}, rec.transport(), PUBLIC_IP, env={})
    assert sum(r["status"] == "ok" for r in out["results"]) == 2
    assert sum(r.get("error") == "request_budget_exhausted" for r in out["results"]) == 3


# ---------------- engine integration ----------------
def direct_manifest(env, html=FORUM_HTML, status=200):
    env.engine.add_manifest("ws_a", "live_demo", [
        {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "direct"}])
    rec = Recorder(lambda r: httpx.Response(status, content=html, headers={"content-type": "text/html"}))
    env.engine.test_transport = rec.transport()
    env.engine.test_resolver = PUBLIC_IP
    env.engine.test_env = {}
    return rec


def test_private_marker_never_leaves(env):
    rec = direct_manifest(env)
    private = fx("roadmap.md").decode() + f"\n\nInternal tracking marker: {MARKER}\n"
    risky = fx("risky_app.py").decode() + f"\n# {MARKER}\n"
    inp = env.upload({f"{MARKER}.md": private.encode(), "risky_app.py": risky.encode()})
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"], public_sources={"manifest_id": "live_demo"},
                 model_review=False)
    assert s["state"] == "completed", s
    assert rec.seen and MARKER not in rec.dump()
    assert "roadmap" not in rec.dump().lower()
    led = env.client.get(f"/v1/workspaces/ws_a/scans/{s['scan_id']}/ledger", headers=env.h()).json()["items"]
    assert len(led) == 1 and led[0]["destination_host"] == "forum.example" and led[0]["purpose"] == "fetch_approved_public_url"
    assert MARKER not in json.dumps(led)
    kinds = {f["kind"] for f in env.findings(s["scan_id"])}
    assert kinds == {"public_exposure", "local_risk"}


def test_retrieval_failure_preserves_local_checks(env):
    direct_manifest(env, html=b"forbidden", status=403)
    inp = env.upload({"risky_app.py": fx("risky_app.py"), "roadmap.md": fx("roadmap.md")})
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"], public_sources={"manifest_id": "live_demo"},
                 model_review=False)
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("source", "forum")]["status"] == "failed" and cov[("source", "forum")]["reason"] == "http_403"
    assert cov[("check", "public_match")]["status"] == "failed"
    assert cov[("check", "local_risk")]["status"] == "complete"
    assert s["state"] == "partial"
    fs = env.findings(s["scan_id"])
    assert fs and all(f["kind"] == "local_risk" for f in fs)


def test_redirect_to_private_address_rejected_in_scan(env):
    env.engine.add_manifest("ws_a", "redir", [{"source_id": "r", "url": "https://forum.example/x", "provider": "direct"}])
    env.engine.test_transport = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "http://169.254.169.254/latest"}))
    env.engine.test_resolver = PUBLIC_IP
    env.engine.test_env = {}
    inp = env.upload({"roadmap.md": fx("roadmap.md")})
    s = env.scan(inp["input_id"], checks=["public_match"], public_sources={"manifest_id": "redir"})
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("source", "r")]["reason"] == "redirect_not_allowed"


def test_real_subprocess_worker(make_env):
    env = make_env(retrieval_in_process=False)
    inp = env.upload({"roadmap.md": fx("roadmap.md")})
    s = env.scan(inp["input_id"], checks=["public_match"], public_sources={"manifest_id": "sources_demo"})
    assert s["state"] == "completed", s
    assert s["summary"]["retrieval_isolation"].startswith("separate_process")
    assert len(env.findings(s["scan_id"])) == 1


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("sandbox-exec"), reason="macOS sandbox-exec only")
def test_sandbox_profile_denies_private_reads(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    (private / "secret.txt").write_text(MARKER)
    work = tmp_path / "work"
    work.mkdir()
    prof = work / "p.sb"
    prof.write_text(sandbox_profile([os.path.realpath(private)], os.path.realpath(work)))
    r = subprocess.run(["sandbox-exec", "-f", str(prof), "/bin/cat", str(private / "secret.txt")], capture_output=True)
    assert r.returncode != 0 and MARKER.encode() not in r.stdout
    r = subprocess.run(["sandbox-exec", "-f", str(prof), "/usr/bin/touch", str(tmp_path / "outside")], capture_output=True)
    assert r.returncode != 0
    # the worker process itself still runs under the profile
    out = run_subprocess({"sources": [{"source_id": "f", "url": "https://forum.example/", "provider": "fixture",
                                       "fixture_path": "public/forum_post.html"}],
                          "limits": LIMITS, "fixture_root": str(FIXTURES), "deadline_seconds": 20},
                         timeout=60, deny_read=[str(private)])
    assert out["results"][0]["status"] == "ok"


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("TRACEFOLD_LIVE") != "1", reason="set TRACEFOLD_LIVE=1 to call real public sources")
def test_live_direct_fetch_through_isolated_worker():
    out = run_subprocess({"sources": [{"source_id": "example", "url": "https://example.com/", "provider": "direct"}],
                          "limits": LIMITS, "deadline_seconds": 30}, timeout=60, deny_read=[])
    r = out["results"][0]
    assert r["status"] == "ok", r
    assert "Example Domain" in r["text"]
    assert out["ledger"][0]["destination_host"] == "example.com"


@pytest.mark.live
@pytest.mark.parametrize("provider,key", [("exa", "EXA_API_KEY"), ("tavily", "TAVILY_API_KEY")])
def test_live_provider_extract(provider, key):
    if os.environ.get("TRACEFOLD_LIVE") != "1" or not os.environ.get(key):
        pytest.skip(f"needs TRACEFOLD_LIVE=1 and {key} (env or server/.env)")
    out = run_subprocess({"sources": [{"source_id": "example", "url": "https://example.com/", "provider": provider}],
                          "limits": LIMITS, "deadline_seconds": 45}, timeout=90, deny_read=[])
    r = out["results"][0]
    assert r["status"] == "ok", r
    assert "documentation examples" in r["text"]
    ev = out["ledger"][0]
    assert ev["destination_host"] == {"exa": "api.exa.ai", "tavily": "api.tavily.com"}[provider]
    assert os.environ[key] not in json.dumps(out["ledger"])  # key masked in the ledger
