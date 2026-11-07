"""Milestone 2: text/code parser, exact matcher, deterministic rules, fixture public adapter."""
from __future__ import annotations

from tracefold.checks import matcher
from tracefold.checks.rules import run_rules
from tracefold.inputs.registry import CapturedFile
from tracefold.parsing.document import parse_text
from tracefold.retrieval.html import html_to_text
from tracefold.util import sha256

from .conftest import FIXTURES, PUBLIC, fx


def doc(name: str, data: bytes | None = None, kind="text", lang=None):
    data = data if data is not None else fx(name)
    return parse_text(CapturedFile("file_x", name, "captured", data=data, sha256=sha256(data), kind=kind, language=lang))


def forum_text() -> str:
    return html_to_text((FIXTURES / "public" / "forum_post.html").read_text())


# ---------------- unit: parser ----------------
def test_parser_locations():
    d = doc("x.md", b"\xef\xbb\xbfline one\r\nline two\nline three")
    assert d.text.startswith("line one\nline two")
    i = d.text.index("two")
    loc = d.location(i, i + 3)
    assert (loc["line_start"], loc["line_end"]) == (2, 2)
    assert d.text[loc["start"]:loc["end"]] == "two"


def test_html_extraction_drops_scripts():
    t = forum_text()
    assert "tracking" not in t and "Harbor ingestion cluster" in t


# ---------------- unit: matcher ----------------
def test_exact_match_positive_with_original_offsets():
    local = doc("roadmap.md")
    pub = forum_text()
    res = matcher.find_matches(local.text, pub, "text_v1")
    assert len(res.matches) == 1
    m = res.matches[0]
    assert m.tokens >= 30
    assert local.text[m.local_start:m.local_end].startswith("In the first half of 2027")
    assert local.text[m.local_start:m.local_end].endswith("nightly batch\nexports")
    assert pub[m.public_start:m.public_end].startswith("In the first half of 2027")
    loc = local.location(m.local_start, m.local_end)
    assert (loc["line_start"], loc["line_end"]) == (5, 7)


def test_same_topic_and_unrelated_stay_negative():
    pub = forum_text() + "\n\n" + html_to_text((FIXTURES / "public" / "vendor_blog.html").read_text())
    assert matcher.find_matches(doc("same_topic.md").text, pub, "text_v1").matches == []
    assert matcher.find_matches(doc("unrelated.txt").text, pub, "text_v1").matches == []


def test_boilerplate_is_not_reported():
    res = matcher.find_matches(doc("license_only.txt").text, forum_text(), "text_v1")
    assert res.matches == [] and res.boilerplate_skipped == 1


def test_short_overlap_below_threshold():
    local = "we will retire the Harbor ingestion cluster soon"  # 8 tokens < 12
    assert matcher.find_matches(local, forum_text(), "text_v1").matches == []


def test_normalization_case_whitespace_unicode():
    local = "IN THE FIRST HALF of 2027 we will\tretire the Harbor ingestion cluster and move every tenant"
    pub = "In  the first half of 2027 we will retire the ＨＡＲＢＯＲ ingestion cluster and move every tenant onto"
    assert len(matcher.find_matches(local, pub, "text_v1").matches) == 1


def test_code_policy_is_case_sensitive():
    code = "def handler(event, context):\n    result = compute_total(event['items'], context.region, rate=0.07)\n    return result\n"
    assert len(matcher.find_matches(code, code.replace("\n", " "), "code_v1").matches) == 1
    assert matcher.find_matches(code, code.upper(), "code_v1").matches == []


# ---------------- unit: rules ----------------
def test_logging_rule_flags_risky_and_not_fixed():
    hits, notes = run_rules(doc("risky_app.py", kind="code", lang="python"))
    log_hits = [h for h in hits if h.rule_id == "py_sensitive_logging"]
    assert sorted(h.meta["line"] for h in log_hits) == [7, 10]
    assert {tuple(h.meta["names"]) for h in log_hits} == {("password",), ("session_token",)}
    assert not notes
    fixed, _ = run_rules(doc("fixed_app.py", kind="code", lang="python"))
    assert [h for h in fixed if h.rule_id == "py_sensitive_logging"] == []


