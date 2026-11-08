"""HTTP boundary: routing, auth, host/origin checks and error mapping. No detection logic here."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..contracts.enums import Check
from ..contracts.models import (
    ActionOut, ActionPage, ApproveRequest, EditActionRequest, MarkSubmittedRequest, RejectRequest,
    CompanyIn, CompanyOut, CompanyProfileIn, SitesIn, SitesOut, CompanyProfileList, CompanyProfileOut, QueryPlanIn, QueryPlanOut, QueryPlanPage, QueryPresetCatalog, SourcePage,
    CapabilitiesOut, CaptureRequest, ErrorEnvelope, EvidenceOut, FindingDetail, FindingOut, FindingPage, InputOut,
    LedgerPage, ManifestOut, RecheckAccepted, RecheckRequest, ReviewRequest, ScanAccepted, ScanList, ScanOut, ScanRequest, WorkspaceList,
    WorkspaceOut,
)
from ..engine import Engine
from ..errors import ApiError
from ..jobs.pipeline import ENGINE_VERSION
from ..policy.auth import Principal, authenticate
from ..util import new_id

log = logging.getLogger("tracefold.api")

ERRORS = {s: {"model": ErrorEnvelope} for s in (401, 403, 404, 409, 410, 413, 422, 429)}


def _envelope(status: int, code: str, message: str, retryable: bool, request_id: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "retryable": retryable},
                                                     "request_id": request_id})


def create_app(engine: Engine) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not engine.started:
            engine.startup()
        yield
        engine.shutdown()

    app = FastAPI(title="Tracefold engine", version=ENGINE_VERSION, lifespan=lifespan,
                  description="Shared private scan engine for the Tracefold upload app and MCP adapter.")
    app.state.engine = engine
    settings = engine.settings

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        rid = new_id("req")
        request.state.request_id = rid
        host = (request.headers.get("host") or "").rsplit(":", 1)[0] if not (request.headers.get("host") or "").startswith("[") \
            else (request.headers.get("host") or "").split("]")[0] + "]"
        if host not in settings.allowed_hosts:
            return _envelope(400, "invalid_host", "Unexpected Host header.", False, rid)
        origin = request.headers.get("origin")
        if origin is not None and origin not in settings.allowed_origins:
            return _envelope(403, "invalid_origin", "This browser origin is not allowed.", False, rid)
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        if origin is not None:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return _envelope(exc.status, exc.code, exc.message, exc.retryable, request.state.request_id)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(x) for x in e.get("loc", [])[1:]) for e in exc.errors()})
        return _envelope(422, "invalid_request", "Invalid request fields: " + ", ".join(fields)[:300], False,
                         request.state.request_id)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _envelope(exc.status_code, code, "Resource not found." if exc.status_code == 404 else "Request not allowed.",
                         False, request.state.request_id)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        log.error("unhandled %s on %s", type(exc).__name__, request.url.path)
        return _envelope(500, "internal_error", "Internal error.", True, request.state.request_id)

    def principal(authorization: str | None = Header(default=None)) -> Principal:
        return authenticate(engine.repo, authorization)

    # ---------------- routes ----------------
    @app.get("/v1/health")
    def health():
        return {"status": "ok"}

    @app.get("/v1/capabilities", response_model=CapabilitiesOut, responses=ERRORS)
    def capabilities(p: Principal = Depends(principal)):
        from ..checks.rules import RULES
        lim = settings.limits
        return CapabilitiesOut(
            engine_version=ENGINE_VERSION, checks=[Check.public_match, Check.local_risk],
            supported_inputs=["text/plain (.txt, .md)", "code (UTF-8; local rules for Python)", "docx"],
            local_risk_rules=[r for r in RULES],
            model=engine.reviewer.status(),
            limits={"max_files_per_capture": lim.max_files_per_capture, "max_file_bytes": lim.max_file_bytes,
                    "max_request_bytes": lim.max_request_bytes, "max_queued_scans": lim.max_queued_scans,
                    "scan_deadline_seconds": lim.scan_deadline_seconds, "max_public_pages": lim.max_public_pages,
                    "capture_ttl_seconds": lim.capture_ttl_seconds, "max_model_requests": lim.max_model_requests},
            client_capabilities={ws: sorted(g.capabilities, key=lambda c: c.value) for ws, g in p.grants.items()},
            remediation=engine.remediation.status(),
        )

    @app.get("/v1/workspaces", response_model=WorkspaceList, responses=ERRORS)
    def workspaces(p: Principal = Depends(principal)):
        items = []
        for ws_id, g in sorted(p.grants.items()):
            ws = engine.repo.get_workspace(ws_id)
            if ws:
                items.append(WorkspaceOut(id=ws["id"], name=ws["name"], source_type=ws["source_type"], revision=ws["revision"],
                                          capabilities=sorted(g.capabilities, key=lambda c: c.value), disclosure=g.disclosure,
                                          manifests=engine.repo.list_manifests(ws_id)))
        return WorkspaceList(items=items)

    @app.get("/v1/workspaces/{ws_id}/manifests/{manifest_id}", response_model=ManifestOut, responses=ERRORS)
    def get_manifest(ws_id: str, manifest_id: str, p: Principal = Depends(principal)):
        from ..contracts.enums import Capability
        from ..errors import not_found
        p.require(ws_id, Capability.read)
        m = engine.repo.get_manifest(ws_id, manifest_id)
        if m is None:
            raise not_found()
        return ManifestOut(
            manifest_id=m["id"], version=m["version"],
            sources=[{"source_id": x["source_id"], "url": x["url"], "provider": x["provider"], "mode": x.get("mode", "seeded")}
                     for x in m["sources"]],
            outbound_note="Only these approved URLs (and provider authentication) are sent outside the engine; "
                          "private file text is never used as a query.")

    @app.post("/v1/workspaces/{ws_id}/uploads", response_model=InputOut, status_code=201, responses=ERRORS)
    async def upload(ws_id: str, request: Request, p: Principal = Depends(principal)):
        p.grant(ws_id)
        limit = settings.limits.max_request_bytes
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            raise ApiError(413, "request_too_large", "The upload exceeds the request size limit.")
        buf = bytearray()
        async for chunk in request.stream():
            buf.extend(chunk)
            if len(buf) > limit:
                raise ApiError(413, "request_too_large", "The upload exceeds the request size limit.")
        return engine.inputs.upload(p, ws_id, request.headers.get("content-type"), bytes(buf))

    @app.post("/v1/workspaces/{ws_id}/captures", response_model=InputOut, status_code=201, responses=ERRORS)
    def capture(ws_id: str, body: CaptureRequest, p: Principal = Depends(principal)):
        return engine.inputs.capture(p, ws_id, body)

    @app.post("/v1/workspaces/{ws_id}/scans", response_model=ScanAccepted, status_code=202, responses=ERRORS)
    def submit_scan(ws_id: str, body: ScanRequest, p: Principal = Depends(principal),
                    idempotency_key: str | None = Header(default=None)):
        return engine.scans.submit(p, ws_id, body, idempotency_key)

    @app.get("/v1/workspaces/{ws_id}/scans", response_model=ScanList, responses=ERRORS)
    def list_scans(ws_id: str, cursor: str | None = None, limit: int = Query(default=20, ge=1, le=100),
                   p: Principal = Depends(principal)):
        return engine.scans.list(p, ws_id, cursor, limit)

    @app.delete("/v1/workspaces/{ws_id}/scans", responses=ERRORS)
    def delete_all_scans(ws_id: str, p: Principal = Depends(principal)) -> dict[str, int]:
        """Delete every finished scan and the findings and actions only they produced (requires `configure`)."""
        return engine.scans.delete(p, ws_id, None)

    @app.delete("/v1/workspaces/{ws_id}/scans/{scan_id}", responses=ERRORS)
    def delete_scan(ws_id: str, scan_id: str, p: Principal = Depends(principal)) -> dict[str, int]:
        """Delete one finished scan and the findings and actions only it produced (requires `configure`)."""
        return engine.scans.delete(p, ws_id, scan_id)

    @app.get("/v1/workspaces/{ws_id}/scans/{scan_id}", response_model=ScanOut, responses=ERRORS)
    def get_scan(ws_id: str, scan_id: str, p: Principal = Depends(principal)):
        return engine.scans.get(p, ws_id, scan_id)

    @app.post("/v1/workspaces/{ws_id}/scans/{scan_id}/cancel", response_model=ScanOut, status_code=202, responses=ERRORS)
    def cancel_scan(ws_id: str, scan_id: str, p: Principal = Depends(principal)):
        return engine.scans.cancel(p, ws_id, scan_id)

    @app.get("/v1/workspaces/{ws_id}/findings", response_model=FindingPage, responses=ERRORS)
    def list_findings(ws_id: str, scan_id: str | None = None, cursor: str | None = None,
                      limit: int = Query(default=50, ge=1, le=100), p: Principal = Depends(principal)):
        return engine.findings.list(p, ws_id, scan_id, cursor, limit)

    @app.get("/v1/workspaces/{ws_id}/findings/{finding_id}", response_model=FindingDetail, responses=ERRORS)
    def get_finding(ws_id: str, finding_id: str, p: Principal = Depends(principal)):
        return engine.findings.detail(p, ws_id, finding_id)

    @app.get("/v1/workspaces/{ws_id}/evidence/{evidence_id}", response_model=EvidenceOut, responses=ERRORS)
    def get_evidence(ws_id: str, evidence_id: str, p: Principal = Depends(principal)):
        return engine.findings.evidence(p, ws_id, evidence_id)

    @app.post("/v1/workspaces/{ws_id}/findings/{finding_id}/rechecks", response_model=RecheckAccepted, status_code=202,
              responses=ERRORS)
    def recheck(ws_id: str, finding_id: str, body: RecheckRequest, p: Principal = Depends(principal),
                idempotency_key: str | None = Header(default=None)):
        return engine.findings.recheck(p, ws_id, finding_id, body, idempotency_key)

    @app.patch("/v1/workspaces/{ws_id}/findings/{finding_id}/review", response_model=FindingOut, responses=ERRORS)
    def review(ws_id: str, finding_id: str, body: ReviewRequest, p: Principal = Depends(principal)):
        return engine.findings.review(p, ws_id, finding_id, body)

    @app.get("/v1/workspaces/{ws_id}/scans/{scan_id}/ledger", response_model=LedgerPage, responses=ERRORS)
    def ledger(ws_id: str, scan_id: str, cursor: str | None = None, limit: int = Query(default=50, ge=1, le=100),
               p: Principal = Depends(principal)):
        return engine.scans.ledger(p, ws_id, scan_id, cursor, limit)

    # ---------------- remediation actions (approval-gated) ----------------
    @app.get("/v1/workspaces/{ws_id}/actions", response_model=ActionPage, responses=ERRORS)
    def list_actions(ws_id: str, status: str | None = None, finding_id: str | None = None, cursor: str | None = None,
                     limit: int = Query(default=50, ge=1, le=100), p: Principal = Depends(principal)):
        return engine.remediation.list(p, ws_id, status, finding_id, cursor, limit)

    @app.get("/v1/workspaces/{ws_id}/actions/{action_id}", response_model=ActionOut, responses=ERRORS)
    def get_action(ws_id: str, action_id: str, p: Principal = Depends(principal)):
        return engine.remediation.get(p, ws_id, action_id)

    @app.patch("/v1/workspaces/{ws_id}/actions/{action_id}", response_model=ActionOut, responses=ERRORS)
    def edit_action(ws_id: str, action_id: str, body: EditActionRequest, p: Principal = Depends(principal)):
        return engine.remediation.edit(p, ws_id, action_id, body)

    @app.post("/v1/workspaces/{ws_id}/actions/{action_id}/approve", response_model=ActionOut, responses=ERRORS)
    def approve_action(ws_id: str, action_id: str, body: ApproveRequest, p: Principal = Depends(principal)):
        return engine.remediation.approve(p, ws_id, action_id, body)

    @app.post("/v1/workspaces/{ws_id}/actions/{action_id}/reject", response_model=ActionOut, responses=ERRORS)
    def reject_action(ws_id: str, action_id: str, body: RejectRequest, p: Principal = Depends(principal)):
        return engine.remediation.reject(p, ws_id, action_id, body)

    @app.post("/v1/workspaces/{ws_id}/actions/{action_id}/mark-submitted", response_model=ActionOut, responses=ERRORS)
    def mark_submitted(ws_id: str, action_id: str, body: MarkSubmittedRequest, p: Principal = Depends(principal)):
        return engine.remediation.mark_submitted(p, ws_id, action_id, body)

    # ---------------- company discovery ----------------
    @app.get("/v1/workspaces/{ws_id}/sites", response_model=SitesOut, responses=ERRORS)
    def get_sites(ws_id: str, p: Principal = Depends(principal)):
        """Pages checked in every public scan, and hosts never fetched."""
        return engine.discovery.get_sites(p, ws_id)

    @app.put("/v1/workspaces/{ws_id}/sites", response_model=SitesOut, responses=ERRORS)
    def put_sites(ws_id: str, body: SitesIn, p: Principal = Depends(principal)):
        """Replace both lists (requires `configure`). Never-fetch hosts include their subdomains."""
        return engine.discovery.put_sites(p, ws_id, body)

    @app.get("/v1/workspaces/{ws_id}/company", response_model=CompanyOut, responses=ERRORS)
    def get_company(ws_id: str, p: Principal = Depends(principal)):
        """The workspace's own company: name, website and takedown reply-to."""
        return engine.discovery.get_company(p, ws_id)

    @app.put("/v1/workspaces/{ws_id}/company", response_model=CompanyOut, responses=ERRORS)
    def put_company(ws_id: str, body: CompanyIn, p: Principal = Depends(principal)):
        """Set the company (requires `configure`). Its name is searched in every public check alongside names found in
        the files, and takedown requests are signed with it."""
        return engine.discovery.put_company(p, ws_id, body)

    @app.post("/v1/workspaces/{ws_id}/company-profiles", response_model=CompanyProfileOut, status_code=201, responses=ERRORS)
    def create_company_profile(ws_id: str, body: CompanyProfileIn, p: Principal = Depends(principal)):
        """Approve a public company identity (requires the `configure` capability). Creates a new immutable version
        when `profile_id` is given."""
        return engine.discovery.create_profile(p, ws_id, body)

    @app.get("/v1/workspaces/{ws_id}/company-profiles", response_model=CompanyProfileList, responses=ERRORS)
    def list_company_profiles(ws_id: str, p: Principal = Depends(principal)):
        """Approved public identities (latest version of each)."""
        return engine.discovery.list_profiles(p, ws_id)

    @app.get("/v1/workspaces/{ws_id}/company-profiles/{profile_id}", response_model=CompanyProfileOut, responses=ERRORS)
    def get_company_profile(ws_id: str, profile_id: str, p: Principal = Depends(principal)):
        return engine.discovery.get_profile(p, ws_id, profile_id)

    @app.get("/v1/query-presets", response_model=QueryPresetCatalog, responses=ERRORS)
    def query_presets(p: Principal = Depends(principal)):
        """Fixed preset catalog: per-provider templates, status (benchmarked/experimental/legacy), packs, site groups,
        noise domains and budget shapes."""
        return engine.discovery.preset_catalog(p)

    @app.post("/v1/workspaces/{ws_id}/query-plans", response_model=QueryPlanOut, status_code=201, responses=ERRORS)
    def create_query_plan(ws_id: str, body: QueryPlanIn, p: Principal = Depends(principal)):
        """Create an immutable plan of exact outbound searches from an approved profile, fixed presets, providers and
        a public-site scope (requires `configure`)."""
        return engine.discovery.create_plan(p, ws_id, body)

    @app.get("/v1/workspaces/{ws_id}/query-plans", response_model=QueryPlanPage, responses=ERRORS)
    def list_query_plans(ws_id: str, cursor: str | None = None, limit: int = Query(default=50, ge=1, le=100),
                         p: Principal = Depends(principal)):
        return engine.discovery.list_plans(p, ws_id, cursor, limit)

    @app.get("/v1/workspaces/{ws_id}/query-plans/{plan_id}", response_model=QueryPlanOut, responses=ERRORS)
    def get_query_plan(ws_id: str, plan_id: str, p: Principal = Depends(principal)):
        """Preview the exact outbound queries, providers, domain scope and budget."""
        return engine.discovery.get_plan(p, ws_id, plan_id)

    @app.get("/v1/workspaces/{ws_id}/scans/{scan_id}/sources", response_model=SourcePage, responses=ERRORS)
    def scan_sources(ws_id: str, scan_id: str, cursor: str | None = None, limit: int = Query(default=50, ge=1, le=100),
                     p: Principal = Depends(principal)):
        """Complete source list for a scan, including no-match, failed, blocked and skipped candidates, with
        discovery provenance."""
        return engine.discovery.sources(p, ws_id, scan_id, cursor, limit)

    return app
