"""Idempotently provision all benchmark-company identities and query plans; no provider requests or copied datasets."""
import json
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from tracefold.api.app import create_app
from tracefold.config import Settings
from tracefold.engine import Engine
from tracefold.envfile import load_env_file

SERVER = Path(__file__).resolve().parent.parent

def configure():
    load_env_file(SERVER / '.env')
    data = SERVER / 'data/discovery'
    state = json.loads((data / 'discovery_state.json').read_text())
    settings = Settings(data_dir=data)
    settings.start_runner = False
    settings.allowed_hosts = (*settings.allowed_hosts, 'testserver')
    engine = Engine(settings)
    with TestClient(create_app(engine)) as c:
        h = {'Authorization': 'Bearer ' + state['web_token']}
        b = '/v1/workspaces/ws_main'
        profiles = c.get(b + '/company-profiles', headers=h).raise_for_status().json()['items']
        plans = c.get(b + '/query-plans?limit=100', headers=h).raise_for_status().json()['items']
        hints = {}
        for case in json.loads((SERVER.parent / 'docs/benchmark/cases.json').read_text()):
            identity = case['identity']
            profile = next((p for p in profiles if all(p.get(k) == v for k, v in identity.items())), None)
            if profile is None:
                profile = c.post(b + '/company-profiles', headers=h, json={**identity, 'confirm_public': True}).raise_for_status().json()
                profiles.append(profile)
            presets = (['leak_news', 'leaked_email'] if '_memo' in case['case_id'] else
                       ['leak_news', 'leak_news_alias'] if case['case_id'] == 'nothing' else
                       ['security_docs', 'policy_copies'])
            for reference in case['references']:
                path = SERVER.parent / reference
                if path.is_file():
                    hints[hashlib.sha256(path.read_bytes()).hexdigest()] = {**identity, 'presets': presets}
            plan = next((p for p in plans if p['profile_id'] == profile['profile_id'] and
                         set(q['template_id'] for q in p['searches']) == set(presets) and
                         p['scope'].get('exclude_official_domain') is False), None)
            if plan is None:
                plan = c.post(b + '/query-plans', headers=h, json={
                    'profile_id': profile['profile_id'], 'presets': presets, 'providers': ['exa', 'tavily'],
                    'scope': {'mode': 'broad', 'exclude_official_domain': False, 'exclude_noise': True}
                }).raise_for_status().json()
                plans.append(plan)
            print(case['case_id'], identity['display_name'], 'ready', plan['query_plan_id'])
        (data / 'input_identity_hints.json').write_text(json.dumps({'ws_main': hints}, indent=2) + '\n')

if __name__ == '__main__':
    configure()
