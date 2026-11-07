"""Client tokens, grants and workspace-scoped authorization."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from ..contracts.enums import Capability, Disclosure
from ..errors import ApiError, not_found
from ..storage.repo import Repo

TOKEN_PREFIX = "tf_"


def generate_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class Grant:
    workspace_id: str
    capabilities: frozenset[Capability]
    disclosure: Disclosure


@dataclass
class Principal:
    client_id: str
    name: str
    grants: dict[str, Grant] = field(default_factory=dict)

    def grant(self, ws_id: str) -> Grant:
        g = self.grants.get(ws_id)
        if g is None:
            raise not_found()  # non-enumerating
        return g

    def require(self, ws_id: str, cap: Capability) -> Grant:
        g = self.grant(ws_id)
        if cap not in g.capabilities:
            raise ApiError(403, "forbidden", f"This client lacks the '{cap.value}' capability for this workspace.")
        return g


def authenticate(repo: Repo, authorization: str | None) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "unauthenticated", "A valid bearer token is required.")
    token = authorization[len("Bearer "):].strip()
    if not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        raise ApiError(401, "unauthenticated", "A valid bearer token is required.")
    th = hash_token(token)
    client = repo.client_by_token_hash(th)
    if client is None or not hmac.compare_digest(client["token_hash"], th):
        raise ApiError(401, "unauthenticated", "A valid bearer token is required.")
    p = Principal(client_id=client["id"], name=client["name"])
    for g in repo.grants_for(client["id"]):
        p.grants[g["workspace_id"]] = Grant(
            workspace_id=g["workspace_id"],
            capabilities=frozenset(Capability(c) for c in g["capabilities"]),
            disclosure=Disclosure(g["disclosure"]),
        )
    return p
