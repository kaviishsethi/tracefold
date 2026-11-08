"""Edited copies: paragraphs mostly reworded but clearly the same text, without flagging same-topic writing."""
from tracefold.checks.matcher import find_matches, find_similar

from .conftest import fx
from .test_m8_discovery import FORUM_CANON, Providers, approved_plan, discover, sources

ORIG = ("Harbor moves every tenant onto the Lantern streaming tier during the first half of 2027, starting with the twelve "
        "logistics customers that still depend on nightly batch exports and the two healthcare pilots that need regional "
        "storage guarantees before they can migrate.")
EDITED = ("In the first half of 2027, Harbor moves all tenants onto the Lantern streaming tier, starting with twelve logistics "
          "customers who still depend on nightly batch exports, plus two healthcare pilots that need regional storage "
          "guarantees before they can migrate.")
SAME_TOPIC = ("Our streaming tier is called Lantern. During 2027 we expect most tenants to move off batch exports. Logistics "
              "customers and healthcare pilots have asked about regional storage guarantees, and we will publish a "
              "migration guide for them in the first half of the year.")


def test_edited_paragraph_is_found_and_located():
    page = "Intro.\n\n" + EDITED + "\n\nCookie notice."
    sims = find_similar(ORIG, page, find_matches(ORIG, page, "text_v1").matches)
    assert len(sims) == 1 and sims[0].containment >= 0.4
    assert "first half of 2027" in page[sims[0].public_start:sims[0].public_end]


def test_same_topic_writing_is_not_a_copy():
    assert find_similar(ORIG, SAME_TOPIC, []) == []


def test_exact_copies_are_not_reported_twice():
    assert find_similar(ORIG, "Intro.\n\n" + ORIG, find_matches(ORIG, ORIG, "text_v1").matches) == []


def test_scan_reports_an_edited_copy_on_a_public_page(env):
    roadmap = fx("roadmap.md").decode()
    summary = roadmap.split("## Summary", 1)[1].split("## Pricing", 1)[0]
    edited = (summary.replace("we will retire", "we're retiring").replace("move every tenant", "moving all tenants")
              .replace("starting with the twelve", "beginning with twelve").replace("still depend", "still rely")
              .replace("will be scheduled per tenant", "get scheduled tenant by tenant").replace("no customer loses", "nobody loses")
              .replace("forty minutes", "about forty minutes"))
    Providers(results={'"Northstar Robotics" internal memo document': [{"url": FORUM_CANON, "title": "Thread", "id": "1"}]},
              pages={FORUM_CANON: "A reply:\n\n" + edited}).install(env)
    p = approved_plan(env)
    s = discover(env, env.upload({"roadmap.md": fx("roadmap.md")})["input_id"], p["query_plan_id"])
    pub = [f for f in env.findings(s["scan_id"]) if f["kind"] == "public_exposure"]
    assert [f["latest"]["title"] for f in pub] == ["Edited copy found publicly"]
    assert pub[0]["latest"]["severity"] == "medium"
    by = {x["original_url"]: x for x in sources(env, s["scan_id"])["items"]}
    assert by[FORUM_CANON]["comparison_status"] == "matched"
