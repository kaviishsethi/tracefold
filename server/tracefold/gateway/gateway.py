"""The single outbound HTTP path for the engine and its workers.

Enforces: destination allowlist per purpose, DNS-resolved address checks (public policies reject private,
loopback, link-local, reserved and multicast addresses; the local-model policy requires loopback), manual
redirect handling with per-hop checks, request/response size limits, deadlines, and a redacted ledger.

Limitation: the address check happens before httpx connects and resolves again, so a DNS-rebinding race is
possible. OS-level egress restrictions on the private runtime remain the real control; this gateway is a
supplement, not a sandbox.
"""
from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import httpx

from ..util import iso, new_id, now


class GatewayDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class Policy:
    category: str                       # public_retrieval | provider_api | local_model
    purpose: str
    allowed_hosts: frozenset[str]
    require_loopback: bool = False
    allow_http: bool = False
    max_request_bytes: int = 64 * 1024
    max_response_bytes: int = 2 * 1024 * 1024
    timeout: float = 15.0
    max_redirects: int = 3
    allowed_ports: frozenset[int] = field(default_factory=lambda: frozenset({443, 80}))


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    final_url: str
    truncated: bool


Resolver = Callable[[str, int], list[str]]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return sorted({i[4][0] for i in infos})


def _address_ok(ip: str, require_loopback: bool) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if require_loopback:
        return addr.is_loopback
    return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast
                or addr.is_unspecified or (isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10")))


def mask_secret(v: str | None) -> str:
    if not v:
        return ""
    return "****" + v[-4:] if len(v) >= 12 else "****"


class Gateway:
    def __init__(self, transport: httpx.BaseTransport | None = None, resolver: Resolver | None = None):
        self.transport = transport
        self.resolver = resolver or system_resolver
        self.ledger: list[dict[str, Any]] = []
        self.requests = 0

    def _check(self, url: str, policy: Policy) -> tuple[str, int]:
        parts = urlsplit(url)
        if parts.scheme not in ("https", "http") or (parts.scheme == "http" and not policy.allow_http):
            raise GatewayDenied("scheme_not_allowed")
        if parts.username or parts.password or not parts.hostname:
            raise GatewayDenied("invalid_destination")
        host = parts.hostname.lower()
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if host not in policy.allowed_hosts:
            raise GatewayDenied("destination_not_allowed")
        if port not in policy.allowed_ports:
            raise GatewayDenied("port_not_allowed")
        try:
            ips = self.resolver(host, port)
        except OSError:
            raise GatewayDenied("dns_failed")
        if not ips or not all(_address_ok(ip, policy.require_loopback) for ip in ips):
            raise GatewayDenied("address_not_allowed")
        return host, port

    def _log(self, policy: Policy, host: str, source_id: str | None, status: str, summary: dict[str, Any], started: float) -> None:
        self.ledger.append({
            "id": new_id("ev"), "destination_category": policy.category, "destination_host": host, "purpose": policy.purpose,
            "source_id": source_id, "status": status, "at": iso(now()),
            "payload_summary": {**summary, "duration_ms": int((time.monotonic() - started) * 1000)},
        })

    def request(self, method: str, url: str, policy: Policy, *, source_id: str | None = None,
                headers: dict[str, str] | None = None, json_body: Any = None, summary: dict[str, Any] | None = None,
                deadline: float | None = None) -> Response:
        """Perform one logical request (following allowed redirects). ``summary`` must already be redacted."""
        import json as _json
        started = time.monotonic()
        body = _json.dumps(json_body).encode() if json_body is not None else None
        summary = dict(summary or {})
        summary.setdefault("method", method)
        host = urlsplit(url).hostname or "?"
        if body is not None and len(body) > policy.max_request_bytes:
            self._log(policy, host, source_id, "denied:request_too_large", summary, started)
            raise GatewayDenied("request_too_large")
        hdrs = {"User-Agent": "tracefold-retrieval/0.1", **(headers or {})}
        if body is not None:
            hdrs["Content-Type"] = "application/json"
        current = url
        hops = 0
        try:
            while True:
                host, _ = self._check(current, policy)
                remaining = policy.timeout if deadline is None else max(0.5, min(policy.timeout, deadline - time.monotonic()))
                if deadline is not None and deadline - time.monotonic() <= 0:
                    raise GatewayDenied("deadline_exceeded")
                self.requests += 1
                with httpx.Client(transport=self.transport, follow_redirects=False, timeout=remaining, trust_env=False) as c:
                    with c.stream(method, current, headers=hdrs, content=body) as r:
                        if r.is_redirect and "location" in r.headers:
                            hops += 1
                            if hops > policy.max_redirects:
                                raise GatewayDenied("too_many_redirects")
                            nxt = urljoin(current, r.headers["location"])
                            if (urlsplit(nxt).hostname or "").lower() not in policy.allowed_hosts:
                                raise GatewayDenied("redirect_not_allowed")
                            summary.setdefault("redirects", []).append(urlsplit(nxt).hostname)
                            current = nxt
                            if method == "POST":
                                raise GatewayDenied("redirect_on_post_refused")
                            continue
                        chunks, total, truncated = [], 0, False
                        for chunk in r.iter_bytes():
                            total += len(chunk)
                            if total > policy.max_response_bytes:
                                chunks.append(chunk[: len(chunk) - (total - policy.max_response_bytes)])
                                truncated = True
                                break
                            chunks.append(chunk)
                        resp = Response(r.status_code, {k.lower(): v for k, v in r.headers.items()}, b"".join(chunks),
                                        current, truncated)
                self._log(policy, host, source_id, str(resp.status), {**summary, "bytes": len(resp.body),
                                                                       "truncated": truncated}, started)
                return resp
        except GatewayDenied as ex:
            self._log(policy, host, source_id, f"denied:{ex.reason}", summary, started)
            raise
        except httpx.TimeoutException:
            self._log(policy, host, source_id, "error:timeout", summary, started)
            raise GatewayDenied("timeout")
        except httpx.HTTPError as ex:
            self._log(policy, host, source_id, f"error:{type(ex).__name__}", summary, started)
            raise GatewayDenied("network_error")
