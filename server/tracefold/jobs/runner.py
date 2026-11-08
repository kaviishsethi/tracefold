"""Single supervised scan runner. SQLite holds job state; one runner owns execution at a time."""
from __future__ import annotations

import logging
import os
import socket
import threading
import time
from typing import TYPE_CHECKING

from ..util import new_id

if TYPE_CHECKING:
    from ..engine import Engine

log = logging.getLogger("tracefold.runner")


def _owner_alive(owner: str) -> bool:
    try:
        host, pid, _ = owner.split(":", 2)
        if host != socket.gethostname():
            return True  # cannot check; assume alive
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except (ValueError, PermissionError):
        return True


class RunnerConflict(RuntimeError):
    pass


class Runner:
    def __init__(self, engine: "Engine"):
        self.e = engine
        self.owner = f"{socket.gethostname()}:{os.getpid()}:{new_id('runner')}"
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._exec_lock = threading.Lock()
        self.acquired = False

    def acquire(self) -> None:
        if self.e.repo.acquire_runner(self.owner):
            self.acquired = True
            return
        # Take over a lock left by a dead process on this host; otherwise refuse (no leasing yet).
        from ..storage.repo import Repo  # noqa: F401
        row = self.e.repo.db.conn().execute("SELECT owner FROM runner_lock WHERE id=1").fetchone()
        if row and not _owner_alive(row[0]):
            self.e.repo.force_release_runner()
            if self.e.repo.acquire_runner(self.owner):
                self.acquired = True
                return
        raise RunnerConflict("Another scan runner owns this database; multi-runner execution is not supported.")

    def start(self) -> None:
        if not self.acquired:
            self.acquire()
        self._thread = threading.Thread(target=self._loop, name="tracefold-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)
        if self.acquired:
            self.e.repo.release_runner(self.owner)
            self.acquired = False

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        last_schedule_check = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_schedule_check >= 5:  # scheduled checks: start any that are due
                    last_schedule_check = time.monotonic()
                    self.e.schedules.run_due()
                self.run_pending()
            except Exception:  # pragma: no cover - defensive; never crash the loop
                log.exception("runner loop error")
            self._wake.wait(self.e.settings.runner_poll_seconds)
            self._wake.clear()

    def run_pending(self, limit: int | None = None) -> int:
        """Run queued scans one at a time. Returns the number executed."""
        if not self.acquired:
            self.acquire()
        n = 0
        with self._exec_lock:
            while limit is None or n < limit:
                scan = self.e.repo.claim_next_scan()
                if scan is None:
                    break
                self.execute(scan)
                n += 1
        return n

    def execute(self, scan: dict) -> None:
        from .pipeline import run_scan
        try:
            run_scan(self.e, scan)
        finally:
            self.e.registry.unpin(scan["input_id"], consumed=True)
            try:
                self.e.maintenance()
            except Exception:  # retention must never fail a scan
                log.exception("maintenance failed")
