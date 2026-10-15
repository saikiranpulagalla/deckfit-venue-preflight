"""R8 release-blocking exploit regressions and utility/availability controls."""
import shutil
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from app import main
from app.pptx.parser import parse_pptx_shapes, map_elements
from app.pptx.renderer import render_pptx_to_pdf
from app.security.intake import IntakeError, validate_pptx
from app.storage import sessions

FIX = Path(__file__).resolve().parents[1] / 'fixtures' / 'r8'
VENUE = {'active_image_height_m':1.8, 'farthest_viewer_distance_m':10.8, 'measurement_basis':'MEASURED'}
CONSTRAINTS = {'max_mutations':2,'max_scale_factor':1.6,'minimum_target_coverage':0.9,'protect_titles':True,'semantic_rewrite':False}


def test_theme_style_is_inventory_unknown_and_normal_demo_remains_text_only():
    visual = parse_pptx_shapes(FIX / 'theme-default-overlay.pptx')
    assert any(r.unsupported_visible_content and 'surface' in str(r.notes) for r in visual)
    themed = next(r for r in visual if r.text == 'MASK')
    assert themed.mutation_capability.name != 'SAFE_MUTATION'
    demo = parse_pptx_shapes(Path(__file__).resolve().parents[3] / 'demo' / 'venue-agent-demo.pptx')
    assert not any(r.unsupported_visible_content for r in demo)


@pytest.mark.parametrize('name', ['corrupt-content-types.pptx','corrupt-media-crc.pptx','corrupt-slide-deflate.pptx'])
def test_corrupt_packages_fail_during_intake_not_after_allocation(name):
    with pytest.raises(IntakeError):
        validate_pptx(FIX / name)


def test_all_r8_readable_powerpoints_are_accepted():
    for name in ['theme-default-overlay.pptx','hidden-middle-visible-last.pptx','hidden-slide-image.pptx']:
        assert validate_pptx(FIX / name).slide_count >= 1


def test_delete_failure_is_not_acknowledged_and_is_retryable(tmp_path):
    store = sessions.SessionStore(tmp_path/'sessions', max_sessions=2, clear_orphans_on_start=False)
    obj=store.create('x.pptx',b'private bytes','sha',owner_key='o')
    token=obj.take_issued_capability_token()
    with patch('app.storage.sessions.shutil.rmtree',return_value=None):
        with pytest.raises(sessions.SessionCleanupError):
            store.delete(obj.session_id)
    assert obj.source_path.exists()
    assert store.authorize(obj.session_id,token)
    with pytest.raises(KeyError):
        with store.locked(obj.session_id):
            pass
    assert store.delete(obj.session_id) is True
    assert not obj.root.exists()
    assert not store.authorize(obj.session_id,token)


def test_pending_explicit_deletion_is_retried_by_reaper(tmp_path):
    store=sessions.SessionStore(tmp_path/'sessions',max_sessions=2)
    item=store.create('x.pptx',b'private','digest',owner_key='A')
    with patch('app.storage.sessions.shutil.rmtree',return_value=None):
        with pytest.raises(sessions.SessionCleanupError):
            store.delete(item.session_id)
    assert item.root.exists()
    assert store.retry_pending_deletions()==1
    assert not item.root.exists()
    assert item.session_id not in store._items


def test_disk_stall_cannot_convoy_unrelated_session(tmp_path):
    store=sessions.SessionStore(tmp_path/'sessions',max_sessions=5,per_owner_sessions=5)
    first=store.create('a.pptx', b'a','a',owner_key='A')
    token=first.take_issued_capability_token()
    started=threading.Event(); release=threading.Event(); auth_done=threading.Event();errors=[]
    original=sessions._secure_write
    def slow_write(path,content):
        if path.name=='source.pptx' and content==b'b':
            started.set()
            if not release.wait(3):
                raise RuntimeError('unexpected_test_timeout')
        return original(path,content)
    def create_second():
        try:store.create('b.pptx',b'b','b',owner_key='B')
        except Exception as exc:errors.append(exc)
    with patch('app.storage.sessions._secure_write',side_effect=slow_write):
        worker=threading.Thread(target=create_second);worker.start()
        assert started.wait(2)
        probe=threading.Thread(target=lambda:(store.authorize(first.session_id,token) and auth_done.set()))
        probe.start()
        try:assert auth_done.wait(0.3),'unrelated session was blocked by filesystem IO'
        finally:release.set();worker.join(5);probe.join(5)
    assert not errors


