"""Automatic upload scans must work without demo hashes, profile setup or configure permission."""
import json
from types import SimpleNamespace

import pytest

from tracefold.analysis.ollama import ChatResult, ModelUnavailable
from tracefold.discovery.automatic import grounded_names


def fake_model(env, monkeypatch, companies=None, kind="policy", unavailable=False):
    class Client:
        gw = SimpleNamespace(ledger=[])
        def identify(self, **kw):
            if unavailable:
                raise ModelUnavailable("model_not_installed")
            return "local-test"
        def chat(self, system, user, schema, deadline):
            assert "untrusted" in system
            return ChatResult(json.dumps({"companies": companies or [], "kind": kind}), 20, 10)
    monkeypatch.setattr(env.engine.reviewer, "client", lambda: Client())
    # No paid network calls: record that search receives only company names plus fixed templates.
    def search(ctx):
        plan = env.engine.repo.get_query_plan(ctx.scan['public_discovery']['query_plan_id'])
        ctx.summary['tested_queries'] = [q['query'] for q in plan['plan']['searches']]
    monkeypatch.setattr(env.engine.discovery, "search", search)
    monkeypatch.setattr(env.engine.discovery, "fetch", lambda ctx: None)


def test_grounded_only():
    assert grounded_names({'companies': ['Acme', 'Hallucinated']}, 'Acme policy') == ['Acme']
    assert grounded_names({'companies': ['Acme']}, 'Acmeology') == []
    assert grounded_names({'companies': ['sk-abcdefghijklmnop']}, 'sk-abcdefghijklmnop') == []


def test_arbitrary_file_without_profile_or_configure(env, monkeypatch):
    fake_model(env, monkeypatch, ['Example Widgets'])
    inp = env.upload({'renamed.md': b'Example Widgets security policy. PRIVATE_MARKER_DO_NOT_SEARCH'}, who='cloud')
    scan = env.scan(inp['input_id'], checks=['public_match', 'local_risk'], who='cloud',
                    automatic_discovery=True, model_review=False)
    assert scan['summary']['automatic_discovery']['companies'] == ['Example Widgets']
    assert all('Example Widgets' in q and 'PRIVATE_MARKER' not in q for q in scan['summary']['tested_queries'])
    assert scan['summary']['files_parsed'] == 1
    # Identical searches reuse one immutable plan.
    inp2 = env.upload({'another-name.txt': b'Example Widgets security policy. Edited content.'}, who='cloud')
    scan2 = env.scan(inp2['input_id'], checks=['public_match'], who='cloud', automatic_discovery=True, model_review=False)
    assert scan2['public_discovery']['query_plan_id'] == scan['public_discovery']['query_plan_id']


@pytest.mark.parametrize('unavailable,reason', [(False, 'company_not_identified'), (True, 'model_not_installed')])
def test_identity_failure_keeps_local_checks(env, monkeypatch, unavailable, reason):
    fake_model(env, monkeypatch, unavailable=unavailable)
    inp = env.upload({'notes.md': b'An anonymous document without a company.'})
    scan = env.scan(inp['input_id'], checks=['public_match', 'local_risk'], automatic_discovery=True, model_review=False)
    assert scan['state'] == 'partial'
    assert scan['summary']['automatic_discovery']['reason'] == reason
    check = next(c for c in scan['coverage'] if c['scope'] == 'check' and c['id'] == 'public_match')
    assert check['status'] == 'failed' and check['reason'] == reason
    assert scan['summary']['local_rule_hits'] == 0
    assert 'tested_queries' not in scan['summary']


def test_conflicting_modes_rejected(env):
    inp = env.upload({'policy.txt': b'Example Widgets'})
    r = env.client.post('/v1/workspaces/ws_a/scans', headers=env.h(), json={
        'input_id': inp['input_id'], 'checks': ['public_match'], 'automatic_discovery': True,
        'public_sources': {'manifest_id': 'sources_demo'}})
    assert r.status_code == 422


def test_multiple_companies_bounded(env, monkeypatch):
    fake_model(env, monkeypatch, ['Acme', 'Contoso'])
    inp = env.upload({'notes.md': b'Acme and Contoso security policy'})
    scan = env.scan(inp['input_id'], checks=['public_match'], automatic_discovery=True, model_review=False)
    queries = scan['summary']['tested_queries']
    assert len(queries) == 8
    plan = env.engine.repo.get_query_plan(scan['public_discovery']['query_plan_id'])['plan']
    assert len({q['query_id'] for q in plan['searches']}) == 8
    assert all(q['num_results'] == 3 for q in plan['searches'])


def test_preconfigured_attribution_for_nameless_excerpt(env, monkeypatch):
    import hashlib
    fake_model(env, monkeypatch, [], kind="other")
    text = b"A short genuine quotation without an organization name."
    digest = hashlib.sha256(text).hexdigest()
    (env.engine.settings.data_dir / 'input_identity_hints.json').write_text(json.dumps({
        'ws_a': {digest: {'display_name': 'Example Widgets', 'official_domain': None, 'public_aliases': []}}}))
    inp = env.upload({'excerpt.txt': text})
    scan = env.scan(inp['input_id'], checks=['public_match'], automatic_discovery=True, model_review=False)
    assert scan['summary']['automatic_discovery']['companies'] == ['Example Widgets']
    assert scan['summary']['automatic_discovery']['configured_attribution'] is True
    # Editing the excerpt removes the attribution; arbitrary text cannot borrow its identity.
    inp = env.upload({'excerpt.txt': text + b' edited'})
    scan = env.scan(inp['input_id'], checks=['public_match'], automatic_discovery=True, model_review=False)
    assert scan['summary']['automatic_discovery']['reason'] == 'company_not_identified'
