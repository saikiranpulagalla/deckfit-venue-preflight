from pathlib import Path
import hashlib
import os
import threading
import time

import pytest
from unittest.mock import patch

from app.storage.sessions import ROOT_MARKER, SESSION_MARKER, SessionStore


class Clock:
    def __init__(self, now: float = 1000.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_session_expires_and_artifacts_are_deleted(tmp_path: Path):
    clock = Clock()
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2, clock=clock)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    assert s.root.exists()
    clock.now += 61
    with pytest.raises(KeyError):
        store.get(s.session_id)
    assert not s.root.exists()


def test_capacity_is_bounded_but_expired_sessions_free_space(tmp_path: Path):
    clock = Clock()
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2, clock=clock)
    s1 = store.create("a.pptx", b"a", digest(b"a"))
    store.create("b.pptx", b"b", digest(b"b"))
    with pytest.raises(RuntimeError, match="session_capacity_reached"):
        store.create("c.pptx", b"c", digest(b"c"))
    clock.now += 61
    s3 = store.create("c.pptx", b"c", digest(b"c"))
    assert s3.root.exists()
    assert not s1.root.exists()


def test_explicit_delete_removes_artifacts(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    assert store.delete(s.session_id) is True
    assert not s.root.exists()
    assert store.delete(s.session_id) is False


def test_startup_clears_only_owned_orphaned_session_directories(tmp_path: Path):
    base = tmp_path / "sessions"
    first = SessionStore(base, ttl_seconds=60, max_sessions=2)
    s = first.create("demo.pptx", b"secret", digest(b"secret"))
    unrelated = base / "DO_NOT_DELETE.txt"
    unrelated.write_text("operator data")
    unrelated_dir = base / "unrelated-folder"
    unrelated_dir.mkdir()
    (unrelated_dir / "data.txt").write_text("keep")

    first.stop_reaper()  # Simulate previous process shutdown before startup sweep.
    SessionStore(base, ttl_seconds=60, max_sessions=2, clear_orphans_on_start=True)

    assert not s.root.exists()
    assert unrelated.read_text() == "operator data"
    assert (unrelated_dir / "data.txt").read_text() == "keep"
    assert (base / ROOT_MARKER).exists()


def test_nonempty_unowned_session_root_is_rejected(tmp_path: Path):
    base = tmp_path / "sessions"
    base.mkdir()
    (base / "DO_NOT_DELETE.txt").write_text("operator data")
    with pytest.raises(RuntimeError, match="session_root_not_owned_by_venue_agent"):
        SessionStore(base, ttl_seconds=60, max_sessions=2)
    assert (base / "DO_NOT_DELETE.txt").read_text() == "operator data"


def test_clear_derived_state_invalidates_plan_and_removes_output(tmp_path: Path):
    from app.domain.models import RepairConstraints, WorkflowState

    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    output = s.root / "output.pptx"
    output.write_bytes(b"old-output")
    s.output_path = output
    s.selected_candidate_ids = ["candidate-1"]
    s.selected_constraints = RepairConstraints()
    s.plan_hash = "old-plan"
    s.approved_plan_hash = "old-plan"
    s.state = WorkflowState.VERIFIED

    s.clear_derived_state(remove_output=True)

    assert s.candidates == []
    assert s.selected_candidate_ids == []
    assert s.selected_constraints is None
    assert s.plan_simulation is None
    assert s.plan_hash is None
    assert s.approved_plan_hash is None
    assert s.output_path is None
    assert not output.exists()


def test_locked_serializes_same_session(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first():
        with store.locked(s.session_id):
            first_entered.set()
            assert release_first.wait(timeout=2)

    def second():
        assert first_entered.wait(timeout=2)
        with store.locked(s.session_id):
            second_entered.set()

    t1 = threading.Thread(target=first)
    t2 = threading.Thread(target=second)
    t1.start(); t2.start()
    assert first_entered.wait(timeout=2)
    time.sleep(0.05)
    assert not second_entered.is_set()
    release_first.set()
    t1.join(timeout=2); t2.join(timeout=2)
    assert not t1.is_alive() and not t2.is_alive()
    assert second_entered.is_set()


def test_waiting_on_one_session_does_not_block_unrelated_session(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=3)
    a = store.create("a.pptx", b"a", digest(b"a"))
    b = store.create("b.pptx", b"b", digest(b"b"))
    entered_a = threading.Event()
    release_a = threading.Event()
    waiter_started = threading.Event()

    def hold_a():
        with store.locked(a.session_id):
            entered_a.set()
            assert release_a.wait(timeout=2)

    def wait_a():
        assert entered_a.wait(timeout=2)
        waiter_started.set()
        with store.locked(a.session_id):
            pass

    t1 = threading.Thread(target=hold_a); t2 = threading.Thread(target=wait_a)
    t1.start(); t2.start()
    assert waiter_started.wait(timeout=2)
    time.sleep(0.05)
    start = time.monotonic()
    with store.locked(b.session_id):
        elapsed = time.monotonic() - start
    assert elapsed < 0.15, f"unrelated session was convoyed for {elapsed:.3f}s"
    release_a.set()
    t1.join(timeout=2); t2.join(timeout=2)


def test_restart_clears_verified_output_and_stale_session_identity(tmp_path: Path):
    from app.domain.models import WorkflowState

    base = tmp_path / "sessions"
    first = SessionStore(base, ttl_seconds=60, max_sessions=2)
    s = first.create("demo.pptx", b"abc", digest(b"abc"))
    output = s.root / "output.pptx"
    output.write_bytes(b"verified-copy")
    s.output_path = output
    s.state = WorkflowState.VERIFIED
    sid = s.session_id

    first.stop_reaper()
    restarted = SessionStore(base, ttl_seconds=60, max_sessions=2, clear_orphans_on_start=True)

    assert not s.root.exists()
    with pytest.raises(KeyError):
        restarted.get(sid)


def test_operation_lease_refreshes_idle_ttl_even_when_waiting(tmp_path: Path):
    clock = Clock()
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2, clock=clock)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    entered: list[str] = []

    s.lock.acquire()
    try:
        def waiter():
            with store.locked(s.session_id) as live:
                entered.append("entered")
                assert live.expires_at > clock.now

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        clock.now = s.expires_at + 10
    finally:
        s.lock.release()

    t.join(timeout=2)
    assert not t.is_alive()
    assert entered == ["entered"]
    assert store.get(s.session_id).expires_at > clock.now


def test_proactive_reaper_deletes_idle_expired_artifacts_without_new_request(tmp_path: Path):
    clock = Clock()
    store = SessionStore(
        tmp_path / "sessions",
        ttl_seconds=60,
        max_sessions=2,
        clock=clock,
        reaper_interval_seconds=0.01,
    )
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    store.start_reaper()
    try:
        clock.now = s.expires_at + 1
        deadline = time.monotonic() + 1.0
        while s.root.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not s.root.exists()
        with pytest.raises(KeyError):
            store.get(s.session_id)
    finally:
        store.stop_reaper()


def test_session_capability_is_separate_and_server_side_hash_is_authoritative(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    token = s.take_issued_capability_token()
    assert token not in s.session_id
    assert token != s.capability_hash
    assert store.authorize(s.session_id, token) is True
    assert store.authorize(s.session_id, token + "x") is False
    assert s._issued_capability_token is None


def test_session_artifacts_use_private_permissions(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2)
    s = store.create("demo.pptx", b"abc", digest(b"abc"))
    if os.name == "posix":
        assert (os.stat(store.base).st_mode & 0o777) == 0o700
        assert (os.stat(s.root).st_mode & 0o777) == 0o700
        assert (os.stat(s.source_path).st_mode & 0o777) == 0o600
    else:
        # Windows chmod mode bits are not an ACL security oracle. Keep the
        # portable checks active: artifacts remain inside the owned root and
        # access requires the separate server-side capability.
        token = s.take_issued_capability_token()
        assert s.source_path.parent == s.root
        assert store.authorize(s.session_id, token)
    assert (s.root / SESSION_MARKER).exists()


def test_expiry_cleanup_failure_revokes_access_and_retries(tmp_path: Path):
    clock = Clock()
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2, clock=clock)
    s = store.create("demo.pptx", b"private", digest(b"private"))
    token = s.take_issued_capability_token()
    clock.now += 61
    with patch("app.storage.sessions.shutil.rmtree", return_value=None):
        assert store.cleanup_expired() == 0
    assert s.root.exists()
    assert s.session_id in store._items
    assert s.cleanup_pending and s.expired
    assert not store.authorize(s.session_id, token)
    with pytest.raises(KeyError):
        store.get(s.session_id)
    assert store.retry_pending_deletions() == 1
    assert not s.root.exists()
    assert s.session_id not in store._items


def test_expiry_cleanup_oserror_is_retryable(tmp_path: Path):
    clock = Clock()
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, max_sessions=2, clock=clock)
    s = store.create("demo.pptx", b"private", digest(b"private"))
    clock.now += 61
    with patch("app.storage.sessions.shutil.rmtree", side_effect=PermissionError("locked")):
        assert store.cleanup_expired() == 0
    assert s.root.exists() and s.cleanup_pending and s.expired
    assert store.retry_pending_deletions() == 1
    assert not s.root.exists()


def test_startup_cleanup_failure_stays_owned_and_retries_in_process(tmp_path: Path):
    base = tmp_path / "sessions"
    first = SessionStore(base, ttl_seconds=60, max_sessions=2)
    s = first.create("demo.pptx", b"private", digest(b"private"))
    first.stop_reaper()
    with patch("app.storage.sessions.shutil.rmtree", side_effect=PermissionError("locked")):
        restarted = SessionStore(base, ttl_seconds=60, max_sessions=2, clear_orphans_on_start=True)
    assert s.root.exists()
    assert s.root in restarted._startup_cleanup_pending
    assert restarted.retry_startup_cleanup() == 1
    assert not s.root.exists()


def test_clear_plan_state_clears_verified_output_digest_when_output_removed(tmp_path):
    store = SessionStore(tmp_path / "sessions", ttl_seconds=60, clear_orphans_on_start=False)
    s = store.create("a.pptx", b"pptx", "digest")
    s.take_issued_capability_token()
    output = s.root / "output.pptx"
    output.write_bytes(b"verified")
    s.output_path = output
    s.output_sha256 = "abc123"
    s.clear_plan_state(remove_output=True)
    assert s.output_path is None
    assert s.output_sha256 is None
    assert not output.exists()
