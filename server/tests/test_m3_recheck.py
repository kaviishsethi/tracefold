"""Milestone 3: recheck and finding history."""
from __future__ import annotations

from .conftest import PUBLIC, fx

PASSAGE = fx("roadmap.md").decode().split("## Summary\n\n")[1].split("\n\n")[0]

SERVICE_RISKY = f'''"""
{PASSAGE}
"""
import logging

logger = logging.getLogger(__name__)


def charge(card_number: str, amount: int) -> None:
    logger.info("charging card %s for %d", card_number, amount)
'''

SERVICE_FIXED = SERVICE_RISKY.replace('logger.info("charging card %s for %d", card_number, amount)',
                                      'logger.info("charging card ending %s for %d", mask(card_number), amount)')


def write(env, name, text):
    (env.root / name).write_text(text)


def recheck(env, finding_id, input_id, who="mcp"):
    r = env.client.post(f"/v1/workspaces/ws_a/findings/{finding_id}/rechecks", headers=env.h(who), json={"input_id": input_id})
    assert r.status_code == 202, r.text
    env.engine.runner.run_pending()
    detail = env.client.get(f"/v1/workspaces/ws_a/findings/{finding_id}", headers=env.h(who)).json()
    rc = next(x for x in detail["rechecks"] if x["recheck_id"] == r.json()["recheck_id"])
    return detail, rc, r.json()


def test_fix_and_recheck_keeps_public_exposure_open(env):
    write(env, "service.py", SERVICE_RISKY)
    inp = env.capture(["service.py"])
    s = env.scan(inp["input_id"], checks=["public_match", "local_risk"], public_sources=PUBLIC, model_review=False)
    assert s["state"] == "completed", s
    fs = env.findings(s["scan_id"])
    local = next(f for f in fs if f["kind"] == "local_risk")
    public = next(f for f in fs if f["kind"] == "public_exposure")
    assert local["latest"]["evidence"][0]["location"]["line_start"] == SERVICE_RISKY.splitlines().index(
        '    logger.info("charging card %s for %d", card_number, amount)') + 1

    # the assistant applies the reviewed correction through the editor workflow, then rechecks
    write(env, "service.py", SERVICE_FIXED)
    inp2 = env.capture(["service.py"], who="mcp")
    detail, rc, acc = recheck(env, local["finding_id"], inp2["input_id"])
    assert rc["outcome"] == "not_detected_in_checked_version", rc
    assert detail["status"] == "not_detected_in_checked_version"
    assert len(detail["observations"]) == 1  # history: the original detection is retained
    # the recheck scan is scoped to the finding's check only
    rs = env.get_scan(acc["scan_id"])
    assert rs["checks"] == ["local_risk"] and rs["recheck_of"] == local["finding_id"]
    # the platform client sees the same updated finding; the public copy stays open
    pub_now = env.client.get(f"/v1/workspaces/ws_a/findings/{public['finding_id']}", headers=env.h("app")).json()
    assert pub_now["status"] == "open"
    loc_now = env.client.get(f"/v1/workspaces/ws_a/findings/{local['finding_id']}", headers=env.h("app")).json()
    assert loc_now["status"] == "not_detected_in_checked_version" and loc_now["rechecks"][0]["outcome"] == rc["outcome"]


def test_unfixed_recheck_still_detected(env):
    write(env, "service.py", SERVICE_RISKY)
    s = env.scan(env.capture(["service.py"])["input_id"], model_review=False)
    local = env.findings(s["scan_id"])[0]
    write(env, "service.py", SERVICE_RISKY + "\n# unrelated edit\n")
    detail, rc, _ = recheck(env, local["finding_id"], env.capture(["service.py"])["input_id"])
    assert rc["outcome"] == "still_detected" and detail["status"] == "open"
    assert len(detail["observations"]) == 2


