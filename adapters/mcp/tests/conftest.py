"""Start a real engine (`tracefold serve`) provisioned by its CLI, with a Git workspace, for adapter tests."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

SERVER = Path(__file__).resolve().parents[3] / "server"
FIXTURES = SERVER / "fixtures"

RISKY = '''import logging

logger = logging.getLogger(__name__)


def charge(card_number: str, amount: int) -> None:
    logger.info("charging card %s for %d", card_number, amount)
'''
FIXED = RISKY.replace('logger.info("charging card %s for %d", card_number, amount)',
                      'logger.info("charging card ending %s for %d", mask(card_number), amount)')


@dataclass
class Engine:
    base: str
    root: Path
    tokens: dict[str, str]
    data: Path
    env: dict[str, str]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=root,
                   check=True, capture_output=True)


@pytest.fixture(scope="session")
def engine(tmp_path_factory) -> Engine:
    tmp = tmp_path_factory.mktemp("engine")
    data, root = tmp / "data", tmp / "ws"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "README.md").write_text("demo workspace\n")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "init")
    env = {**os.environ, "TRACEFOLD_DATA": str(data), "TRACEFOLD_FIXTURES": str(FIXTURES),
           "TRACEFOLD_OLLAMA_URL": "http://127.0.0.1:9"}  # no model: rule findings stay, review 'unavailable'
    cli = [sys.executable, "-m", "tracefold.cli"]

    def run(*a: str) -> str:
        return subprocess.run([*cli, *a], env=env, capture_output=True, text=True, check=True, cwd=SERVER).stdout.strip()

    run("init")
    run("add-workspace", "ws_demo", "--name", "Demo", "--root", str(root))
    run("add-workspace", "ws_other", "--name", "Other")
    tokens = {
        "mcp": run("add-client", "mcp-adapter", "--workspace", "ws_demo", "--caps", "submit,read,read_evidence,recheck,cancel"),
        "cloud": run("add-client", "cloud-host", "--workspace", "ws_demo", "--caps", "submit,read,recheck",
                     "--disclosure", "minimal"),
        "app": run("add-client", "upload-app", "--workspace", "ws_demo"),
    }
    manifest = tmp / "m.json"
    manifest.write_text(json.dumps([{"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture",
                                     "fixture_path": "public/forum_post.html"}]))
    run("add-manifest", "ws_demo", "sources_demo", str(manifest))

    port = _free_port()
    proc = subprocess.Popen([*cli, "serve", "--port", str(port)], env=env, cwd=SERVER,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            if httpx.get(base + "/v1/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        proc.terminate()
        raise RuntimeError("engine did not start")
    try:
        yield Engine(base, root, tokens, data, env)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
