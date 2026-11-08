"""Async HTTP client for the Tracefold engine. The only place the adapter talks to the network."""
from __future__ import annotations

import time
from typing import Any

import anyio
import httpx

from .config import AdapterConfig

TERMINAL = {"completed", "partial", "failed", "cancelled", "interrupted"}
POLL_SECONDS = 0.5


class EngineError(Exception):
    """An engine error envelope (or a transport failure), with the engine's code preserved."""

    def __init__(self, code: str, message: str, retryable: bool, status: int | None = None,
                 request_id: str | None = None):
        super().__init__(f"{code}: {message}")
        self.code, self.message, self.retryable, self.status, self.request_id = code, message, retryable, status, request_id

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "retryable": self.retryable,
                "http_status": self.status, "request_id": self.request_id}


class EngineClient:
    def __init__(self, config: AdapterConfig, http: httpx.AsyncClient | None = None):
        self.config = config
        self._http = http or httpx.AsyncClient(
            base_url=config.base_url, timeout=config.timeout_seconds,
            headers={"Authorization": f"Bearer {config.token}", "User-Agent": "tracefold-mcp/0.1"},
            follow_redirects=False, trust_env=False)

    async def aclose(self) -> None:
        await self._http.aclose()

    def ws(self, workspace_id: str | None) -> str:
        return f"/v1/workspaces/{_id(workspace_id or self.config.workspace_id)}"

    async def request(self, method: str, path: str, **kw: Any) -> Any:
        try:
            r = await self._http.request(method, path, **kw)
        except httpx.TimeoutException:
            raise EngineError("engine_timeout", "The Tracefold engine did not respond in time.", True) from None
        except httpx.HTTPError:
            raise EngineError("engine_unreachable",
                              "The Tracefold engine is not reachable at the configured loopback address.", True) from None
        if r.status_code >= 400:
            try:
                body = r.json()
                err = body["error"]
                raise EngineError(str(err["code"]), str(err["message"]), bool(err.get("retryable", False)),
                                  r.status_code, body.get("request_id"))
            except (ValueError, KeyError, TypeError):
                raise EngineError(f"http_{r.status_code}", "The engine returned an unexpected error.",
                                  r.status_code >= 500, r.status_code) from None
        return r.json() if r.content else None

    # --- endpoints ---------------------------------------------------------------------------------
    async def capabilities(self) -> dict:
        return await self.request("GET", "/v1/capabilities")

    async def workspaces(self) -> dict:
        return await self.request("GET", "/v1/workspaces")

    async def capture(self, ws: str | None, body: dict) -> dict:
        return await self.request("POST", f"{self.ws(ws)}/captures", json=body)

    async def submit_scan(self, ws: str | None, body: dict, idempotency_key: str | None = None) -> dict:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self.request("POST", f"{self.ws(ws)}/scans", json=body, headers=headers)

    async def scan(self, ws: str | None, scan_id: str) -> dict:
        return await self.request("GET", f"{self.ws(ws)}/scans/{_id(scan_id)}")

    async def cancel(self, ws: str | None, scan_id: str) -> dict:
        return await self.request("POST", f"{self.ws(ws)}/scans/{_id(scan_id)}/cancel")

    async def findings(self, ws: str | None, scan_id: str | None, cursor: str | None, limit: int) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if scan_id:
            params["scan_id"] = scan_id
        if cursor:
            params["cursor"] = cursor
        return await self.request("GET", f"{self.ws(ws)}/findings", params=params)

    async def scans(self, ws: str | None, limit: int) -> dict:
        return await self.request("GET", f"{self.ws(ws)}/scans", params={"limit": limit})

    async def actions(self, ws: str | None, status: str | None, limit: int) -> dict:
        params: dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.request("GET", f"{self.ws(ws)}/actions", params=params)

    async def finding(self, ws: str | None, finding_id: str) -> dict:
        return await self.request("GET", f"{self.ws(ws)}/findings/{_id(finding_id)}")

    async def evidence(self, ws: str | None, evidence_id: str) -> dict:
        return await self.request("GET", f"{self.ws(ws)}/evidence/{_id(evidence_id)}")

    async def recheck(self, ws: str | None, finding_id: str, body: dict) -> dict:
        return await self.request("POST", f"{self.ws(ws)}/findings/{_id(finding_id)}/rechecks", json=body)

    async def wait_for_scan(self, ws: str | None, scan_id: str, wait_seconds: float) -> dict:
        """Poll briefly; return the latest scan state whether or not it finished. Never blocks for a full scan."""
        end = time.monotonic() + max(0.0, wait_seconds)
        while True:
            s = await self.scan(ws, scan_id)
            if s["state"] in TERMINAL or time.monotonic() >= end:
                return s
            await anyio.sleep(POLL_SECONDS)


def _id(value: str) -> str:
    """Opaque engine IDs are path segments; refuse anything that could change the route."""
    if not value or len(value) > 100 or not all(c.isalnum() or c in "_-" for c in value):
        raise EngineError("invalid_request", "IDs are opaque engine identifiers like scan_… or fnd_….", False, 422)
    return value
