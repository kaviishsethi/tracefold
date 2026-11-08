from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tracefold.api.app import create_app
from tracefold.config import Settings
from tracefold.contracts.enums import Capability
from tracefold.engine import Engine

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

if os.environ.get("TRACEFOLD_LIVE") == "1":  # opt-in live tests may use local provider keys from server/.env
    from tracefold.envfile import load_env_file
    load_env_file(Path(__file__).resolve().parent.parent / ".env")
ALL = [c.value for c in Capability]


def fx(name: str) -> bytes:
    return (FIXTURES / "private" / name).read_bytes()


PUBLIC = {"manifest_id": "sources_main", "mode": "refresh"}


class Env:
    def __init__(self, engine: Engine, client: TestClient, tokens: dict[str, str], root: Path):
        self.engine, self.client, self.tokens, self.root = engine, client, tokens, root

    def h(self, who: str = "app", **extra) -> dict:
        return {"Authorization": f"Bearer {self.tokens[who]}", **extra}

    def upload(self, files: dict[str, bytes], who="app", ws="ws_a"):
        r = self.client.post(f"/v1/workspaces/{ws}/uploads", headers=self.h(who),
                             files=[("file", (n, d, "application/octet-stream")) for n, d in files.items()])
        assert r.status_code == 201, r.text
        return r.json()

    def capture(self, paths, who="app", ws="ws_a"):
        r = self.client.post(f"/v1/workspaces/{ws}/captures", headers=self.h(who), json={"mode": "files", "paths": paths})
        assert r.status_code == 201, r.text
        return r.json()

    def scan(self, input_id, checks=("local_risk",), who="app", ws="ws_a", run=True, **kw):
        body = {"input_id": input_id, "checks": list(checks), **kw}
        r = self.client.post(f"/v1/workspaces/{ws}/scans", headers=self.h(who), json=body)
        assert r.status_code == 202, r.text
        sid = r.json()["scan_id"]
        if run:
            self.engine.runner.run_pending()
        return self.get_scan(sid, who, ws)

    def get_scan(self, sid, who="app", ws="ws_a"):
        r = self.client.get(f"/v1/workspaces/{ws}/scans/{sid}", headers=self.h(who))
        assert r.status_code == 200, r.text
        return r.json()

    def findings(self, scan_id=None, who="app", ws="ws_a"):
        q = f"?scan_id={scan_id}" if scan_id else ""
        r = self.client.get(f"/v1/workspaces/{ws}/findings{q}", headers=self.h(who))
        assert r.status_code == 200, r.text
        return r.json()["items"]

    def wait(self, sid, who="app", ws="ws_a", timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            s = self.get_scan(sid, who, ws)
            if s["state"] not in ("queued", "running"):
                return s
            time.sleep(0.05)
        raise AssertionError("scan did not finish")


def make_settings(tmp_path: Path, **kw) -> Settings:
    s = Settings(data_dir=tmp_path / "data")
    s.allowed_hosts = (*s.allowed_hosts, "testserver")
    s.start_runner = False
    s.retrieval_in_process = True
    s.ollama_url = "http://127.0.0.1:9"  # nothing listens: model unavailable unless a test sets a fake
    s.fixture_root = FIXTURES
    s.gitleaks = "off"  # deterministic by default; Gitleaks tests opt in
    for k, v in kw.items():
        setattr(s, k, v)
    return s


@pytest.fixture
def make_env(tmp_path):
    made = []

    def _make(**kw) -> Env:
        root = tmp_path / "workspace"
        root.mkdir(exist_ok=True)
        if made and "data_dir" not in kw:
            kw["data_dir"] = tmp_path / f"data{len(made)}"
        eng = Engine(make_settings(tmp_path, **kw))
        if eng.repo.get_workspace("ws_a") is None:
            eng.add_workspace("ws_a", "Test workspace", str(root))
            eng.add_workspace("ws_b", "Other workspace", None)
            eng.add_manifest("ws_a", "sources_main", [
                {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture",
                 "fixture_path": "public/forum_post.html"},
                {"source_id": "vendor_blog", "url": "https://vendor.example/blog/streaming", "provider": "fixture",
                 "fixture_path": "public/vendor_blog.html"},
            ])
            eng.add_manifest("ws_a", "sources_with_failure", [
                {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture",
                 "fixture_path": "public/forum_post.html"},
                {"source_id": "gone", "url": "https://gone.example/x", "provider": "fixture",
                 "fixture_path": "public/does_not_exist.html"},
            ])
        tokens = {
            "app": eng.add_client(f"app{len(made)}", {"ws_a": (ALL, "full")}),
            "mcp": eng.add_client(f"mcp{len(made)}", {"ws_a": (ALL, "full")}),
            "cloud": eng.add_client(f"cloud{len(made)}", {"ws_a": (["read", "submit", "read_evidence"], "minimal")}),
            "other": eng.add_client(f"other{len(made)}", {"ws_b": (ALL, "full")}),
            "reader": eng.add_client(f"reader{len(made)}", {"ws_a": (["read"], "full")}),
        }
        client = TestClient(create_app(eng))
        client.__enter__()
        env = Env(eng, client, tokens, root)
        made.append(env)
        return env

    yield _make
    for env in made:
        try:
            env.client.__exit__(None, None, None)
        except Exception:
            pass


@pytest.fixture
def env(make_env) -> Env:
    return make_env()
