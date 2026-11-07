"""Milestone 4: DOCX parser and local Git change capture."""
from __future__ import annotations

import io
import subprocess
import zipfile
from xml.sax.saxutils import escape

import pytest

from tracefold.config import Limits
from tracefold.inputs.registry import CapturedFile
from tracefold.parsing.docx import DocxError, parse_docx
from tracefold.util import sha256

from .conftest import PUBLIC, fx

W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
       'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"'


def make_docx(paragraphs: list[str], extra: dict[str, bytes] | None = None, raw_xml: bytes | None = None) -> bytes:
    body = "".join(
        f'<w:p w14:paraId="{i:08X}"><w:r><w:t xml:space="preserve">{escape(t)}</w:t></w:r></w:p>' for i, t in enumerate(paragraphs, 1))
    xml = raw_xml or f'<?xml version="1.0" encoding="UTF-8"?><w:document {W_NS}><w:body>{body}</w:body></w:document>'.encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", xml)
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


def parse(data: bytes, limits: Limits | None = None):
    return parse_docx(CapturedFile("file_d", "d.docx", "captured", data=data, sha256=sha256(data), kind="docx"), limits or Limits())


ROADMAP_PARAS = [p.replace("\n", " ") for p in fx("roadmap.md").decode().split("\n\n")]


# ---------------- DOCX unit ----------------
def test_docx_paragraph_locations():
    d = parse(make_docx(["Title", "Second paragraph with words", "Third"]))
    assert [p.pid for p in d.paragraphs] == ["00000001", "00000002", "00000003"]
    i = d.text.index("with")
    loc = d.location(i, i + 4)
    assert loc["paragraph_id"] == "00000002" and loc["para_start"] == len("Second paragraph ")
    assert loc["line_start"] is None


def test_docx_tabs_breaks_and_tracked_deletions():
    xml = (f'<w:document {W_NS}><w:body><w:p><w:r><w:t>a</w:t><w:tab/><w:t>b</w:t><w:br/><w:t>c</w:t></w:r>'
           '<w:del><w:r><w:delText>gone</w:delText></w:r></w:del></w:p></w:body></w:document>').encode()
    d = parse(make_docx([], raw_xml=xml))
    assert d.text == "a\tb\nc"


def test_docx_refuses_doctype_and_entities():
    xml = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]>'
           b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
    with pytest.raises(DocxError) as ei:
        parse(make_docx([], raw_xml=xml))
    assert ei.value.reason == "docx_doctype_refused"


def test_docx_size_bounds():
    bomb = make_docx(["x"], extra={"word/media/zeros.bin": b"\0" * (3 * 1024 * 1024)})
    with pytest.raises(DocxError) as ei:
        parse(bomb)
    assert ei.value.reason == "docx_compression_ratio"
    many = make_docx(["x"], extra={f"word/media/{i}.txt": b"a" for i in range(250)})
    with pytest.raises(DocxError) as ei:
        parse(many)
    assert ei.value.reason == "docx_too_many_entries"
    with pytest.raises(DocxError) as ei:
        parse(b"not a zip")
    assert ei.value.reason == "not_a_docx"
    small = Limits(docx_max_uncompressed_bytes=1000)
    with pytest.raises(DocxError) as ei:
        parse(make_docx(["y" * 2000]), small)
    assert ei.value.reason == "docx_too_large_uncompressed"


def test_docx_macros_and_external_relationships_only_noted():
    rels = b'<Relationships><Relationship Id="r1" Target="https://tracker.example/x.png" TargetMode="External"/></Relationships>'
    d = parse(make_docx(["Hello there"], extra={"word/vbaProject.bin": b"\x00macro", "word/_rels/document.xml.rels": rels}))
    assert "macros_present_ignored" in d.notes and "external_relationships_not_fetched" in d.notes


# ---------------- DOCX end to end ----------------
def test_docx_public_match_and_rules_with_paragraph_evidence(env):
    data = make_docx(ROADMAP_PARAS + ["CONFIDENTIAL — do not forward."])
    inp = env.upload({"roadmap.docx": data, "broken.docx": b"PK\x03\x04garbage"})
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"], public_sources=PUBLIC, model_review=False)
    assert s["state"] == "partial"  # broken.docx is reported, so the whole input is not claimed complete
    assert any(c["scope"] == "file" and c["reason"] == "not_a_docx" for c in s["coverage"])
    fs = env.findings(s["scan_id"])
    pub = next(f for f in fs if f["kind"] == "public_exposure")
    loc = pub["latest"]["evidence"][0]["location"]
    assert loc["paragraph_id"] == "00000003" and loc["line_start"] is None
    assert any(f["rule_id"] == "doc_confidential_marker" for f in fs)
    ev = env.client.get(f"/v1/workspaces/ws_a/evidence/{pub['latest']['evidence'][0]['evidence_id']}", headers=env.h()).json()
    assert "Harbor ingestion cluster" in ev["local_text"]


