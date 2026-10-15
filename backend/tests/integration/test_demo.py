from fastapi.testclient import TestClient
from app.main import app


def test_demo_and_homepage():
    with TestClient(app) as c:
        r = c.post('/api/demo')
        assert r.status_code == 200, r.text
        assert r.json()['state'] == 'UPLOADED'
        h = c.get('/')
        assert h.status_code == 200
        assert 'Prepare your slides for the actual room' in h.text
        assert 'Active image height' in h.text
        assert 'Target structural coverage' in h.text
        assert 'Reject plan' in h.text
        assert 'Unrepairable issues stay visible' in h.text
        assert 'Candidate tradeoffs' in h.text
        assert 'Titles never auto-mutate' in h.text
        assert 'Structural coverage' in h.text
        assert 'installNewSession' in h.text
        assert 'analysis universe preserved' in h.text
        assert 'sessionStorage' in h.text
        assert 'X-Venue-Token' in h.text
        assert 'restoreSession' in h.text
        assert 'downloadOutput' in h.text


def test_demo_session_can_be_explicitly_deleted():
    with TestClient(app) as c:
        r = c.post('/api/demo')
        assert r.status_code == 200
        sid = r.json()['session_id']
        headers = {'X-Venue-Token': r.json()['session_token']}
        d = c.delete(f'/api/sessions/{sid}', headers=headers)
        assert d.status_code == 200
        assert d.json() == {'deleted': True}
        again = c.delete(f'/api/sessions/{sid}', headers=headers)
        assert again.status_code == 404
