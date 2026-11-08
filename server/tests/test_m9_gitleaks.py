"""Gitleaks as a sandboxed secret-lead source, with Tracefold's privacy contract around it.

Offline tests use a fake ``gitleaks`` shell script so the suite stays deterministic. Tests marked ``gitleaks``
use the real binary and run only when it is installed.
"""
from __future__ import annotations

import shutil
import socket
import sys
import threading
from pathlib import Path

import pytest

from tracefold.checks.gitleaks import GitleaksScanner, RawLeak, locate
from tracefold.checks.rules import gitleaks_hits, run_rules
from tracefold.config import Settings
from tracefold.inputs.registry import CapturedFile
from tracefold.parsing.document import parse_text
from tracefold.util import sha256

from .test_m3_recheck import recheck, write

GL_ONLY = "hk_9f8e7d6c5b4a3f2e1d0c9b8a7f6e"          # not caught by the built-in rules
CONFIG = f"""import os

WEBHOOK = "{GL_ONLY}"
DEBUG = os.environ.get("DEBUG")
"""
REAL_BINARY = shutil.which("gitleaks") or next(
    (p for p in ("/opt/homebrew/bin/gitleaks", "/usr/local/bin/gitleaks") if Path(p).exists()), None)


def fake_gitleaks(tmp_path: Path, leaks_json: str, exit_code: int = 0, name: str = "gitleaks") -> str:
    """A stand-in binary. It reports EXA_API_KEY as a leak if it ever sees it, to prove the env is stripped."""
    p = tmp_path / "bin" / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(f"""#!/bin/sh
if [ "$1" = "version" ]; then echo "8.0.0-fake"; exit 0; fi
cat > /dev/null
if [ -n "$EXA_API_KEY" ]; then
  echo '[{{"RuleID":"env-leak","Secret":"'"$EXA_API_KEY"'","StartLine":1,"EndLine":1}}]'; exit 0
fi
echo '{leaks_json}'
exit {exit_code}
""")
    p.chmod(0o755)
    return str(p)


LEAK_JSON = (f'[{{"RuleID":"generic-api-key","Secret":"{GL_ONLY}","StartLine":3,"EndLine":3,"StartColumn":99,'
             f'"EndColumn":1,"Entropy":4.2}},'
             f'{{"RuleID":"ghost","Secret":"value-that-is-not-in-the-file","StartLine":1,"EndLine":1}}]')


def doc(text: str, name="config.py", kind="code", lang="python"):
    data = text.encode()
    return parse_text(CapturedFile("file_x", name, "captured", data=data, sha256=sha256(data), kind=kind, language=lang))


# ---------------- unit: locating leads in our own text ----------------
def test_locate_ignores_reported_columns_and_skips_taken_spans():
    d = doc('a = "tok123456789"\nb = "tok123456789"\n')
    leak = RawLeak("r", "tok123456789", 1, 1)
    taken: set = set()
    first = locate(d.text, d.line_starts, leak, taken)
    assert d.text[first[0]:first[1]] == "tok123456789" and d.line_of(first[0]) == 1
    taken.add(first)
    # Same line, already taken: widen by one line rather than double-claim.
    second = locate(d.text, d.line_starts, leak, taken)
    assert second != first and d.line_of(second[0]) == 2
    assert locate(d.text, d.line_starts, RawLeak("r", "absent-value", 1, 1), set()) is None


def test_repr_never_contains_secret():
    assert GL_ONLY not in repr(RawLeak("r", GL_ONLY, 1, 1))


def test_overlap_merges_into_builtin_and_widens_masking():
    body = "\n".join(["MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun"] * 3)
    key = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----"
    d = doc(f"x = 1\n{key}\n", name="k.txt", kind="text", lang=None)
    hits, _ = run_rules(d)
    builtin = [h for h in hits if h.rule_id == "secret_literal"]
    assert len(builtin) == 1 and builtin[0].secret_values == ["-----BEGIN RSA PRIVATE KEY-----"]
    extra, unlocated = gitleaks_hits(d, [RawLeak("private-key", key, 2, 6)], hits)
    assert extra == [] and unlocated == 0                       # no duplicate finding
    assert key in builtin[0].secret_values                      # the whole key body is now masked/scrubbed
    assert builtin[0].meta["gitleaks_rules"] == ["private-key"]


