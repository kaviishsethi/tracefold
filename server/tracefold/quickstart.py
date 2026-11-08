"""One-command local setup, designed so a coding agent can finish it unattended.

``tracefold quickstart --root <folder>``:
1. creates or migrates the database,
2. registers the folder as a workspace (reused if it already exists),
3. optionally registers public URLs to check (``--public-url``, repeatable),
4. creates fresh tokens for the web app and the MCP adapter (older quickstart tokens are revoked),
5. writes ``frontend/.env.local`` and the MCP adapter config, both readable only by you,
6. prints the commands that are left. Tokens are never printed.

Re-running is safe: it reuses the workspace and rotates the tokens.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .contracts.enums import Capability
from .util import iso, now

REPO = Path(__file__).resolve().parents[2]
APP_PREFIX = "web-app"
MCP_PREFIX = "coding-assistant"
# The assistant can scan, read and recheck, but never approve takedowns or key changes.
MCP_CAPS = [Capability.submit, Capability.read, Capability.read_evidence, Capability.recheck, Capability.cancel]


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(path, 0o600)


def _rotate(engine, prefix: str, ws_id: str, caps: list[Capability]) -> str:
    for c in engine.repo.clients_with_prefix(prefix + "-"):
        if not c["revoked_at"]:
            engine.repo.revoke_client(c["id"])
    name = f"{prefix}-{now().strftime('%Y%m%d%H%M%S%f')}"
    return engine.add_client(name, {ws_id: (caps, "full")})


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return ("ws_" + s)[:40] or "ws_main"


def _company(engine, ws_id: str, company: str, domain: str | None, reply_to: str | None) -> dict:
    """Sign takedowns as this company, approve it as the public identity for discovery, and create a first plan.
    Re-running reuses a matching identity and plan instead of adding duplicates."""
    from .discovery import identity, presets

    out: dict = {}
    if reply_to:
        engine.set_remediation_profile(ws_id, company, reply_to)
        out["takedown_signer"] = company
    clean = identity.validate_profile(company, domain, [])
    prof = next((p for p in engine.repo.list_profiles(ws_id)
                 if p["display_name"] == clean["display_name"] and p["official_domain"] == clean["official_domain"]), None)
    if prof is None:
        from .util import new_id
        pid = new_id("cprof")
        version = engine.repo.insert_profile_version({"id": pid, "workspace_id": ws_id, **clean, "approved_by": "operator:quickstart",
                                                      "approved_at": iso(now()), "privacy_notice_version": identity.PRIVACY_NOTICE_VERSION})
        prof = engine.repo.get_profile(ws_id, pid, version)
    out["identity"] = {"profile_id": prof["id"], "version": prof["version"], "display_name": prof["display_name"]}
    providers = [p for p, key in (("exa", "EXA_API_KEY"), ("tavily", "TAVILY_API_KEY")) if os.environ.get(key)]
    if not providers:
        out["plan"] = None
        out["plan_note"] = "No EXA_API_KEY or TAVILY_API_KEY set, so no discovery plan yet. Add one to server/.env and re-run."
        return out
    existing = next((r for r in engine.repo.list_query_plans(ws_id, None, 100)
                     if r["profile_id"] == prof["id"] and r["profile_version"] == prof["version"]
                     and r["plan"].get("pack") == "broad_triage"
                     and sorted({s["provider"] for s in r["plan"]["searches"]}) == sorted(providers)), None)
    if existing is None:
        from .util import new_id
        profile = {k: prof[k] for k in ("display_name", "official_domain", "public_aliases")}
        plan = presets.build_plan(profile, None, "broad_triage", providers, {"mode": "broad"}, None)
        existing = {"id": new_id("qplan"), "workspace_id": ws_id, "profile_id": prof["id"], "profile_version": prof["version"],
                    "profile": profile, "plan": plan, "created_by": "operator:quickstart", "created_at": iso(now())}
        engine.repo.insert_query_plan(existing)
    out["plan"] = {"query_plan_id": existing["id"], "pack": "broad_triage", "searches": len(existing["plan"]["searches"]),
                   "providers": providers}
    return out


def run(engine, root: str, workspace: str | None, name: str | None, port: int, public_urls: list[str],
        frontend_env: str | None, mcp_config: str | None, company: str | None = None, domain: str | None = None,
        reply_to: str | None = None) -> dict:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise SystemExit(f"tracefold quickstart: {root_path} is not a folder")
    ws_id = workspace or _slug(root_path.name)
    ws = engine.repo.get_workspace(ws_id)
    created = ws is None
    if created:
        engine.add_workspace(ws_id, name or root_path.name, str(root_path))
    elif ws["root"] != str(root_path):
        raise SystemExit(f"tracefold quickstart: workspace {ws_id} already points at {ws['root']}. "
                         f"Pass --workspace with a new id to register {root_path}.")

    sources = None
    if public_urls:
        entries = [{"source_id": f"page{i + 1}", "url": u, "provider": "direct"} for i, u in enumerate(public_urls)]
        version = engine.add_manifest(ws_id, "public", entries)
        sources = {"manifest_id": "public", "version": version, "count": len(entries)}

    company_out = _company(engine, ws_id, company, domain, reply_to) if company else None

    app_token = _rotate(engine, APP_PREFIX, ws_id, list(Capability))
    mcp_token = _rotate(engine, MCP_PREFIX, ws_id, MCP_CAPS)
    base = f"http://127.0.0.1:{port}"

    env_path = Path(frontend_env).expanduser() if frontend_env else REPO / "frontend" / ".env.local"
    _write_private(env_path, f"# Written by `tracefold quickstart` on {iso(now())}\n"
                             f"TRACEFOLD_ENGINE_URL={base}\nTRACEFOLD_APP_TOKEN={app_token}\n")
    mcp_path = Path(mcp_config).expanduser() if mcp_config else Path.home() / ".config" / "tracefold" / "mcp.json"
    mcp_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _write_private(mcp_path, json.dumps({"base_url": base, "token": mcp_token, "workspace_id": ws_id}, indent=2) + "\n")

    return {"workspace": ws_id, "workspace_created": created, "root": str(root_path), "public_sources": sources,
            "company": company_out,
            "engine_url": base, "frontend_env": str(env_path), "mcp_config": str(mcp_path),
            "adapter_dir": str(REPO / "adapters" / "mcp"), "frontend_dir": str(REPO / "frontend"),
            "server_dir": str(REPO / "server")}


def describe(r: dict) -> str:
    src = (f"{r['public_sources']['count']} public URL(s) registered as source list 'public'"
           if r["public_sources"] else "No public URLs yet. Add them with --public-url to check for public copies.")
    c = r.get("company")
    lines = []
    if c:
        lines.append(f"Company {c['identity']['display_name']} approved for discovery")
        if c.get("takedown_signer"):
            lines.append(f"Takedown requests will be signed as {c['takedown_signer']}")
        lines.append(f"Discovery plan {c['plan']['query_plan_id']} ({c['plan']['searches']} searches) is ready"
                     if c.get("plan") else c.get("plan_note", ""))
    return "\n".join([
        f"Workspace {r['workspace']} {'created' if r['workspace_created'] else 'reused'} for {r['root']}",
        src,
        *lines,
        f"Web app config written: {r['frontend_env']}",
        f"Coding assistant config written: {r['mcp_config']}",
        "Tokens were rotated; they are in those files and are not shown here.",
        "",
        "Next, each in its own terminal:",
        f"  cd {r['server_dir']} && uv run tracefold serve --port {r['engine_url'].rsplit(':', 1)[1]}",
        f"  cd {r['frontend_dir']} && npm install && npm run dev",
        "Connect your coding assistant (Claude Code shown):",
        f"  claude mcp add tracefold -- uv run --directory {r['adapter_dir']} tracefold-mcp",
        "Then open http://localhost:3000/overview",
    ])
