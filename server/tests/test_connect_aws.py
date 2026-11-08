"""`tracefold connect-aws`: least-privilege IAM user, key written to .env privately, never printed."""
import json
import stat
import subprocess

import pytest

from tracefold.connect_aws import ConnectError, run, write_env

SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def fake_aws(log, exists=False, signed_in=True):
    def runner(argv, **kw):
        log.append(argv)
        cmd = argv[argv.index("json") + 1:]
        if cmd[:2] == ["sts", "get-caller-identity"]:
            return subprocess.CompletedProcess(argv, 0 if signed_in else 255, json.dumps({"Account": "123456789012"}) if signed_in else "",
                                               "" if signed_in else "Unable to locate credentials")
        if cmd[:2] == ["iam", "create-user"] and exists:
            return subprocess.CompletedProcess(argv, 254, "", "An error occurred (EntityAlreadyExists) when calling CreateUser")
        if cmd[:2] == ["iam", "create-access-key"]:
            return subprocess.CompletedProcess(argv, 0, json.dumps({"AccessKey": {"AccessKeyId": "AKIATRACEFOLDREM0001", "SecretAccessKey": SECRET}}), "")
        return subprocess.CompletedProcess(argv, 0, "{}", "")
    return runner


def test_creates_scoped_user_and_writes_key_privately(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# keep me\nEXA_API_KEY=exa-123\n")
    log = []
    steps = run(env, runner=fake_aws(log))
    assert not any(SECRET in s for s in steps)
    pol = next(a for a in log if "put-user-policy" in a)
    doc = json.loads(pol[pol.index("--policy-document") + 1])
    assert doc["Statement"][0]["Action"] == ["iam:GetAccessKeyLastUsed", "iam:UpdateAccessKey"]
    assert doc["Statement"][0]["Resource"] == "arn:aws:iam::123456789012:user/*"
    text = env.read_text()
    assert "EXA_API_KEY=exa-123" in text and "# keep me" in text
    assert "TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID=AKIATRACEFOLDREM0001" in text and SECRET in text
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_rerun_reuses_user_and_keeps_existing_key(tmp_path):
    env = tmp_path / ".env"
    run(env, runner=fake_aws([]))
    log = []
    steps = run(env, runner=fake_aws(log, exists=True))
    assert not any("create-access-key" in a for a in log) and "Kept the key" in steps[-1]
    run(env, rotate=True, runner=fake_aws(log, exists=True))
    assert any("create-access-key" in a for a in log)
    assert env.read_text().count("TRACEFOLD_AWS_REMEDIATION_ACCESS_KEY_ID=") == 1


def test_not_signed_in_is_a_plain_error(tmp_path):
    with pytest.raises(ConnectError, match="Unable to locate credentials"):
        run(tmp_path / ".env", runner=fake_aws([], signed_in=False))


def test_write_env_replaces_commented_placeholder(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# EXA_API_KEY=\n")
    write_env(env, {"EXA_API_KEY": "exa-1"})
    assert env.read_text() == "EXA_API_KEY=exa-1\n"