def test_logging_rule_benign_lookalikes():
    hits, _ = run_rules(doc("benign_lookalike.py", kind="code", lang="python"))
    assert hits == []


def test_secret_literal_rule_masks_and_skips_placeholders():
    d = doc("config_with_secret.py", kind="code", lang="python")
    hits, _ = run_rules(d)
    assert [h.rule_id for h in hits] == ["secret_literal"]
    h = hits[0]
    assert d.text[h.start:h.end] == "q8Zr2LmV9xKp4TnWb7Hd"
    assert "q8Zr2LmV9xKp4TnWb7Hd" not in h.claim and "your-token" not in h.claim


def test_document_rules():
    hits, _ = run_rules(doc("hr_note.md"))
    assert sorted(h.rule_id for h in hits) == ["doc_confidential_marker", "doc_personal_identifier"]
    assert all("512-44-8721" not in h.claim for h in hits)


def test_unsupported_language_reported():
    hits, notes = run_rules(doc("a.js", b"const apiKey = 'Zx81LmQ02pNnB7rT';\nconsole.log(password)\n", kind="code", lang="javascript"))
    assert [h.rule_id for h in hits] == ["secret_literal"]
    assert notes == {"py_sensitive_logging": "unsupported_language"}


def test_python_syntax_error_is_partial():
    hits, notes = run_rules(doc("bad.py", b"def broken(:\n  print(password)\n", kind="code", lang="python"))
    assert notes == {"py_sensitive_logging": "python_syntax_error"}


# ---------------- API end to end ----------------
def test_public_match_end_to_end(env):
    inp = env.upload({"roadmap.md": fx("roadmap.md"), "same_topic.md": fx("same_topic.md"),
                      "unrelated.txt": fx("unrelated.txt"), "license_only.txt": fx("license_only.txt")})
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"], public_sources=PUBLIC, model_review=False)
    assert s["state"] == "completed", s
    assert s["public_freshness"] == "fresh retrieval" and s["public_snapshot_id"]
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("check", "public_match")]["status"] == "complete"
    assert cov[("check", "public_match")]["counts"]["boilerplate_skipped"] == 1
    assert cov[("source", "forum")]["status"] == "complete"
    fs = env.findings(s["scan_id"])
    pub = [f for f in fs if f["kind"] == "public_exposure"]
    assert len(pub) == 1 and pub[0]["path"] == "roadmap.md" and pub[0]["status"] == "open"
    ev = pub[0]["latest"]["evidence"][0]
    assert ev["public"]["url"] == "https://forum.example/t/123" and ev["public"]["freshness"] == "fresh"
    assert ev["location"]["line_start"] == 5 and ev["matched_tokens"] >= 30
    assert pub[0]["latest"]["title"] == "Matching content found publicly"
    full = env.client.get(f"/v1/workspaces/ws_a/evidence/{ev['evidence_id']}", headers=env.h()).json()
    assert full["availability"] == "available"
    assert "retire the Harbor ingestion cluster" in full["local_text"]
    assert "retire the Harbor ingestion cluster" in full["public_text"]
    # same-topic, unrelated and boilerplate stay negative
    assert {f["path"] for f in fs} == {"roadmap.md"}
    # the second client sees the same finding IDs
    assert [f["finding_id"] for f in env.findings(s["scan_id"], who="mcp")] == [f["finding_id"] for f in fs]


def test_failed_source_makes_partial_not_clean(env):
    inp = env.upload({"same_topic.md": fx("same_topic.md")})
    s = env.scan(inp["input_id"], checks=["public_match"],
                 public_sources={"manifest_id": "sources_with_failure", "mode": "refresh"})
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("source", "gone")]["status"] == "failed"
    assert cov[("check", "public_match")]["status"] == "partial"
    assert s["state"] == "partial"


