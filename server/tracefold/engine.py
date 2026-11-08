"""Engine container: wires settings, storage, capture registry, services and the runner."""
from __future__ import annotations

from .config import Settings
from .contracts.enums import Capability, Disclosure
from .inputs.registry import CaptureRegistry
from .jobs.runner import Runner
from .policy.auth import generate_token, hash_token
from .services.inputs import InputService
from .services.scans import ScanService
from .services.store import FindingStore
from .storage.db import Database
from .storage.repo import Repo
from .util import dumps, iso, now


class Hooks:
    """Test seams. Default implementations do nothing."""

    def after_read(self) -> None:
        pass

    def before_stage(self, ctx, name: str) -> None:
        pass


class Engine:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.settings.ensure_dirs()
        self.db = Database(self.settings.db_path)
        self.db.migrate()
        self.repo = Repo(self.db)
        self.registry = CaptureRegistry(self.settings.limits)
        self.hooks = Hooks()
        self.store = FindingStore(self)
        self.runner = Runner(self)
        self.inputs = InputService(self)
        self.scans = ScanService(self)
        from .services.findings import FindingService
        self.findings = FindingService(self)
        from .services.schedules import ScheduleService
        self.schedules = ScheduleService(self)
        self._init_optional()
        self.started = False

    def _init_optional(self) -> None:
        from .retrieval.service import RetrievalService
        from .analysis.review import ModelReviewer
        from .remediation.service import RemediationService
        self.retrieval = RetrievalService(self)
        from .discovery.service import DiscoveryService
        self.discovery = DiscoveryService(self)
        self.reviewer = ModelReviewer(self)
        self.remediation = RemediationService(self)
        from .checks.gitleaks import GitleaksScanner
        self.secret_scanner = GitleaksScanner(self.settings)

    # ---------- lifecycle ----------
    def startup(self) -> None:
        """Recover job state. Previously running jobs become interrupted; queued jobs whose ephemeral
        input no longer exists fail with input_expired (no silent replay of billed provider calls)."""
        self.runner.acquire()
        self.repo.mark_running_interrupted()
        for s in self.repo.queued_scans():
            if self.registry.get(s["input_id"]) is None:
                self.repo.update_scan(s["id"], state="failed", finished_at=iso(now()), errors=dumps([
                    {"code": "input_expired", "message": "The engine restarted; capture this input again.", "retryable": False}]))
                if s["recheck_id"]:
                    self.repo.update_recheck(s["recheck_id"], "inconclusive", "input_expired")
        if self.settings.start_runner:
            self.runner.start()
        self.started = True

    def maintenance(self) -> dict:
        """Retention: keep the latest N scans or D days of metadata (whichever is smaller), never active jobs or
        scans that back findings/rechecks; garbage-collect unreferenced public blobs over the cache cap."""
        from datetime import timedelta
        lim = self.settings.limits
        cutoff = iso(now() - timedelta(days=lim.retained_days))
        pruned = self.repo.prune_scans(lim.retained_scans, cutoff)
        blobs = self.retrieval.blobs.gc(self.repo.referenced_blob_hashes())
        return {"scans_pruned": pruned, "blobs_removed": blobs}

    def shutdown(self) -> None:
        self.runner.stop()
        self.started = False

    # ---------- operator provisioning (CLI / tests; never exposed over HTTP) ----------
    def add_workspace(self, ws_id: str, name: str, root: str | None = None, excludes: list[str] | None = None) -> None:
        self.repo.create_workspace(ws_id, name, "local_dir" if root else "upload_only", root, excludes or [])

    def add_client(self, name: str, grants: dict[str, tuple[list[Capability] | list[str], Disclosure | str]]) -> str:
        token = generate_token()
        cid = self.repo.create_client(name, hash_token(token))
        for ws_id, (caps, disclosure) in grants.items():
            self.repo.put_grant(cid, ws_id, [Capability(c).value for c in caps], Disclosure(disclosure).value)
        return token

    def add_manifest(self, ws_id: str, manifest_id: str, sources: list[dict]) -> int:
        from .retrieval.manifest import validate_sources
        return self.repo.put_manifest(ws_id, manifest_id, validate_sources(sources))

    def set_remediation_profile(self, ws_id: str, company_name: str, reply_to: str) -> None:
        """Company details used to sign takedown requests."""
        if self.repo.get_workspace(ws_id) is None:
            raise ValueError(f"unknown workspace {ws_id}")
        if "@" not in reply_to or not company_name.strip():
            raise ValueError("company name and a reply-to email are required")
        self.repo.put_remediation_profile(ws_id, company_name.strip(), reply_to.strip())

    def add_takedown_contact(self, ws_id: str, host: str, email: str | None = None, form_url: str | None = None) -> None:
        """Where takedown requests for a public host go: its abuse/legal email, or its own removal web form."""
        from urllib.parse import urlsplit
        if self.repo.get_workspace(ws_id) is None:
            raise ValueError(f"unknown workspace {ws_id}")
        if bool(email) == bool(form_url):
            raise ValueError("give exactly one of email or form_url")
        host = host.strip().lower()
        if not host or "/" in host or ":" in host:
            raise ValueError("host must be a bare hostname like pastebin.com")
        if email:
            if "@" not in email or any(c.isspace() for c in email):
                raise ValueError("invalid email")
            self.repo.put_takedown_contact(ws_id, host, "email", email.strip())
        else:
            if urlsplit(form_url).scheme != "https":
                raise ValueError("form_url must be an https URL")
            self.repo.put_takedown_contact(ws_id, host, "form", form_url.strip())