def test_edited_but_still_risky_is_not_cleared(env):
    write(env, "service.py", SERVICE_RISKY)
    s = env.scan(env.capture(["service.py"])["input_id"], model_review=False)
    local = env.findings(s["scan_id"])[0]
    write(env, "service.py", SERVICE_RISKY.replace('"charging card %s for %d"', '"card=%s amount=%d"'))
    detail, rc, _ = recheck(env, local["finding_id"], env.capture(["service.py"])["input_id"])
    assert rc["outcome"] == "still_detected" and rc["reason"] == "same_rule_detected_at_changed_location"
    assert detail["status"] == "open"


def test_stale_recheck_cannot_clear_newer_detection(env):
    write(env, "service.py", SERVICE_RISKY)
    s1 = env.scan(env.capture(["service.py"])["input_id"], model_review=False)
    local = env.findings(s1["scan_id"])[0]
    write(env, "service.py", SERVICE_FIXED)
    fixed_input = env.capture(["service.py"])            # older capture (fixed)
    write(env, "service.py", SERVICE_RISKY)
    newer = env.capture(["service.py"])                  # newer capture (risky again)
    env.scan(newer["input_id"], model_review=False)      # newer revision detects the issue
    assert fixed_input["revision"] < newer["revision"]
    detail, rc, _ = recheck(env, local["finding_id"], fixed_input["input_id"])
    assert rc["outcome"] == "not_detected_in_checked_version"
    assert rc["reason"] == "stale_revision_newer_capture_owns_current_status"
    assert detail["status"] == "open" and detail["current_revision"] == newer["revision"]


def test_stale_scan_completion_only_adds_history(env):
    write(env, "service.py", SERVICE_RISKY)
    risky_old = env.capture(["service.py"])
    s1 = env.scan(risky_old["input_id"], model_review=False)
    local = env.findings(s1["scan_id"])[0]
    write(env, "service.py", SERVICE_FIXED)
    detail, rc, _ = recheck(env, local["finding_id"], env.capture(["service.py"])["input_id"])
    assert detail["status"] == "not_detected_in_checked_version"
    # an older capture that is scanned again afterwards must not reopen the newer cleared status
    env.engine.registry.get(risky_old["input_id"]).consumed = False
    env.scan(risky_old["input_id"], model_review=False)
    after = env.client.get(f"/v1/workspaces/ws_a/findings/{local['finding_id']}", headers=env.h()).json()
    assert after["status"] == "not_detected_in_checked_version"
    assert len(after["observations"]) == 2


def test_inconclusive_when_file_missing_or_unparseable(env):
    write(env, "service.py", SERVICE_RISKY)
    s = env.scan(env.capture(["service.py"])["input_id"], model_review=False)
    local = env.findings(s["scan_id"])[0]
    write(env, "other.py", "x = 1\n")
    _, rc, _ = recheck(env, local["finding_id"], env.capture(["other.py"])["input_id"])
    assert rc["outcome"] == "inconclusive" and rc["reason"] == "file_not_in_capture"
    write(env, "service.py", "def broken(:\n")
    detail, rc, _ = recheck(env, local["finding_id"], env.capture(["service.py"])["input_id"])
    assert rc["outcome"] == "inconclusive" and rc["reason"].startswith("incomplete_coverage")
    assert detail["status"] == "open"


