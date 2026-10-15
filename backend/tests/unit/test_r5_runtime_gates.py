import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app import main
from app.pptx.renderer import RenderError
from app.storage.sessions import SessionStore


def test_deep_readiness_does_not_cache_stale_success(monkeypatch):
    monkeypatch.setattr(main, "_READINESS_LAST_PROBE_AT", 0.0)
    monkeypatch.setattr(main, "_READINESS_LAST_SUCCESS_AT", 0.0)
    monkeypatch.setattr(main, "_READINESS_LAST_RESULT", False)
    monkeypatch.setattr(main, "_READINESS_PROBE_TTL_S", 60.0)
    monkeypatch.setattr(main, "_READINESS_SUCCESS_GRACE_S", 900.0)
    clock = [1000.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    status = ["ok"]

    def render(*args, **kwargs):
        if status[0] == "bad":
            raise RenderError("broken")
        class PDF:
            def exists(self): return True
            def stat(self):
                class S: st_size = 100
                return S()
        return PDF()
    monkeypatch.setattr(main, "render_pptx_to_pdf", render)
    assert main._deep_renderer_readiness()[0] is True
    clock[0] += 61
    status[0] = "bad"
    assert main._deep_renderer_readiness()[0] is False
    clock[0] += 1
    assert main._deep_renderer_readiness()[0] is False


def test_session_limit_per_client_and_release_on_delete(tmp_path):
    store = SessionStore(tmp_path / "sessions", max_sessions=24, per_owner_sessions=2,
                         clear_orphans_on_start=False)
    s1 = store.create("a.pptx", b"a", "1", owner_key="one")
    s2 = store.create("b.pptx", b"b", "2", owner_key="one")
    with pytest.raises(RuntimeError, match="client_session_capacity_reached"):
        store.create("c.pptx", b"c", "3", owner_key="one")
    third = store.create("c.pptx", b"c", "3", owner_key="two")
    assert third.session_id
    store.delete(s1.session_id)
    fourth = store.create("d.pptx", b"d", "4", owner_key="one")
    assert fourth.session_id


def test_spoofed_forwarded_header_does_not_bypass_peer_quota(monkeypatch, tmp_path):
    store = SessionStore(tmp_path / "sessions", max_sessions=24, per_owner_sessions=2)
    monkeypatch.setattr(main, "STORE", store)
    monkeypatch.delenv("VENUE_TRUSTED_PROXY_IPS", raising=False)
    with TestClient(main.app) as c:
        for n in range(2):
            r = c.post("/api/demo", headers={"X-Forwarded-For": f"192.0.2.{n+1}"})
            assert r.status_code == 200, r.text
        r = c.post("/api/demo", headers={"X-Forwarded-For": "192.0.2.199"})
        assert r.status_code == 429, r.text
    store.stop_reaper()
