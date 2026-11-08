"""`tracefold connect-aws`: one command that lets Tracefold turn off leaked AWS keys.

Uses the AWS CLI you're already signed in to. It creates (or reuses) an IAM user that can do exactly two things,
look up which user owns a key and set a key to Inactive, then creates an access key for that user and writes it to
server/.env (readable only by you). The new key is never printed. The running engine picks it up on the next
approval; no restart needed.

This is an operator setup step on your own machine, so it calls the AWS CLI directly instead of going through the
engine gateway.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .remediation.aws import ENV_KEY_ID, ENV_SECRET

POLICY_NAME = "tracefold-disable-leaked-keys"


def policy(account: str) -> dict:
    return {"Version": "2012-10-17", "Statement": [{
        "Sid": "TracefoldTurnOffLeakedKeys", "Effect": "Allow",
        "Action": ["iam:GetAccessKeyLastUsed", "iam:UpdateAccessKey"],
        "Resource": f"arn:aws:iam::{account}:user/*",
    }]}


class ConnectError(Exception):
    pass


def _env_has_keys(path: Path) -> bool:
    if not path.is_file():
        return False
    keys = {line.split("=", 1)[0].strip() for line in path.read_text().splitlines() if "=" in line and not line.lstrip().startswith("#")}
    return ENV_KEY_ID in keys and ENV_SECRET in keys


def write_env(path: Path, values: dict[str, str]) -> None:
    """Set these keys in a .env file, keeping every other line, readable only by the owner."""
    lines = path.read_text().splitlines() if path.is_file() else []
    out, done = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip().removeprefix("# ").strip() if "=" in line else None
        if key in values:
            if key not in done:
                out.append(f"{key}={values[key]}")
                done.add(key)
            continue
        out.append(line)
    if len(done) < len(values):
        out += ["", "# AWS remediation user written by `tracefold connect-aws`"] if out else []
        out += [f"{k}={v}" for k, v in values.items() if k not in done]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write("\n".join(out) + "\n")
    os.chmod(path, 0o600)


def run(env_path: Path, profile: str | None = None, user: str = "tracefold-remediation", rotate: bool = False,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> list[str]:
    """Returns the steps taken, for printing. Raises ConnectError with a plain message on failure."""
    if runner is subprocess.run and shutil.which("aws") is None:
        raise ConnectError("The AWS CLI isn't installed. Install it (brew install awscli), run `aws configure` or "
                           "`aws sso login`, then run this again.")
    base = ["aws", *(["--profile", profile] if profile else []), "--output", "json"]

    def aws(*args: str, ok_codes: tuple[str, ...] = ()) -> dict:
        r = runner([*base, *args], capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            err = (r.stderr or "").strip()
            if any(code in err for code in ok_codes):
                return {}
            first = err.splitlines()[-1] if err else f"aws {args[0]} {args[1]} failed"
            raise ConnectError(first)
        return json.loads(r.stdout) if r.stdout.strip() else {}

    steps = []
    who = aws("sts", "get-caller-identity")
    account = who.get("Account")
    if not account:
        raise ConnectError("The AWS CLI isn't signed in. Run `aws configure` or `aws sso login` first.")
    steps.append(f"Signed in to AWS account {account}")
    aws("iam", "create-user", "--user-name", user, "--tags", "Key=created-by,Value=tracefold", ok_codes=("EntityAlreadyExists",))
    steps.append(f"IAM user {user} is ready")
    aws("iam", "put-user-policy", "--user-name", user, "--policy-name", POLICY_NAME,
        "--policy-document", json.dumps(policy(account)))
    steps.append("It can only look up and turn off access keys")
    if _env_has_keys(env_path) and not rotate:
        steps.append(f"Kept the key already in {env_path} (pass --rotate to replace it)")
        return steps
    key = aws("iam", "create-access-key", "--user-name", user).get("AccessKey") or {}
    if not key.get("AccessKeyId") or not key.get("SecretAccessKey"):
        raise ConnectError("AWS didn't return an access key.")
    write_env(env_path, {ENV_KEY_ID: key["AccessKeyId"], ENV_SECRET: key["SecretAccessKey"]})
    steps.append(f"Saved its key to {env_path} (not shown here)")
    return steps