def test_public_recheck_requires_fresh_retrieval(env):
    inp = env.upload({"roadmap.md": fx("roadmap.md")})
    s = env.scan(inp["input_id"], checks=["public_match"], public_sources=PUBLIC)
    pub = env.findings(s["scan_id"])[0]
    # the public page still contains the passage -> still detected
    detail, rc, acc = recheck(env, pub["finding_id"], inp["input_id"])
    assert rc["outcome"] == "still_detected" and detail["status"] == "open"
    rs = env.get_scan(acc["scan_id"])
    assert rs["checks"] == ["public_match"] and rs["public_freshness"] == "fresh retrieval"
    # the copy is removed from the page: only a fresh successful retrieval can show it is no longer observed
    env.engine.repo.put_manifest("ws_a", "sources_main", [
        {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/vendor_blog.html"}])
    detail, rc, _ = recheck(env, pub["finding_id"], inp["input_id"])
    assert rc["outcome"] == "not_detected_in_checked_version" and detail["status"] == "no_longer_observed"
    # a failed retrieval cannot establish removal
    env.engine.repo.put_manifest("ws_a", "sources_main", [
        {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/missing.html"}])
    env.engine.repo.update_finding(pub["finding_id"], status="open")
    detail, rc, _ = recheck(env, pub["finding_id"], inp["input_id"])
    assert rc["outcome"] == "inconclusive" and detail["status"] == "open"


def test_remaining_copy_prevents_closing(env):
    """Two public copies: removing one leaves the other occurrence open."""
    env.engine.repo.put_manifest("ws_a", "two_copies", [
        {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/forum_post.html"},
        {"source_id": "mirror", "url": "https://mirror.example/p/9", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/forum_post.html"}])
    inp = env.upload({"roadmap.md": fx("roadmap.md")})
    s = env.scan(inp["input_id"], checks=["public_match"], public_sources={"manifest_id": "two_copies"})
    fs = env.findings(s["scan_id"])
    assert len(fs) == 2
    env.engine.repo.put_manifest("ws_a", "two_copies", [
        {"source_id": "forum", "url": "https://forum.example/t/123", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/vendor_blog.html"},
        {"source_id": "mirror", "url": "https://mirror.example/p/9", "provider": "fixture", "mode": "seeded",
         "fixture_path": "public/forum_post.html"}])
    s2 = env.scan(inp["input_id"], checks=["public_match"], public_sources={"manifest_id": "two_copies"})
    status = {f["latest"]["source_id"] if False else f["latest"]["evidence"][0]["public"]["source_id"]: f["status"]
              for f in env.findings()}
    assert status == {"forum": "no_longer_observed", "mirror": "open"}


def test_human_review_and_history(env):
    write(env, "service.py", SERVICE_RISKY)
    s = env.scan(env.capture(["service.py"])["input_id"], model_review=False)
    f = env.findings(s["scan_id"])[0]
    url = f"/v1/workspaces/ws_a/findings/{f['finding_id']}/review"
    r = env.client.patch(url, headers=env.h(), json={"state": "dismissed", "expected_version": f["version"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "reason_required"
    r = env.client.patch(url, headers=env.h(), json={"state": "dismissed", "reason": "test fixture", "expected_version": f["version"]})
    assert r.status_code == 200 and r.json()["human_review"] == "dismissed" and r.json()["version"] == f["version"] + 1
    r = env.client.patch(url, headers=env.h(), json={"state": "acknowledged", "expected_version": f["version"]})
    assert r.status_code == 409
    # dismissal never deletes evidence or detection status
    d = env.client.get(f"/v1/workspaces/ws_a/findings/{f['finding_id']}", headers=env.h()).json()
    assert d["status"] == "open" and d["observations"][0]["evidence"]
    # capability enforcement
    r = env.client.patch(url, headers=env.h("cloud"), json={"state": "acknowledged", "expected_version": 2})
    assert r.status_code == 403


def test_recheck_idempotency_and_access(env):
    write(env, "service.py", SERVICE_RISKY)
    s = env.scan(env.capture(["service.py"])["input_id"], model_review=False)
    f = env.findings(s["scan_id"])[0]
    write(env, "service.py", SERVICE_FIXED)
    inp = env.capture(["service.py"])
    url = f"/v1/workspaces/ws_a/findings/{f['finding_id']}/rechecks"
    r1 = env.client.post(url, headers=env.h(**{"Idempotency-Key": "r1"}), json={"input_id": inp["input_id"]})
    r2 = env.client.post(url, headers=env.h(**{"Idempotency-Key": "r1"}), json={"input_id": inp["input_id"]})
    assert r1.json() == r2.json()
    assert env.client.post(url, headers=env.h("other"), json={"input_id": inp["input_id"]}).status_code == 404
    assert env.client.post(url, headers=env.h("cloud"), json={"input_id": inp["input_id"]}).status_code == 403