def test_local_risk_only_reports_public_not_requested(env):
    inp = env.upload({"risky_app.py": fx("risky_app.py")})
    s = env.scan(inp["input_id"], checks=["local_risk"], model_review=False)
    assert s["state"] == "completed"
    cov = {(c["scope"], c["id"]): c for c in s["coverage"]}
    assert cov[("check", "public_match")]["status"] == "not_requested"
    fs = env.findings(s["scan_id"])
    assert len(fs) == 2 and all(f["kind"] == "local_risk" and f["rule_id"] == "py_sensitive_logging" for f in fs)
    lines = sorted(f["latest"]["evidence"][0]["location"]["line_start"] for f in fs)
    assert lines == [7, 10]
    assert all(f["latest"]["origin"] == "rule" and f["latest"]["risk_review"] == "not_requested" for f in fs)


def test_invalid_input_keeps_scan_incomplete(env):
    inp = env.upload({"risky_app.py": fx("risky_app.py"), "image.png": b"\x89PNG"})
    s = env.scan(inp["input_id"], checks=["local_risk"], model_review=False)
    assert s["state"] == "partial"
    assert any(c["scope"] == "file" and c["status"] == "failed" and c["reason"] == "unsupported_type" for c in s["coverage"])


def test_secret_evidence_is_masked(env):
    inp = env.upload({"config_with_secret.py": fx("config_with_secret.py")})
    s = env.scan(inp["input_id"], checks=["local_risk"], model_review=False)
    f = env.findings(s["scan_id"])[0]
    eid = f["latest"]["evidence"][0]["evidence_id"]
    full = env.client.get(f"/v1/workspaces/ws_a/evidence/{eid}", headers=env.h()).json()
    assert "q8Zr2LmV9xKp4TnWb7Hd" not in full["local_text"] and "•" in full["local_text"]
    assert "PAYMENTS_API_KEY" in full["local_text"]
    minimal = env.client.get(f"/v1/workspaces/ws_a/evidence/{eid}", headers=env.h("cloud")).json()
    assert minimal["availability"] == "withheld_by_policy" and minimal["local_text"] is None
    assert minimal["location"]["path"] is None
    # nothing stored in the database contains the secret value
    import sqlite3
    con = sqlite3.connect(env.engine.settings.db_path)
    dump = "\n".join(con.iterdump())
    assert "q8Zr2LmV9xKp4TnWb7Hd" not in dump


def test_prompt_injection_text_is_inert(env):
    inp = env.upload({"injection_doc.md": fx("injection_doc.md")})
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"], public_sources=PUBLIC, model_review=False)
    assert s["state"] == "completed"
    assert env.findings(s["scan_id"]) == []
    led = env.client.get(f"/v1/workspaces/ws_a/scans/{s['scan_id']}/ledger", headers=env.h()).json()
    assert all("attacker" not in e["destination_host"] for e in led["items"])


def test_snapshot_mode_reuses_and_labels_cached(env):
    inp = env.upload({"roadmap.md": fx("roadmap.md")})
    s1 = env.scan(inp["input_id"], checks=["public_match"], public_sources=PUBLIC)
    snap = s1["public_snapshot_id"]
    s2 = env.scan(inp["input_id"], checks=["public_match"],
                  public_sources={"manifest_id": "sources_demo", "mode": "snapshot", "snapshot_id": snap})
    assert s2["public_snapshot_id"] == snap and s2["public_freshness"].startswith("cached snapshot")
    f = env.findings(s2["scan_id"])[0]
    assert f["latest"]["evidence"][0]["public"]["freshness"] == "cached"
    assert f["latest"]["title"] == "Matching content in cached public evidence"
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={
        "input_id": inp["input_id"], "checks": ["public_match"],
        "public_sources": {"manifest_id": "sources_demo", "mode": "snapshot"}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "snapshot_required"


def test_unknown_source_ids_rejected(env):
    inp = env.upload({"roadmap.md": fx("roadmap.md")})
    r = env.client.post("/v1/workspaces/ws_a/scans", headers=env.h(), json={
        "input_id": inp["input_id"], "checks": ["public_match"],
        "public_sources": {"manifest_id": "sources_demo", "source_ids": ["https://evil.example"]}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_source"
