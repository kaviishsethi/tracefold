"""Loopback-only Ollama client. All calls go through the gateway's local-model policy (no cloud fallback)."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..gateway.gateway import Gateway, GatewayDenied, Policy

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class ModelUnavailable(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass
class ChatResult:
    content: str
    prompt_tokens: int
    output_tokens: int


class OllamaClient:
    def __init__(self, base_url: str, model: str, context_tokens: int, max_output: int, timeout: float,
                 gateway: Gateway | None = None):
        parts = urlsplit(base_url)
        host = (parts.hostname or "").lower()
        if host not in LOOPBACK_HOSTS:
            raise ModelUnavailable("model_endpoint_not_loopback")
        self.base = base_url.rstrip("/")
        self.model = model
        self.context_tokens = context_tokens
        self.max_output = max_output
        self.gw = gateway or Gateway()
        self.policy = Policy("local_model", "local_model_review", frozenset({host}), require_loopback=True, allow_http=True,
                             allowed_ports=frozenset({parts.port or 80}), max_request_bytes=256 * 1024,
                             max_response_bytes=512 * 1024, timeout=timeout, max_redirects=0)
        self.digest: str | None = None

    @property
    def model_id(self) -> str:
        return f"{self.model}@{self.digest[:12]}" if self.digest else self.model

    def identify(self, timeout: float | None = None) -> str:
        """Confirm the pinned model is installed locally and record its digest."""
        pol = self.policy if timeout is None else Policy(**{**self.policy.__dict__, "timeout": timeout})
        try:
            r = self.gw.request("GET", f"{self.base}/api/tags", pol, summary={"endpoint": "/api/tags"})
        except GatewayDenied as ex:
            raise ModelUnavailable(f"ollama_unreachable:{ex.reason}")
        if r.status != 200:
            raise ModelUnavailable(f"ollama_http_{r.status}")
        try:
            models = json.loads(r.body).get("models", [])
        except ValueError:
            raise ModelUnavailable("ollama_response_invalid")
        m = next((m for m in models if m.get("name") == self.model or m.get("model") == self.model), None)
        if m is None:
            raise ModelUnavailable("model_not_installed")
        self.digest = m.get("digest") or None
        if not self.digest:
            raise ModelUnavailable("model_identity_unknown")
        return self.model_id

    def chat(self, system: str, user: str, schema: dict, deadline: float) -> ChatResult:
        body = {
            "model": self.model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "options": {"temperature": 0, "num_ctx": self.context_tokens, "num_predict": self.max_output},
            "keep_alive": "5m",
        }
        try:
            r = self.gw.request("POST", f"{self.base}/api/chat", self.policy, json_body=body, deadline=deadline,
                                summary={"endpoint": "/api/chat", "model": self.model, "prompt_bytes": len(system) + len(user)})
        except GatewayDenied as ex:
            raise ModelUnavailable(f"ollama_call_failed:{ex.reason}")
        if r.status != 200:
            raise ModelUnavailable(f"ollama_http_{r.status}")
        try:
            data = json.loads(r.body)
            content = data["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise ModelUnavailable("ollama_response_invalid")
        return ChatResult(content, int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0))


def monotonic_deadline(seconds: float) -> float:
    return time.monotonic() + max(0.5, seconds)
