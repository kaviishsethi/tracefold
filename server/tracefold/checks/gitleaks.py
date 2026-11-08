"""Gitleaks as an additional, sandboxed source of secret leads.

Privacy contract (see docs/GITLEAKS.md):

- Private text reaches Gitleaks only through stdin. No temporary copy of a document is written.
- Gitleaks runs with an empty environment (no provider keys from ``server/.env``), an empty temporary working
  directory (so no ``.gitleaks.toml`` / ``.gitleaksignore`` from the scanned material is honoured) and its built-in,
  version-pinned rule set.
- On macOS it runs under ``sandbox-exec`` with network access and file writes denied, and reads of the home
  directory and Tracefold data directory denied. On Linux it runs in a new network namespace via ``unshare``.
  Without a working sandbox it does not run unless ``gitleaks_allow_unsandboxed`` is set explicitly.
- Gitleaks never verifies credentials and makes no network calls; the sandbox enforces that rather than
  relying on it.
- Gitleaks stdout (which contains the matched secret) is parsed in memory only. Its stderr is discarded and
  never logged. Secret values are attached to ``Hit.secret_values``, which is never persisted and drives
  masking/scrubbing of everything that is.
- Gitleaks' reported columns are byte-based and inconsistent across lines, so they are not trusted: each
  secret is located again inside Tracefold's own in-memory text, within the reported line range.

A Gitleaks hit is a format-based lead, exactly like ``secret_literal``; it is not proof a credential is real.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

RULE_ID = "gitleaks_secret"
ADAPTER_VERSION = "1"

# Where Homebrew and common package managers install the binary; PATH is consulted first.
_KNOWN_PATHS = ("/opt/homebrew/bin/gitleaks", "/usr/local/bin/gitleaks", "/usr/bin/gitleaks")


@dataclass
class RawLeak:
    rule: str
    secret: str
    start_line: int
    end_line: int
    entropy: float | None = None

    def __repr__(self) -> str:  # never let a secret reach a log line or traceback via repr()
        return f"RawLeak(rule={self.rule!r}, lines={self.start_line}-{self.end_line}, secret=<{len(self.secret)} chars>)"


@dataclass
class ScanResult:
    status: str                    # ok | off | unavailable | failed
    reason: str | None = None
    leaks: list[RawLeak] = field(default_factory=list)


@dataclass
class Probe:
    available: bool
    reason: str | None = None
    path: str | None = None
    version: str | None = None
    sha256: str | None = None
    sandbox: str | None = None     # sandbox-exec | unshare | none


def _sandbox_profile(deny_read: list[str]) -> str:
    rules = ["(version 1)", "(allow default)", "(deny network*)",
             '(deny file-write* (require-not (literal "/dev/null")))']
    for p in deny_read:
        rules.append(f'(deny file-read* (subpath "{_sb_escape(p)}"))')
    return "".join(rules)


def _sb_escape(p: str) -> str:
    return p.replace("\\", "\\\\").replace('"', '\\"')


class GitleaksScanner:
    def __init__(self, settings):
        self.settings = settings
        self._probe: Probe | None = None
        self._lock = threading.Lock()

    # ---------- configuration ----------
    @property
    def mode(self) -> str:
        m = (self.settings.gitleaks or "auto").lower()
        return m if m in ("auto", "off", "required") else "auto"

    def _find_binary(self) -> str | None:
        explicit = self.settings.gitleaks_path
        if explicit:
            return explicit if os.path.isfile(explicit) and os.access(explicit, os.X_OK) else None
        found = shutil.which("gitleaks")
        if found:
            return found
        return next((p for p in _KNOWN_PATHS if os.path.isfile(p) and os.access(p, os.X_OK)), None)

    def _deny_read_paths(self) -> list[str]:
        paths = {str(Path.home()), str(self.settings.data_dir)}
        try:
            paths.add(str(Path(__file__).resolve().parents[2]))   # server/ (holds .env with provider keys)
        except IndexError:
            pass
        return sorted(os.path.realpath(p) for p in paths)

    def _wrap(self, argv: list[str], sandbox: str) -> list[str]:
        if sandbox == "sandbox-exec":
            return ["/usr/bin/sandbox-exec", "-p", _sandbox_profile(self._deny_read_paths()), *argv]
        if sandbox == "unshare":
            return ["unshare", "--user", "--map-root-user", "--net", "--", *argv]
        return argv

    def _run(self, argv: list[str], sandbox: str, stdin: bytes, timeout: float) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="tracefold-gl-") as cwd:
            env = {"PATH": "/usr/bin:/bin"}
            return subprocess.run(self._wrap(argv, sandbox), input=stdin, capture_output=True, cwd=cwd, env=env,
                                  timeout=timeout, check=False)

    def _pick_sandbox(self, binary: str) -> str | None:
        if sys.platform == "darwin" and os.path.exists("/usr/bin/sandbox-exec"):
            candidates = ["sandbox-exec"]
        elif sys.platform.startswith("linux") and shutil.which("unshare"):
            candidates = ["unshare"]
        else:
            candidates = []
        for sb in candidates:
            try:
                r = self._run([binary, "version"], sb, b"", 15)
                if r.returncode == 0:
                    return sb
            except (OSError, subprocess.SubprocessError):
                continue
        return None

    def probe(self) -> Probe:
        with self._lock:
            if self._probe is None:
                self._probe = self._do_probe()
            return self._probe

    def _do_probe(self) -> Probe:
        if self.mode == "off":
            return Probe(False, "disabled")
        binary = self._find_binary()
        if not binary:
            return Probe(False, "gitleaks_not_installed")
        try:
            digest = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        except OSError:
            return Probe(False, "gitleaks_unreadable", path=binary)
        pin = (self.settings.gitleaks_sha256 or "").lower().strip()
        if pin and pin != digest:
            return Probe(False, "gitleaks_checksum_mismatch", path=binary, sha256=digest)
        sandbox = self._pick_sandbox(binary)
        if sandbox is None:
            if not self.settings.gitleaks_allow_unsandboxed:
                return Probe(False, "no_network_sandbox", path=binary, sha256=digest)
            sandbox = "none"
        try:
            r = self._run([binary, "version"], sandbox, b"", 15)
        except (OSError, subprocess.SubprocessError):
            return Probe(False, "gitleaks_failed_to_start", path=binary, sha256=digest, sandbox=sandbox)
        version = r.stdout.decode("utf-8", "replace").strip().splitlines()[0:1]
        if r.returncode != 0 or not version:
            return Probe(False, "gitleaks_failed_to_start", path=binary, sha256=digest, sandbox=sandbox)
        return Probe(True, None, path=binary, version=version[0][:40], sha256=digest, sandbox=sandbox)

    def status(self) -> dict:
        p = self.probe()
        return {"mode": self.mode, "available": p.available, "reason": p.reason, "version": p.version,
                "sha256": p.sha256, "sandbox": p.sandbox}

    def check_version(self) -> str:
        p = self.probe()
        return f"gitleaks-{p.version}+adapter{ADAPTER_VERSION}" if p.available else "gitleaks-unavailable"

    # ---------- scanning ----------
    def scan_text(self, text: str) -> ScanResult:
        if self.mode == "off":
            return ScanResult("off", "disabled")
        p = self.probe()
        if not p.available:
            return ScanResult("unavailable", p.reason)
        timeout = float(self.settings.gitleaks_timeout_seconds)
        argv = [p.path, "stdin", "--no-banner", "--no-color", "--log-level", "error", "--report-format", "json",
                "--report-path", "-", "--exit-code", "0", "--timeout", str(max(1, int(timeout)))]
        try:
            r = self._run(argv, p.sandbox or "none", text.encode("utf-8"), timeout + 5)
        except subprocess.TimeoutExpired:
            return ScanResult("failed", "gitleaks_timeout")
        except (OSError, subprocess.SubprocessError):
            return ScanResult("failed", "gitleaks_failed_to_start")
        if r.returncode != 0:
            return ScanResult("failed", f"gitleaks_exit_{r.returncode}")   # stderr deliberately not kept
        try:
            data = json.loads(r.stdout or b"[]")
        except ValueError:
            return ScanResult("failed", "gitleaks_output_unparseable")
        finally:
            del r
        if not isinstance(data, list):
            return ScanResult("failed", "gitleaks_output_unparseable")
        leaks = []
        for item in data:
            try:
                secret = item["Secret"]
                if not isinstance(secret, str) or not secret:
                    continue
                ent = item.get("Entropy")
                leaks.append(RawLeak(rule=str(item.get("RuleID", "unknown"))[:80], secret=secret,
                                     start_line=int(item["StartLine"]), end_line=int(item.get("EndLine") or item["StartLine"]),
                                     entropy=round(float(ent), 2) if isinstance(ent, (int, float)) else None))
            except (KeyError, TypeError, ValueError):
                continue
        return ScanResult("ok", None, leaks)


def locate(text: str, line_starts: list[int], leak: RawLeak, taken: set[tuple[int, int]]) -> tuple[int, int] | None:
    """Find the leak's secret within its reported lines in our own text; widen to ±1 line, then give up."""
    n = len(line_starts)

    def span(first: int, last: int) -> tuple[int, int]:
        first, last = max(1, first), min(n, last)
        s = line_starts[first - 1]
        e = line_starts[last] if last < n else len(text)
        return s, e

    for pad in (0, 1):
        s, e = span(leak.start_line - pad, leak.end_line + pad)
        i = text.find(leak.secret, s, e)
        while i >= 0 and i + len(leak.secret) <= e:
            sp = (i, i + len(leak.secret))
            if sp not in taken:
                return sp
            i = text.find(leak.secret, i + 1, e)
    return None