def test_parallel_creates_reserve_capacity_and_rollback(tmp_path):
    store=sessions.SessionStore(tmp_path/'store',max_sessions=1,per_owner_sessions=1)
    started=threading.Event();release=threading.Event();original=sessions._secure_write
    def delay(path,content):
        if path.name=='source.pptx':
            started.set();release.wait(3)
        return original(path,content)
    results=[]
    with patch('app.storage.sessions._secure_write',side_effect=delay):
        worker=threading.Thread(target=lambda:results.append(store.create('a',b'a','sha',owner_key='one')))
        worker.start();assert started.wait(2)
        with pytest.raises(RuntimeError,match='session_capacity_reached'):
            store.create('b',b'b','sha',owner_key='two')
        release.set();worker.join(5)
    assert len(results)==1 and len(store._items)==1 and not store._pending_creates


def test_failed_disk_write_does_not_leak_capacity_or_dir(tmp_path):
    store=sessions.SessionStore(tmp_path/'store', max_sessions=1)
    original=sessions._secure_write
    def fail(path, content):
        if path.name=='source.pptx':raise OSError('disk full')
        return original(path,content)
    with patch('app.storage.sessions._secure_write',side_effect=fail):
        with pytest.raises(OSError):store.create('a',b'a','sha',owner_key='A')
    assert not store._items and not store._pending_creates
    assert not list(store.base.glob('session-*'))
    assert store.create('b',b'b','sha',owner_key='B')


def test_failed_explicit_delete_http_is_retryable(monkeypatch):
    with TestClient(main.app) as client:
        item=client.post('/api/demo').json();sid=item['session_id']; auth={'X-Venue-Token':item['session_token']}
        original=shutil.rmtree
        with patch('app.storage.sessions.shutil.rmtree',return_value=None):
            rejected=client.delete(f'/api/sessions/{sid}',headers=auth)
        assert rejected.status_code == 503
        assert client.delete(f'/api/sessions/{sid}',headers=auth).status_code == 200
        assert client.get(f'/api/sessions/{sid}',headers=auth).status_code == 404


@pytest.mark.resource
def test_theme_styled_overlay_cannot_verify_via_public_api():
    with TestClient(main.app) as client:
        with (FIX/'theme-default-overlay.pptx').open('rb') as f:
            response=client.post('/api/upload',files={'file':('theme.pptx',f)})
        assert response.status_code == 200,response.text
        item=response.json();sid=item['session_id'];auth={'X-Venue-Token':item['session_token']}
        try:
            analyze=client.post(f'/api/sessions/{sid}/analyze',headers=auth,json={'venue':VENUE})
            assert analyze.status_code == 200,analyze.text
            assert analyze.json()['analysis']['summary']['unsupported_visible_content_elements']>=1
            plan=client.post(f'/api/sessions/{sid}/plan',headers=auth,json={'constraints':CONSTRAINTS})
            assert plan.status_code == 200,plan.text
            if plan.json()['state']=='AWAITING_APPROVAL':
                approval=client.post(f'/api/sessions/{sid}/approve-and-apply',headers=auth,json={'candidate_ids':plan.json()['decision']['selected_candidate_ids'],'plan_hash':plan.json()['plan_hash'],'idempotency_key':'r8-theme','approve':True})
                assert approval.status_code==200,approval.text
                assert approval.json()['state']!='VERIFIED'
        finally:client.delete(f'/api/sessions/{sid}',headers=auth)


@pytest.mark.resource
def test_hidden_middle_slide_maps_visible_last_slide(tmp_path):
    source=FIX/'hidden-middle-visible-last.pptx'
    pdf=render_pptx_to_pdf(source,tmp_path/'render')
    mapped=map_elements(source,pdf)
    third=[x for x in mapped if x.slide_index==2 and 'FINAL VISIBLE SLIDE TEXT' in x.source_text]
    assert len(third)==1 and third[0].rendered_span_count>=1
    assert not any(x.slide_index==1 for x in mapped)


@pytest.mark.resource
def test_hidden_image_is_not_reported_as_visible_unknown(tmp_path):
    source=FIX/'hidden-slide-image.pptx'
    pdf=render_pptx_to_pdf(source,tmp_path/'render')
    mapped=map_elements(source,pdf)
    assert not any(x.slide_index==1 for x in mapped)
    assert not any('page_count_mismatch' in x.notes for x in mapped)
