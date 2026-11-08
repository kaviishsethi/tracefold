"""Optional scheduled checks: re-run a scan every hour, day or week, like a scheduled task.

Off until someone adds one. Two sources:
- ``files``: the files from an earlier upload. Uploads normally live only in memory, so adding a schedule keeps a
  private copy of just those files in the engine's data folder (owner-only permissions, never sent anywhere).
  Deleting the schedule deletes the copy.
- ``folder``: the registered workspace folder's uncommitted changes, read from disk each run.

Each run is an ordinary scan started as the client that created the schedule, so the usual capabilities, page
memory, findings and approvals all apply. A run never approves anything.
"""
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from ..contracts.enums import Capability, Check, Disclosure, ScanState
from ..contracts.models import CaptureRequest, ScanRequest
from ..errors import ApiError, not_found
from ..policy.auth import Grant, Principal
from ..util import iso, new_id, now

if TYPE_CHECKING:
    from ..engine import Engine

log = logging.getLogger("tracefold.schedules")
EVERY = {"hour": timedelta(hours=1), "day": timedelta(days=1), "week": timedelta(weeks=1)}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


class ScheduleService:
    def __init__(self, engine: "Engine"):
        self.e = engine

    @property
    def files_dir(self) -> Path:
        return self.e.settings.data_dir / "schedule_files"

    # ---------------- API ----------------
    def list(self, p: Principal, ws_id: str) -> list[dict]:
        p.require(ws_id, Capability.read)
        return [self.out(m) for m in self.e.repo.list_monitors(ws_id)]

    def create(self, p: Principal, ws_id: str, *, scan_id: str | None, every: str, public: bool, name: str | None) -> dict:
        p.require(ws_id, Capability.configure)
        p.require(ws_id, Capability.submit)
        ws = self.e.repo.get_workspace(ws_id)
        if ws is None:
            raise not_found()
        if every not in EVERY:
            raise ApiError(422, "invalid_schedule", "Choose hour, day or week.")
        mid = new_id("sched")
        files: list[str] = []
        if scan_id:
            scan = self.e.repo.get_scan(scan_id)
            if scan is None or scan["workspace_id"] != ws_id:
                raise not_found()
            cap = self.e.registry.get(scan["input_id"])
            kept = [f for f in (cap.files if cap else []) if f.status == "captured" and f.data is not None]
            if not kept:
                raise ApiError(409, "files_not_in_memory",
                               "Uploaded files aren't kept after the engine restarts. Scan the files again, then schedule it.")
            folder = self.files_dir / mid
            folder.mkdir(parents=True, exist_ok=True)
            os.chmod(folder, 0o700)
            for i, f in enumerate(kept):
                path = folder / f"{i:03d}"
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(f.data)
                files.append(f.path)
            source, label = "files", name or (files[0] if len(files) == 1 else f"{files[0]} and {len(files) - 1} more")
        else:
            if ws["source_type"] != "local_dir" or not ws["root"]:
                raise ApiError(422, "not_a_registered_directory", "This workspace has no folder; schedule an uploaded scan instead.")
            source, label = "folder", name or "Workspace changes"
        t = now()
        self.e.repo.insert_monitor({
            "id": mid, "workspace_id": ws_id, "client_id": p.client_id, "name": label[:120], "source": source,
            "source_scan_id": scan_id, "file_names": files, "every": every, "public": int(public), "enabled": 1,
            "created_at": iso(t), "next_run_at": iso(t + EVERY[every]), "runs": 0,
        })
        return self.out(self.e.repo.get_monitor(mid))

    def update(self, p: Principal, ws_id: str, mid: str, *, enabled: bool | None = None, every: str | None = None,
               run_now: bool = False) -> dict:
        p.require(ws_id, Capability.configure)
        m = self._get(ws_id, mid)
        fields: dict = {}
        if every is not None:
            if every not in EVERY:
                raise ApiError(422, "invalid_schedule", "Choose hour, day or week.")
            fields["every"] = every
            fields["next_run_at"] = iso(now() + EVERY[every])
        if enabled is not None:
            fields["enabled"] = int(enabled)
        if run_now:
            fields["next_run_at"] = iso(now())
        if fields:
            self.e.repo.update_monitor(m["id"], **fields)
        if run_now:
            self.run_due()
        return self.out(self.e.repo.get_monitor(m["id"]))

    def delete(self, p: Principal, ws_id: str, mid: str) -> None:
        p.require(ws_id, Capability.configure)
        m = self._get(ws_id, mid)
        self.e.repo.delete_monitor(m["id"])
        shutil.rmtree(self.files_dir / m["id"], ignore_errors=True)

    def out(self, m: dict) -> dict:
        return {"schedule_id": m["id"], "name": m["name"], "source": m["source"], "files": m["file_names"],
                "every": m["every"], "public": bool(m["public"]), "enabled": bool(m["enabled"]),
                "created_at": m["created_at"], "next_run_at": m["next_run_at"], "last_run_at": m["last_run_at"],
                "last_scan_id": m["last_scan_id"], "last_error": m["last_error"], "runs": m["runs"]}

    def _get(self, ws_id: str, mid: str) -> dict:
        m = self.e.repo.get_monitor(mid)
        if m is None or m["workspace_id"] != ws_id:
            raise not_found()
        return m

    # ---------------- runner ----------------
    def _principal(self, client_id: str) -> Principal | None:
        client = self.e.repo.get_client(client_id)
        if client is None or client.get("revoked_at"):
            return None
        p = Principal(client_id=client["id"], name=client["name"])
        for g in self.e.repo.grants_for(client["id"]):
            p.grants[g["workspace_id"]] = Grant(workspace_id=g["workspace_id"],
                                                capabilities=frozenset(Capability(c) for c in g["capabilities"]),
                                                disclosure=Disclosure(g["disclosure"]))
        return p

    def run_due(self) -> int:
        """Start a scan for every schedule that is due. Called from the runner loop; cheap when nothing is due."""
        started = 0
        for m in self.e.repo.due_monitors(iso(now())):
            # Don't stack runs: skip while the previous scheduled scan is still queued or running.
            last = self.e.repo.get_scan(m["last_scan_id"]) if m["last_scan_id"] else None
            if last and last["state"] in (ScanState.queued.value, ScanState.running.value):
                continue
            nxt = iso(now() + EVERY.get(m["every"], EVERY["day"]))
            try:
                scan_id = self._run(m)
            except ApiError as ex:
                self.e.repo.update_monitor(m["id"], next_run_at=nxt, last_run_at=iso(now()), last_error=ex.message)
                continue
            except Exception as ex:  # never let one schedule break the runner
                log.warning("schedule %s failed: %s", m["id"], type(ex).__name__)
                self.e.repo.update_monitor(m["id"], next_run_at=nxt, last_run_at=iso(now()), last_error="Couldn't start the scan.")
                continue
            self.e.repo.update_monitor(m["id"], next_run_at=nxt, last_run_at=iso(now()), last_scan_id=scan_id,
                                       last_error=None, runs=m["runs"] + 1)
            started += 1
        return started

    def _run(self, m: dict) -> str:
        p = self._principal(m["client_id"])
        if p is None:
            raise ApiError(403, "schedule_client_revoked", "The client that created this schedule no longer has access.")
        ws_id = m["workspace_id"]
        if m["source"] == "files":
            folder = self.files_dir / m["id"]
            files = []
            for i, name in enumerate(m["file_names"]):
                path = folder / f"{i:03d}"
                if path.is_file():
                    files.append(self.e.inputs.make_file(name, path.read_bytes()))
            if not files:
                raise ApiError(409, "schedule_files_missing", "The saved copy of these files is missing. Delete this schedule and add it again.")
            cap = self.e.inputs.finalize(p, ws_id, "upload", files)
            input_id = cap.input_id
        else:
            input_id = self.e.inputs.capture(p, ws_id, CaptureRequest(mode="changes", include_untracked=True)).input_id
        checks = [Check.local_risk] + ([Check.public_match] if m["public"] else [])
        acc = self.e.scans.submit(p, ws_id, ScanRequest(input_id=input_id, checks=checks,
                                                        automatic_discovery=bool(m["public"])), None)
        return acc.scan_id
