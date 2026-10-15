"""Release evidence must be sourced from the deployed service, not local SDK calls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load():
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    from live_deployment_check import HttpResult
    import public_planner_probe
    return public_planner_probe, HttpResult


def test_public_probe_repeats_authenticated_real_sessions():
    module, HttpResult = _load()
    calls = []
    def fake_request(base, route, *, method='GET', token=None, json_body=None, **kw):
        calls.append((route, method, token))
        if route == '/health':
            value = {'release_id': 'r6-contract'}
        elif route == '/api/demo':
            index = sum(r == '/api/demo' for r, _, _ in calls)
            value = {'session_id': f'case-{index}', 'session_token': f'secret-{index}'}
        elif route.endswith('/analyze'):
            assert token is not None
            value = {'state': 'ANALYZED'}
        elif route.endswith('/plan'):
            assert token is not None
            value = {'state': 'AWAITING_APPROVAL', 'decision': {
                'selected_candidate_ids': ['c1'],
                'planner_used': 'gemini-test-model', 'fallback_used': False}}
        else:
            assert method == 'DELETE' and token is not None
            value = {'deleted': True}
        return HttpResult(200, json.dumps(value).encode(), {}, 5.0)
    with patch.object(module, '_request', side_effect=fake_request):
        result = module.run('https://actual.example', 'r6-contract', 5)
    assert result['proof_mode'] == 'public_fresh_sessions'
    assert result['origin'] == 'https://actual.example'
    assert result['runs'] == 5
    assert sum(method == 'DELETE' for _, method, _ in calls) == 5
    assert sum(route.endswith('/plan') for route, _, _ in calls) == 5


def test_public_probe_rejects_deterministic_or_fallback_provenance():
    module, HttpResult = _load()
    def fake_request(base, route, *, method='GET', token=None, **kw):
        if route == '/health':
            body = {'release_id': 'r6-contract'}
        elif route == '/api/demo':
            body = {'session_id': 'x', 'session_token': 'secret'}
        elif route.endswith('/analyze'):
            body = {'state': 'ANALYZED'}
        elif route.endswith('/plan'):
            body = {'state': 'AWAITING_APPROVAL', 'decision': {
                'selected_candidate_ids': ['c1'], 'planner_used': 'deterministic',
                'fallback_used': False}}
        else:
            body = {'deleted': True}
        return HttpResult(200, json.dumps(body).encode(), {}, 5.0)
    with patch.object(module, '_request', side_effect=fake_request):
        with pytest.raises(RuntimeError, match='Gemini planning did not complete'):
            module.run('https://actual.example', 'r6-contract', 5)