def test_placeholder_values_are_dropped():
    d = doc('k = "sk_example_value_123456"\n')
    extra, _ = gitleaks_hits(d, [RawLeak("generic", "sk_example_value_123456", 1, 1)], [])
    assert extra == []


# ---------------- scanner configuration ----------------
def _settings(tmp_path, **kw) -> Settings:
    s = Settings(data_dir=tmp_path / "data")
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_off_mode_never_probes(tmp_path):
    sc = GitleaksScanner(_settings(tmp_path, gitleaks="off", gitleaks_path="/nonexistent"))
    assert sc.scan_text("x").status == "off" and sc.status()["reason"] == "disabled"


def test_checksum_pin_mismatch_refuses_to_run(tmp_path):
    path = fake_gitleaks(tmp_path, "[]")
    sc = GitleaksScanner(_settings(tmp_path, gitleaks_path=path, gitleaks_sha256="0" * 64))
    r = sc.scan_text("x")
    assert (r.status, r.reason) == ("unavailable", "gitleaks_checksum_mismatch")


def test_missing_binary_is_reported_not_silent(tmp_path):
    sc = GitleaksScanner(_settings(tmp_path, gitleaks_path=str(tmp_path / "nope")))
    assert sc.scan_text("x").reason == "gitleaks_not_installed"


def test_environment_is_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-provider-key-should-not-pass")
    sc = GitleaksScanner(_settings(tmp_path, gitleaks_path=fake_gitleaks(tmp_path, "[]"),
                                   gitleaks_allow_unsandboxed=True))
    r = sc.scan_text("anything")
    assert r.status == "ok" and r.leaks == []


def test_nonzero_exit_is_failure_without_output(tmp_path):
    sc = GitleaksScanner(_settings(tmp_path, gitleaks_path=fake_gitleaks(tmp_path, LEAK_JSON, exit_code=3),
                                   gitleaks_allow_unsandboxed=True))
    r = sc.scan_text(CONFIG)
    assert (r.status, r.reason, r.leaks) == ("failed", "gitleaks_exit_3", [])


# ---------------- engine integration ----------------
def test_gitleaks_lead_becomes_finding_and_secret_is_never_persisted(make_env, tmp_path):
    env = make_env(gitleaks="auto", gitleaks_path=fake_gitleaks(tmp_path, LEAK_JSON), gitleaks_allow_unsandboxed=True)
    write(env, "config.py", CONFIG)
    s = env.scan(env.capture(["config.py"])["input_id"], model_review=False)
    assert s["state"] == "completed", s
    fs = env.findings(s["scan_id"])
    gl = [f for f in fs if f["rule_id"] == "gitleaks_secret"]
    assert len(gl) == 1
    assert gl[0]["latest"]["evidence"][0]["location"]["line_start"] == 3
    assert gl[0]["latest"]["check_version"].endswith("+gitleaks-8.0.0-fake+adapter1")
    # The unlocatable "ghost" lead is surfaced as partial rule coverage, not dropped silently.
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("rule", "gitleaks_secret")]["reason"] == "gitleaks_lead_not_located"
    assert s["versions"]["secret_scanner"] == "gitleaks-8.0.0-fake+adapter1"
    # Neither the secret nor the ghost value appears anywhere Tracefold stores data.
    for f in Path(env.engine.settings.data_dir).rglob("*"):
        if f.is_file():
            blob = f.read_bytes()
            assert GL_ONLY.encode() not in blob and b"value-that-is-not-in-the-file" not in blob, f
    for x in fs:
        assert GL_ONLY not in str(x)


def test_required_mode_without_binary_marks_check_partial(make_env, tmp_path):
    env = make_env(gitleaks="required", gitleaks_path=str(tmp_path / "missing"))
    write(env, "config.py", CONFIG)
    s = env.scan(env.capture(["config.py"])["input_id"], model_review=False)
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("check", "local_risk")]["status"] == "partial"
    assert cov[("check", "local_risk")]["reason"] == "secret_scanner_incomplete"
    assert cov[("rule", "gitleaks_secret")]["reason"] == "gitleaks_not_installed"


def test_auto_mode_without_binary_keeps_builtin_rules_complete(make_env, tmp_path):
    env = make_env(gitleaks="auto", gitleaks_path=str(tmp_path / "missing"))
    write(env, "config.py", CONFIG)
    s = env.scan(env.capture(["config.py"])["input_id"], model_review=False)
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("check", "local_risk")]["status"] == "complete"
    # optional scanner not installed: shown, but not as an incomplete check
    assert cov[("rule", "gitleaks_secret")]["status"] == "not_requested"
    assert cov[("rule", "gitleaks_secret")]["reason"] == "gitleaks_not_installed"


