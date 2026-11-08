"""MCP tools → engine HTTP endpoints.

Every tool is a thin mapping (docs/ENGINE_API.md, "Endpoints and MCP tool mapping"). The adapter never
decides whether something is risky, never invents a "safe"/"fixed" verdict, and never generates its own
explanation: it returns what the engine stored, grouped and labelled with the engine's vocabulary. What the
host model sees is governed by the engine's per-client disclosure policy (``full`` or ``minimal``).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import Field

from .config import AdapterConfig
from .engine import TERMINAL, EngineClient, EngineError

INSTRUCTIONS = """Tracefold checks work in the approved workspace for two separate things:
1. Potential risks in your files (local_risk): e.g. secret literals or sensitive values written to logs.
2. Public exposure (public_match): passages that also appear on operator-approved public sources.

Workflow: call scan_changes after editing files and before reporting work as complete. If the scan is still
running, call get_scan until it finishes, then get_findings. Use explain_finding for evidence, conditions and the
stored suggested fix. After the user's editor workflow applies a fix, call recheck_fix.

Report results in Tracefold's own terms. "completed" means the requested checks finished within their stated
coverage, not that there are no risks. A recheck outcome of not_detected_in_checked_version is not proof that
something is "fixed", and a local recheck never closes a public-exposure finding. Never claim a file is "safe"."""

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
SUBMIT = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False)

WorkspaceArg = Annotated[str | None, Field(default=None, description="Workspace ID; defaults to the configured workspace.")]
WaitArg = Annotated[float, Field(ge=0, le=25, description="Seconds to wait for the scan before returning (0–25). "
                                                           "Long scans keep running; poll get_scan.")]

STATE_MEANING = {
    "queued": "Waiting to run. Poll get_scan.",
    "running": "Still running. Poll get_scan.",
    "completed": "Every requested check finished within its stated coverage. This does not mean there are no risks.",
    "partial": "Some requested checks or coverage did not finish; results exist but are incomplete. See coverage and errors.",
    "failed": "No usable requested analysis completed. See errors.",
    "cancelled": "Cancelled; any completed observations are partial evidence only.",
    "interrupted": "The engine restarted during the scan. Capture and scan again.",
}

RECHECK_MEANING = {
    "still_detected": "The same check still detects this issue in the checked version.",
    "not_detected_in_checked_version": "The same check no longer detects it in the checked version, with equivalent "
                                       "coverage. This is not a comprehensive 'fixed' verdict.",
    "inconclusive": "The recheck could not establish either outcome; see reason.",
}


def _fail(e: EngineError) -> ToolError:
    import json
    return ToolError(json.dumps({"error": e.as_dict()}))


def _scan_view(s: dict) -> dict:
    return {"done": s["state"] in TERMINAL, "state_meaning": STATE_MEANING.get(s["state"], ""), "scan": s}


def _coverage_notes(scan: dict, counts: dict[str, int]) -> dict[str, str]:
    """Explicit empty/incomplete statements, derived only from engine coverage (ENGINE_API "Empty results")."""
    notes: dict[str, str] = {}
    checks = {c["id"]: c for c in scan.get("coverage", []) if c.get("scope") == "check"}
    files = [c for c in scan.get("coverage", []) if c.get("scope") == "file"]
    pm = checks.get("public_match")
    if pm is None or pm["status"] == "not_requested":
        notes["public_exposure"] = "Public matching was not requested for this scan. This is not a 'no match' result."
    elif pm["status"] != "complete":
        notes["public_exposure"] = f"Public matching {pm['status']}: {pm.get('reason') or 'see scan coverage'}."
    elif counts["public_exposure"] == 0:
        notes["public_exposure"] = f"No match in {pm.get('counts', {}).get('sources_ok', 0)} checked sources."
    lr = checks.get("local_risk")
    if lr is None or lr["status"] == "not_requested":
        notes["local_risk"] = "Local risk review was not requested for this scan."
    elif lr["status"] != "complete":
        notes["local_risk"] = f"Local risk review {lr['status']}: {lr.get('reason') or 'see scan coverage'}."
    elif counts["local_risk"] == 0:
        n = lr.get("counts", {}).get("files", len(files))
        notes["local_risk"] = f"No potential risks identified by this review ({n} file(s) covered by local_risk)."
    return notes


def build_server(config: AdapterConfig, engine: EngineClient | None = None) -> MCPServer:
    holder: dict[str, EngineClient] = {}

    @asynccontextmanager
    async def lifespan(_server: MCPServer):
        holder["engine"] = engine or EngineClient(config)
        try:
            yield {}
        finally:
            if engine is None:
                await holder["engine"].aclose()

    mcp = MCPServer(name="tracefold", title="Tracefold", instructions=INSTRUCTIONS, version="0.1.0", lifespan=lifespan)

    def eng() -> EngineClient:
        return holder.get("engine") or engine or holder.setdefault("engine", EngineClient(config))

    @mcp.tool(annotations=READ)
    async def get_capabilities() -> dict:
        """Engine readiness: supported checks and inputs, local risk rules, model availability, limits and this
        client's capabilities per workspace."""
        try:
            return await eng().capabilities()
        except EngineError as e:
            raise _fail(e) from None

    @mcp.tool(annotations=READ)
    async def list_workspaces() -> dict:
        """Workspaces this adapter's client is granted, with its capabilities and disclosure policy for each."""
        try:
            out = await eng().workspaces()
        except EngineError as e:
            raise _fail(e) from None
        return {"default_workspace_id": config.workspace_id, **out}

    @mcp.tool(annotations=SUBMIT)
    async def scan_changes(
        mode: Annotated[Literal["changes", "files"], Field(
            description="'changes': staged/unstaged Git changes against baseline. 'files': the listed workspace paths.")] = "changes",
        paths: Annotated[list[str] | None, Field(default=None, max_length=100,
                                                 description="Workspace-relative paths (mode='files' only).")] = None,
        baseline: Annotated[str, Field(max_length=200, description="Git baseline for mode='changes'.")] = "HEAD",
        include_untracked: Annotated[bool, Field(description="Include permitted untracked files (mode='changes').")] = True,
        check_public_sources: Annotated[str | None, Field(
            default=None, max_length=100,
            description="Operator-approved manifest ID to also check for public exposure (see list_workspaces).")] = None,
        model_review: Annotated[bool, Field(description="Ask the engine's local model to review rule candidates.")] = True,
        wait_seconds: WaitArg = 10,
        workspace_id: WorkspaceArg = None,
    ) -> dict:
        """Capture workspace changes (or listed files) and queue a Tracefold scan. Returns the capture summary and
        the scan's current state. Call this after editing and before reporting work as complete."""
        if mode == "files" and not paths:
            raise ToolError('{"error": {"code": "invalid_request", "message": "mode=files needs paths.", "retryable": false}}')
        body: dict[str, Any] = ({"mode": "files", "paths": paths} if mode == "files"
                                else {"mode": "changes", "baseline": baseline, "include_untracked": include_untracked})
        try:
            cap = await eng().capture(workspace_id, body)
            req: dict[str, Any] = {"input_id": cap["input_id"], "checks": ["local_risk"], "model_review": model_review}
            if check_public_sources:
                req["checks"] = ["public_match", "local_risk"]
                req["public_sources"] = {"manifest_id": check_public_sources, "mode": "refresh"}
            acc = await eng().submit_scan(workspace_id, req)
            scan = await eng().wait_for_scan(workspace_id, acc["scan_id"], wait_seconds)
        except EngineError as e:
            raise _fail(e) from None
        return {"capture": {k: cap.get(k) for k in ("input_id", "revision", "baseline", "expires_at", "files", "omitted_context")},
                **_scan_view(scan)}

    @mcp.tool(annotations=READ)
    async def get_scan(scan_id: str, wait_seconds: WaitArg = 0, workspace_id: WorkspaceArg = None) -> dict:
        """A scan's state, stages, per-check/source/file coverage, budget, versions and errors."""
        try:
            return _scan_view(await eng().wait_for_scan(workspace_id, scan_id, wait_seconds))
        except EngineError as e:
            raise _fail(e) from None

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=True,
                                          open_world_hint=False))
    async def cancel_scan(scan_id: str, workspace_id: WorkspaceArg = None) -> dict:
        """Request cooperative cancellation of a queued or running scan."""
        try:
            return _scan_view(await eng().cancel(workspace_id, scan_id))
        except EngineError as e:
            raise _fail(e) from None

    @mcp.tool(annotations=READ)
    async def get_findings(
        scan_id: Annotated[str | None, Field(default=None, description="Restrict to one scan (recommended).")] = None,
        cursor: str | None = None,
        limit: Annotated[int, Field(ge=1, le=100)] = 50,
        workspace_id: WorkspaceArg = None,
    ) -> dict:
        """Findings with their latest observation, in two sections: public_exposure and local_risk
        ("Potential risks in your files"). With scan_id, also states coverage for empty sections."""
        try:
            page = await eng().findings(workspace_id, scan_id, cursor, limit)
            scan = await eng().scan(workspace_id, scan_id) if scan_id else None
        except EngineError as e:
            raise _fail(e) from None
        groups: dict[str, list] = {"public_exposure": [], "local_risk": []}
        for f in page["items"]:
            groups.setdefault(f["kind"], []).append(f)
        out: dict[str, Any] = {**groups, "next_cursor": page.get("next_cursor")}
        if scan is not None:
            out["scan_state"] = scan["state"]
            out["scan_done"] = scan["state"] in TERMINAL
            if not cursor:
                out["coverage_notes"] = _coverage_notes(scan, {k: len(v) for k, v in groups.items()})
        return out

    @mcp.tool(annotations=READ)
    async def explain_finding(
        finding_id: str,
        include_evidence: Annotated[bool, Field(
            description="Also fetch evidence text for the latest observation, if this client's policy permits.")] = False,
        workspace_id: WorkspaceArg = None,
    ) -> dict:
        """The engine's stored explanation of a finding: observations (claim, conditions, uncertainty, suggested
        fix, risk review), status, human review and recheck history. Never a newly generated explanation."""
        try:
            detail = await eng().finding(workspace_id, finding_id)
        except EngineError as e:
            raise _fail(e) from None
        out: dict[str, Any] = {"finding": detail}
        if include_evidence and detail.get("latest"):
            evidence = []
            for ref in detail["latest"].get("evidence", []):
                try:
                    evidence.append(await eng().evidence(workspace_id, ref["evidence_id"]))
                except EngineError as e:  # e.g. 403 without read_evidence: report, don't fail the explanation
                    evidence.append({"evidence_id": ref["evidence_id"], "error": e.as_dict()})
            out["evidence"] = evidence
        return out

    @mcp.tool(annotations=SUBMIT)
    async def recheck_fix(
        finding_id: str,
        paths: Annotated[list[str] | None, Field(
            default=None, max_length=100,
            description="Paths to capture if the finding's path is withheld by policy. Defaults to the finding's file.")] = None,
        wait_seconds: WaitArg = 10,
        workspace_id: WorkspaceArg = None,
    ) -> dict:
        """After a fix is applied in the editor, capture the current file and rerun the same check for this finding.
        Outcome is still_detected, not_detected_in_checked_version or inconclusive — never 'fixed'."""
        try:
            detail = await eng().finding(workspace_id, finding_id)
            target = paths or ([detail["path"]] if detail.get("path") else None)
            body = ({"mode": "files", "paths": target} if target
                    else {"mode": "changes", "baseline": "HEAD", "include_untracked": True})
            cap = await eng().capture(workspace_id, body)
            req: dict[str, Any] = {"input_id": cap["input_id"]}
            if detail.get("latest"):
                req["observation_id"] = detail["latest"]["observation_id"]
            acc = await eng().recheck(workspace_id, finding_id, req)
            scan = await eng().wait_for_scan(workspace_id, acc["scan_id"], wait_seconds)
            after = await eng().finding(workspace_id, finding_id) if scan["state"] in TERMINAL else None
        except EngineError as e:
            raise _fail(e) from None
        out: dict[str, Any] = {"recheck_id": acc["recheck_id"], **_scan_view(scan)}
        if after is not None:
            rc = next((r for r in after.get("rechecks", []) if r["recheck_id"] == acc["recheck_id"]), None)
            out["outcome"] = rc and rc.get("outcome")
            out["reason"] = rc and rc.get("reason")
            out["outcome_meaning"] = RECHECK_MEANING.get(out["outcome"] or "", "")
            out["finding_status"] = after["status"]
            if after["kind"] == "public_exposure":
                out["note"] = "Public-exposure status changes only after a fresh, successful public retrieval."
        else:
            out["note"] = "Recheck still running; call get_scan with this scan_id, then explain_finding."
        return out

    return mcp