# ---------------- Git change capture ----------------
def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
                   cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(env):
    r = env.root
    git(r, "init", "-q", "-b", "main")
    (r / "app.py").write_text("def ok():\n    return 1\n")
    (r / "keep.md").write_text("unchanged\n")
    (r / "old.py").write_text("x = 1\n")
    (r / "moved.txt").write_text("content that moves\n")
    (r / ".gitignore").write_text("ignored.log\n")
    git(r, "add", "-A")
    git(r, "commit", "-q", "-m", "base")
    return r


def capture_changes(env, **kw):
    return env.client.post("/v1/workspaces/ws_a/captures", headers=env.h(), json={"mode": "changes", **kw})


def test_git_selects_staged_unstaged_untracked(env, repo):
    (repo / "app.py").write_text(fx("risky_app.py").decode())          # unstaged modification
    (repo / "staged.py").write_text("PAYMENTS_API_KEY = 'q8Zr2LmV9xKp4TnWb7Hd'\n")
    git(repo, "add", "staged.py")                                      # staged addition
    (repo / "scratch.py").write_text("print('hi')\n")                  # untracked
    (repo / "ignored.log").write_text("noise\n")                       # ignored
    (repo / "old.py").unlink()                                         # deletion
    (repo / "moved.txt").rename(repo / "renamed.txt")                  # rename (untracked new path)
    r = capture_changes(env, baseline="HEAD", include_untracked=False)
    assert r.status_code == 201, r.text
    by = {f["path"]: f for f in r.json()["files"]}
    assert by["app.py"]["change"] == "modified" and by["staged.py"]["change"] == "added"
    assert by["old.py"]["status"] == "deleted" and by["moved.txt"]["status"] == "deleted"
    assert "scratch.py" not in by and "keep.md" not in by and "ignored.log" not in by
    assert len(r.json()["baseline"]) == 40
    assert "cross_file_context_not_captured" in r.json()["omitted_context"]

    r = capture_changes(env, baseline="HEAD", include_untracked=True)
    by = {f["path"]: f for f in r.json()["files"]}
    assert by["scratch.py"]["change"] == "untracked" and "ignored.log" not in by
    assert by["renamed.txt"]["change"] == "renamed" and "moved.txt" not in by
    # the change capture feeds a real scan
    s = env.scan(r.json()["input_id"], model_review=False)
    rules = sorted(f["rule_id"] for f in env.findings(s["scan_id"]))
    assert rules == ["py_sensitive_logging", "py_sensitive_logging", "secret_literal"]
    assert any(c["scope"] == "file" and c["reason"] == "deleted_in_working_tree" for c in s["coverage"])


def test_git_baseline_validation(env, repo):
    for bad in ["--output=/tmp/x", "HEAD;rm -rf /", "../../etc", "$(id)", "nope-branch"]:
        r = capture_changes(env, baseline=bad)
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_baseline", bad
    (repo / "app.py").write_text("def ok():\n    return 2\n")
    git(repo, "commit", "-qam", "second")
    r = capture_changes(env, baseline="HEAD~1")
    assert r.status_code == 201 and [f["path"] for f in r.json()["files"]] == ["app.py"]
    assert capture_changes(env, baseline="HEAD").json()["error"]["code"] == "no_changes"


def test_git_never_runs_repo_helpers(env, repo, tmp_path):
    marker = tmp_path / "pwned"
    git(repo, "config", "core.fsmonitor", f"touch {marker}")
    git(repo, "config", "filter.evil.clean", f"touch {marker}; cat")
    git(repo, "config", "diff.evil.textconv", f"touch {marker}; cat")
    git(repo, "config", "core.hooksPath", str(repo / "hooks"))
    (repo / "hooks").mkdir()
    (repo / "hooks" / "post-index-change").write_text(f"#!/bin/sh\ntouch {marker}\n")
    (repo / "hooks" / "post-index-change").chmod(0o755)
    (repo / ".gitattributes").write_text("*.py filter=evil diff=evil\n")
    (repo / "app.py").write_text("def ok():\n    return 3\n")
    r = capture_changes(env, include_untracked=True)
    assert r.status_code == 201, r.text
    assert not marker.exists()


def test_git_symlinks_and_excluded(env, repo):
    (repo / ".env").write_text("SECRET=1\n")
    import os
    os.symlink("/etc/hosts", repo / "hosts.txt")
    (repo / "app.py").write_text("x = 2\n")
    r = capture_changes(env, include_untracked=True)
    by = {f["path"]: f for f in r.json()["files"]}
    assert by["hosts.txt"]["reason"] == "symlink_refused"
    assert by[".env"]["reason"] == "excluded_path"


def test_git_concurrent_change_rejected(env, repo):
    (repo / "app.py").write_text("x = 2\n")

    def mutate():
        (repo / "app.py").write_text("x = 3  # edited while capturing\n")
    env.engine.hooks.after_read = mutate
    r = capture_changes(env)
    assert r.status_code == 409 and r.json()["error"]["code"] == "capture_conflict"


def test_not_a_repository(env):
    r = capture_changes(env)
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_a_git_repository"