def test_fix_and_recheck_gitleaks_finding(make_env, tmp_path):
    env = make_env(gitleaks="auto", gitleaks_path=fake_gitleaks(tmp_path, LEAK_JSON.split(",{")[0] + "]"),
                   gitleaks_allow_unsandboxed=True)
    write(env, "config.py", CONFIG)
    s = env.scan(env.capture(["config.py"])["input_id"], model_review=False)
    f = next(x for x in env.findings(s["scan_id"]) if x["rule_id"] == "gitleaks_secret")
    # Fix: value moved to the environment. Swap the fake so it reports nothing for the fixed file.
    env.engine.settings.gitleaks_path = fake_gitleaks(tmp_path, "[]", name="gitleaks-clean")
    env.engine.secret_scanner._probe = None
    env.engine.settings.gitleaks_sha256 = None
    write(env, "config.py", CONFIG.replace(f'"{GL_ONLY}"', 'os.environ["WEBHOOK"]'))
    # Same reported version, so the recheck is equivalent and may clear the finding.
    detail, rc, _ = recheck(env, f["finding_id"], env.capture(["config.py"])["input_id"])
    assert rc["outcome"] == "not_detected_in_checked_version", rc


def test_recheck_without_gitleaks_is_inconclusive(make_env, tmp_path):
    env = make_env(gitleaks="auto", gitleaks_path=fake_gitleaks(tmp_path, LEAK_JSON.split(",{")[0] + "]"),
                   gitleaks_allow_unsandboxed=True)
    write(env, "config.py", CONFIG)
    s = env.scan(env.capture(["config.py"])["input_id"], model_review=False)
    f = next(x for x in env.findings(s["scan_id"]) if x["rule_id"] == "gitleaks_secret")
    env.engine.settings.gitleaks_path = str(tmp_path / "gone")
    env.engine.secret_scanner._probe = None
    detail, rc, _ = recheck(env, f["finding_id"], env.capture(["config.py"])["input_id"])
    assert rc["outcome"] == "inconclusive" and detail["status"] == "open"


# ---------------- real binary, real sandbox ----------------
needs_real = pytest.mark.skipif(REAL_BINARY is None, reason="gitleaks not installed")


@needs_real
def test_real_gitleaks_runs_sandboxed_and_finds_aws_key(make_env):
    env = make_env(gitleaks="required")
    status = env.engine.secret_scanner.status()
    assert status["available"], status
    assert status["sandbox"] in ("sandbox-exec", "unshare")
    write(env, "settings.py", 'REGION = "us-east-1"\nAWS_ID = "AKIAQ3EGRLPJ7NV2KX4M"\n')
    s = env.scan(env.capture(["settings.py"])["input_id"], model_review=False)
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("check", "local_risk")]["status"] == "complete", s["coverage"]
    secret_findings = [f for f in env.findings(s["scan_id"]) if f["rule_id"] in ("secret_literal", "gitleaks_secret")]
    assert len(secret_findings) == 1                      # built-in and Gitleaks agree: merged, not duplicated
    assert "AKIAQ3EGRLPJ7NV2KX4M" not in str(secret_findings)


@needs_real
@pytest.mark.skipif(sys.platform != "darwin", reason="sandbox-exec profile check is macOS-specific")
def test_sandbox_blocks_loopback_network_and_writes(tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    accepted = []
    srv.settimeout(3)
    t = threading.Thread(target=lambda: accepted.append(_accept(srv)))
    t.start()
    sc = GitleaksScanner(_settings(tmp_path))
    r = sc._run(["/usr/bin/nc", "-z", "-w", "2", "127.0.0.1", str(port)], "sandbox-exec", b"", 10)
    t.join()
    srv.close()
    assert r.returncode != 0 and accepted == [False]
    target = tmp_path / "written"
    r = sc._run(["/usr/bin/touch", str(target)], "sandbox-exec", b"", 10)
    assert r.returncode != 0 and not target.exists()
    r = sc._run(["/bin/cat", str(Path.home() / ".zshrc")], "sandbox-exec", b"", 10)
    assert r.returncode != 0 or r.stdout == b""


def _accept(srv) -> bool:
    try:
        c, _ = srv.accept()
        c.close()
        return True
    except OSError:
        return False
