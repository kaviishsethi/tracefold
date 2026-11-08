"""Industry packs: the company's industry switches on extra regulated-data checks."""
from types import SimpleNamespace

from tracefold.checks.rules import industry_checks

DOC = """Customer card 4111 1111 1111 1111 on file; old card 4111 1111 1111 1112 rejected.
Wire to IBAN GB82 WEST 1234 5698 7654 32, routing number: 021000021.
Patient MRN: A1234567, DOB: 04/12/1987, referring NPI 1234567893.
CONTROLLED UNCLASSIFIED INFORMATION. Passport number: X1234567.
"""


def doc(text=DOC):
    return SimpleNamespace(text=text, kind="text", language=None)


def titles(industry):
    return sorted(h.title for h in industry_checks(doc(), industry))


def test_each_industry_checks_its_own_data():
    assert titles("financial") == ["Apparent bank account (IBAN)", "Apparent bank routing number", "Apparent payment card number"]
    assert titles("healthcare") == ["Apparent date of birth", "Apparent medical record number", "Apparent provider NPI"]
    assert titles("government") == ["Apparent passport number", "Government handling marking"]
    assert titles("retail") == ["Apparent payment card number"]
    assert titles("technology") == [] and titles(None) == []


def test_checksums_reject_look_alikes_and_values_are_masked():
    cards = [h for h in industry_checks(doc(), "financial") if h.meta["pack"] == "card"]
    assert len(cards) == 1 and cards[0].secret_values == ["4111 1111 1111 1111"]   # the ...1112 number fails Luhn
    assert industry_checks(doc("routing number: 021000022"), "financial") == []      # fails the ABA checksum
    assert industry_checks(doc("NPI 1234567890"), "healthcare") == []                # fails the NPI checksum


def test_scan_uses_the_saved_industry(env):
    env.client.put("/v1/workspaces/ws_a/company", headers=env.h(), json={
        "name": "Halyard Freight", "reply_to": "legal@halyardfreight.com", "industry": "healthcare"})
    assert env.client.get("/v1/workspaces/ws_a/company", headers=env.h()).json()["industry"] == "healthcare"
    inp = env.upload({"intake.txt": b"Patient MRN: A1234567 was discharged.\n"})
    s = env.scan(inp["input_id"], model_review=False)
    found = [f["latest"]["title"] for f in env.findings(s["scan_id"])]
    assert "Apparent medical record number" in found
    assert "A1234567" not in str(env.findings(s["scan_id"]))
