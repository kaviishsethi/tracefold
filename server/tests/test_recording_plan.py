"""docs/RECORDING_PLAN.md fallback: the Northstar controlled reconstruction, with the plan's exact text.

The live path additionally needs the Gist published; here the public copy is served by the fixture provider.
The Nothing-memo live path is rehearsed by examples/rehearsal.py against Exa (article text is not retained).
"""
from __future__ import annotations

from .conftest import FIXTURES
from .test_m4_docx_git import make_docx

NS = FIXTURES / "northstar"


def test_northstar_partial_document_match_and_negative(env):
    env.engine.add_manifest("ws_a", "northstar", [
        {"source_id": "northstar_gist", "url": "https://gist.github.com/tracefold-samples/northstar", "provider": "fixture",
         "fixture_path": "northstar/northstar-public-copy.md"}])
    paras = NS.joinpath("partner-guide.paragraphs.txt").read_text().strip().split("\n\n")
    docx = make_docx(paras)
    inp = env.upload({"partner-guide.docx": docx})
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"],
                 public_sources={"manifest_id": "northstar"}, model_review=False)
    assert s["state"] == "completed", s
    pub = [f for f in env.findings(s["scan_id"]) if f["kind"] == "public_exposure"]
    assert len(pub) == 1
    ev = pub[0]["latest"]["evidence"][0]
    # the match is exactly the shared heading + handoff passage; the internal review notes are not part of it
    from tracefold.checks.matcher import tokenize
    expected = len(tokenize(paras[1] + " " + paras[2], "text_v1"))
    assert ev["location"]["paragraph_id"] == "00000002" and ev["matched_tokens"] == expected
    full = env.client.get(f"/v1/workspaces/ws_a/evidence/{ev['evidence_id']}", headers=env.h()).json()
    assert "ND-742-MAPLE" in full["public_text"] and "blue" in full["local_text"]
    assert "each Thursday" not in env.client.get(
        f"/v1/workspaces/ws_a/evidence/{ev['evidence_id']}", headers=env.h()).json()["public_text"]

    neg = env.upload({"partner-guide-unpublished.md": NS.joinpath("partner-guide-unpublished.md").read_bytes()})
    s2 = env.scan(neg["input_id"], checks=["public_match"], public_sources={
        "manifest_id": "northstar", "mode": "snapshot", "snapshot_id": s["public_snapshot_id"]})
    assert s2["state"] == "completed" and env.findings(s2["scan_id"]) == []
    pm = next(c for c in s2["coverage"] if c["scope"] == "check" and c["id"] == "public_match")
    assert pm["status"] == "complete" and pm["counts"]["sources_ok"] == 1


def test_batch_reference_alone_is_not_a_match(env):
    env.engine.add_manifest("ws_a", "northstar", [
        {"source_id": "northstar_gist", "url": "https://gist.github.com/tracefold-samples/northstar", "provider": "fixture",
         "fixture_path": "northstar/northstar-public-copy.md"}])
    inp = env.upload({"note.md": b"# Partner handoff procedure\n\nSee batch reference ND-742-MAPLE for details.\n"})
    s = env.scan(inp["input_id"], checks=["public_match"], public_sources={"manifest_id": "northstar"})
    assert env.findings(s["scan_id"]) == []
