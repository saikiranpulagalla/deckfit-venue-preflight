"""R7 regressions for visual coverage, upload lifecycle and approval recovery."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app import main
from app.pptx.parser import parse_pptx_shapes
from app.storage.sessions import SessionStore

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / 'demo/venue-agent-demo.pptx'
OVERLAY = ROOT / 'backend/tests/fixtures/r6/r6-text-outline-overlay.pptx'
VENUE = {'active_image_height_m': 1.8, 'farthest_viewer_distance_m': 10.8,
         'measurement_basis': 'MEASURED'}
CONSTRAINTS = {'max_mutations': 2, 'max_scale_factor': 1.6,
               'minimum_target_coverage': 0.75, 'protect_titles': True,
               'semantic_rewrite': False}


def test_populated_outlined_textbox_is_unknown_without_poisoning_clean_demo():
    unknown = parse_pptx_shapes(OVERLAY)
    assert any(r.unsupported_visible_content and 'text_shape_surface' in ''.join(r.notes)
               for r in unknown)
    assert not any(r.unsupported_visible_content for r in parse_pptx_shapes(DEMO))


def test_prebody_rejections_have_security_headers(tmp_path):
    store = SessionStore(tmp_path/'sessions', per_owner_sessions=1)
    with patch.object(main, 'STORE', store):
        with TestClient(main.app) as client:
            ok = client.post('/api/demo')
            assert ok.status_code == 200
            rejected = client.post('/api/upload', content=b'', headers={'content-type': 'application/octet-stream'})
            assert rejected.status_code == 429, rejected.text
            large = client.post('/api/upload', content=b'', headers={'content-length': str(24 * 1024 * 1024)})
            assert large.status_code in (413, 429)
            for r in (ok, rejected, large):
                assert r.headers.get('content-security-policy')
                assert r.headers.get('referrer-policy') == 'no-referrer'
                assert r.headers.get('x-frame-options') == 'DENY'
                assert r.headers.get('x-content-type-options') == 'nosniff'
            # Fresh owner tests the body-size branch instead of quota handling.
            fresh = TestClient(main.app)
            with patch.object(main, '_client_owner_key', return_value='different-owner'):
                too_big = fresh.post('/api/upload', content=b'',
                                     headers={'content-length': str(24 * 1024 * 1024)})
                assert too_big.status_code == 413, too_big.text
                for name in ('content-security-policy', 'referrer-policy', 'x-frame-options'):
                    assert too_big.headers.get(name), too_big.headers
            key = ok.json()
            assert client.delete('/api/sessions/'+key['session_id'],
                                 headers={'X-Venue-Token': key['session_token']}).status_code == 200
    store.stop_reaper()


def test_expired_upload_body_releases_global_slot_and_responds_408(tmp_path):
    store = SessionStore(tmp_path/'sessions', max_parallel_intakes_global=1)
    async def downstream(scope, receive, send):
        await receive()
        await JSONResponse({'ok': True})(scope, receive, send)
    layer = main.EarlyUploadAdmissionMiddleware(downstream)
    layer.idle_seconds = 0.03
    layer.absolute_seconds = 0.09
    scope = {'type': 'http', 'path': '/api/upload', 'method':'POST',
             'client':('127.0.0.10', 41000), 'headers':[],
             'asgi': {'version':'3.0'}, 'http_version':'1.1', 'scheme':'http', 'root_path':'', 'server':('test',80)}
    async def exercise():
        sent = []
        async def never():
            await asyncio.Event().wait()
        async def send(msg): sent.append(msg)
        await layer(scope, never, send)
        assert sent[0]['status'] == 408
        assert store._pending_intakes == {}
        sent.clear()
        async def complete():
            return {'type':'http.request', 'body':b'', 'more_body':False}
        await layer(scope, complete, send)
        assert sent[0]['status'] == 200
        assert store._pending_intakes == {}
    with patch.object(main, 'STORE', store):
        asyncio.run(exercise())
    store.stop_reaper()


def test_untrusted_proxy_cannot_spoof_owner_and_trusted_chain_uses_nearest_untrusted(monkeypatch):
    def req(xff):
        return Request({'type':'http', 'method':'POST', 'path':'/api/demo',
                        'client':('10.0.0.2',1234), 'headers':[(b'x-forwarded-for', xff.encode())]})
    monkeypatch.delenv('VENUE_TRUSTED_PROXY_IPS', raising=False)
    assert main._client_owner_key(req('1.2.3.4')) == main._client_owner_key(req('8.8.8.8'))
    monkeypatch.setenv('VENUE_TRUSTED_PROXY_IPS', '10.0.0.0/24')
    assert main._client_owner_key(req('1.1.1.1, 8.8.8.8')) == main._client_owner_key(req('8.8.8.8'))
    assert main._client_owner_key(req('1.1.1.1, 8.8.8.8')) != main._client_owner_key(req('1.1.1.1, 9.9.9.9'))
    monkeypatch.setenv('VENUE_TRUSTED_PROXY_IPS', '')


@pytest.mark.resource
def test_outlined_textbox_never_reaches_verified_during_authenticated_roundtrip():
    with TestClient(main.app) as client:
        with OVERLAY.open('rb') as f:
            uploaded = client.post('/api/upload', files={'file':('mask.pptx', f)})
        assert uploaded.status_code == 200, uploaded.text
        sid = uploaded.json()['session_id']
        auth = {'X-Venue-Token':uploaded.json()['session_token']}
        try:
            analyzed = client.post(f'/api/sessions/{sid}/analyze', headers=auth, json={'venue':VENUE})
            assert analyzed.status_code == 200, analyzed.text
            assert analyzed.json()['analysis']['summary']['unsupported_visible_content_elements'] >= 1
            if analyzed.json()['state'] != 'ANALYZED':
                assert analyzed.json()['state'] == 'REVIEW_REQUIRED'
                return
            planned = client.post(f'/api/sessions/{sid}/plan', headers=auth, json={'constraints':CONSTRAINTS})
            assert planned.status_code == 200, planned.text
            if planned.json()['state'] == 'AWAITING_APPROVAL':
                result = client.post(f'/api/sessions/{sid}/approve-and-apply', headers=auth,
                    json={'candidate_ids':planned.json()['decision']['selected_candidate_ids'],
                          'plan_hash':planned.json()['plan_hash'], 'idempotency_key':'r7-outline-test', 'approve':True})
                assert result.status_code == 200, result.text
                assert result.json()['state'] == 'REVIEW_REQUIRED'
            else:
                assert planned.json()['state'] in ('REVIEW_REQUIRED','NO_FEASIBLE_PLAN')
        finally:
            client.delete(f'/api/sessions/{sid}', headers=auth)


@pytest.mark.resource
def test_authenticated_plan_recovery_after_refresh_and_stale_invalidation():
    with TestClient(main.app) as client:
        created = client.post('/api/demo').json()
        sid = created['session_id']
        auth = {'X-Venue-Token': created['session_token']}
        try:
            assert client.get(f'/api/sessions/{sid}').status_code == 404
            analysis = client.post(f'/api/sessions/{sid}/analyze', headers=auth, json={'venue':VENUE})
            assert analysis.status_code == 200, analysis.text
            planned = client.post(f'/api/sessions/{sid}/plan', headers=auth, json={'constraints':CONSTRAINTS})
            assert planned.status_code == 200, planned.text
            if planned.json()['state'] != 'AWAITING_APPROVAL':
                pytest.fail(f'Unexpected demo plan state: {planned.json()["state"]}')
            recovery = client.get(f'/api/sessions/{sid}', headers=auth)
            assert recovery.status_code == 200, recovery.text
            pending = recovery.json()['pending_plan']
            assert pending and pending['plan_hash'] == planned.json()['plan_hash']
            assert pending['candidate_ids'] == planned.json()['decision']['selected_candidate_ids']
            assert pending['plan_simulation']['safe'] is True
            assert not client.get(f'/api/sessions/{sid}', headers={'X-Venue-Token':'invalid'}).status_code == 200
            # Reanalysis makes a recovered-but-not-yet-approved plan stale.
            renewed = client.post(f'/api/sessions/{sid}/analyze', headers=auth, json={'venue':VENUE})
            assert renewed.status_code == 200, renewed.text
            assert client.get(f'/api/sessions/{sid}', headers=auth).json()['pending_plan'] is None
            stale = client.post(f'/api/sessions/{sid}/approve-and-apply', headers=auth,
                json={'candidate_ids':pending['candidate_ids'], 'plan_hash':pending['plan_hash'],
                      'idempotency_key':'r7-stale', 'approve':True})
            assert stale.status_code == 409
        finally:
            client.delete(f'/api/sessions/{sid}', headers=auth)
