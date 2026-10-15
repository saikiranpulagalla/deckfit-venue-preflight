from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import logging
import os
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager

from app.domain.models import AnalysisResult, PlanDecision, PlanSimulationReport, RepairCandidate, RepairConstraints, WorkflowState, VenueProfile


LOGGER = logging.getLogger(__name__)

ROOT_MARKER = ".venue-agent-session-root-v1"
SESSION_MARKER = ".venue-agent-session-v1"
SESSION_DIR_PREFIX = "session-"
INSTANCE_LOCK = ".venue-agent-instance.lock"


class SessionBusy(RuntimeError):
    """A bounded, retryable per-session admission or lock wait rejection."""


class SessionCleanupError(OSError):
    """Private artifacts were not confirmed deleted; retain retry authority."""


def _capability_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _secure_mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _secure_write(path: Path, content: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    finally:
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


@dataclass
class Session:
    session_id: str
    root: Path
    source_path: Path
    source_sha256: str
    capability_hash: str = ""
    owner_key: str = ""
    created_at: float = 0.0
    last_activity_at: float = 0.0
    expires_at: float = 0.0
    monotonic_expires_at: float = 0.0
    state: WorkflowState = WorkflowState.UPLOADED
    analysis: AnalysisResult | None = None
    candidates: list[RepairCandidate] = field(default_factory=list)
    selected_candidate_ids: list[str] = field(default_factory=list)
    selected_constraints: RepairConstraints | None = None
    plan_simulation: PlanSimulationReport | None = None
    plan_decision: PlanDecision | None = None
    plan_hash: str | None = None
    analysis_revision: int = 0
    plan_nonce: str = ""
    first_authenticated_at: float | None = None
    approved_plan_hash: str | None = None
    used_idempotency_keys: set[str] = field(default_factory=set)
    output_path: Path | None = None
    output_sha256: str | None = None
    output_venue: VenueProfile | None = None
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False, compare=False)
    active_operations: int = 0
    delete_requested: bool = False
    cleanup_pending: bool = False
    # Expiry revokes external authority even if a filesystem retry is pending.
    expired: bool = False
    _issued_capability_token: str | None = field(default=None, repr=False, compare=False)

    def take_issued_capability_token(self) -> str:
        token = self._issued_capability_token
        if not token:
            raise RuntimeError("capability_token_already_consumed")
        self._issued_capability_token = None
        return token

    def clear_plan_state(self, *, remove_output: bool = False) -> None:
        self.selected_candidate_ids = []
        self.selected_constraints = None
        self.plan_simulation = None
        self.plan_decision = None
        self.plan_hash = None
        self.plan_nonce = ""
        self.approved_plan_hash = None
        if remove_output:
            if self.output_path is not None:
                self.output_path.unlink(missing_ok=True)
            (self.root / "output.pptx").unlink(missing_ok=True)
            self.output_path = None
            self.output_sha256 = None
            self.output_venue = None

    def clear_derived_state(self, *, remove_output: bool = False) -> None:
        self.candidates = []
        self.clear_plan_state(remove_output=remove_output)

    def _candidate_snapshot(self, candidate_ids: list[str]) -> list[dict]:
        by_id = {c.candidate_id: c for c in self.candidates}
        rows: list[dict] = []
        for cid in candidate_ids:
            c = by_id.get(cid)
            if c is None:
                raise ValueError(f"candidate_missing_from_snapshot:{cid}")
            rows.append({
                "candidate_id": c.candidate_id,
                "issue_element_id": c.issue_element_id,
                "operation": c.operation,
                "parameters": c.parameters,
                "predicted_state": c.predicted_state,
                "safe": c.safe,
                "actual_percent_before": c.actual_percent_before,
                "actual_percent_after": c.actual_percent_after,
                "issue_role": c.issue_role,
                "simulation_fingerprint": c.simulation_fingerprint,
            })
        return rows

    def compute_plan_hash(
        self,
        candidate_ids: list[str],
        constraints: RepairConstraints,
        plan_simulation: PlanSimulationReport | None = None,
    ) -> str:
        sim = plan_simulation if plan_simulation is not None else self.plan_simulation
        sim_snapshot = sim.model_dump(mode="json") if sim is not None else None
        payload = json.dumps({
            "source_sha256": self.source_sha256,
            "analysis_revision": self.analysis_revision,
            "plan_nonce": self.plan_nonce,
            "candidate_ids": candidate_ids,
            "candidate_snapshot": self._candidate_snapshot(candidate_ids),
            "constraints": constraints.model_dump(mode="json"),
            "plan_simulation": sim_snapshot,
        }, sort_keys=True, separators=(",", ":"), default=str).encode()
        return hashlib.sha256(payload).hexdigest()


class SessionStore:
    def __init__(
        self,
        base: Path,
        *,
        ttl_seconds: int = 45 * 60,
        max_sessions: int = 24,
        per_owner_sessions: int = 8,
        max_waiters_per_session: int = 4,
        lock_wait_timeout_seconds: float = 5.0,
        max_parallel_intakes_per_owner: int = 2,
        max_parallel_intakes_global: int = 6,
        clock: Callable[[], float] = time.time,
        clear_orphans_on_start: bool = True,
        reaper_interval_seconds: float | None = None,
        provisional_ttl_seconds: int = 300,
    ):
        if ttl_seconds < 60:
            raise ValueError("ttl_seconds must be at least 60")
        if max_sessions < 1:
            raise ValueError("max_sessions must be positive")
        if per_owner_sessions < 1:
            raise ValueError("per_owner_sessions must be positive")
        if max_waiters_per_session < 0 or lock_wait_timeout_seconds <= 0:
            raise ValueError("Invalid session lock admission limits")
        if max_parallel_intakes_per_owner < 1 or max_parallel_intakes_global < 1:
            raise ValueError("Invalid intake admission limits")
        self.base = base
        self.ttl_seconds = ttl_seconds
        self.provisional_ttl_seconds = min(ttl_seconds, max(60, provisional_ttl_seconds))
        self.max_sessions = max_sessions
        self.per_owner_sessions = per_owner_sessions
        self.max_waiters_per_session = max_waiters_per_session
        self.lock_wait_timeout_seconds = lock_wait_timeout_seconds
        self.max_parallel_intakes_per_owner = max_parallel_intakes_per_owner
        self.max_parallel_intakes_global = max_parallel_intakes_global
        self._pending_intakes: dict[str, int] = {}
        self._clock = clock
        self._elapsed_clock = time.monotonic if clock is time.time else clock
        self._items: dict[str, Session] = {}
        # Includes allocations whose private filesystem write is in progress.
        # Protects quotas without holding the global mutex during blocking IO.
        self._pending_creates: dict[str, int] = {}
        self._lock = threading.Lock()
        self._reaper_interval_seconds = reaper_interval_seconds
        self._reaper_stop = threading.Event()
        self._reaper_thread: threading.Thread | None = None
        # Owned roots that survived a failed startup sweep are inaccessible
        # (there is no restored session), but retained for bounded in-process
        # retry rather than being forgotten until another restart.
        self._startup_cleanup_pending: set[Path] = set()
        self.cleanup_failures = 0
        self._instance_lock_fd: int | None = None
        self._prepare_base(clear_orphans_on_start=clear_orphans_on_start)

    def _prepare_base(self, *, clear_orphans_on_start: bool) -> None:
        if self.base.exists() and not self.base.is_dir():
            raise RuntimeError("session_root_must_be_directory")
        _secure_mkdir(self.base)
        marker = self.base / ROOT_MARKER
        existing = [p for p in self.base.iterdir() if p.name not in {ROOT_MARKER, INSTANCE_LOCK}]
        if not marker.exists():
            if existing:
                raise RuntimeError("session_root_not_owned_by_venue_agent")
            _secure_write(marker, b"venue-agent-session-root-v1\n")
        else:
            try:
                if marker.read_text(encoding="utf-8").strip() != "venue-agent-session-root-v1":
                    raise RuntimeError("session_root_marker_invalid")
            except OSError as e:
                raise RuntimeError("session_root_marker_unreadable") from e
        # Exclusivity is required *before* orphan cleanup. OS locks are
        # automatically released on process death, permitting crash recovery.
        self._acquire_instance_lock()
        if clear_orphans_on_start:
            for child in list(self.base.iterdir()):
                if (
                    child.is_dir()
                    and child.name.startswith(SESSION_DIR_PREFIX)
                    and (child / SESSION_MARKER).is_file()
                ):
                    try:
                        self._remove_owned_root(child)
                    except SessionCleanupError:
                        # Leave the owned marker in place so the next restart
                        # and this process's reaper can retry rather than
                        # silently forgetting the data.
                        self._startup_cleanup_pending.add(child)
                        self.cleanup_failures += 1
                        continue

    def _acquire_instance_lock(self) -> None:
        if self._instance_lock_fd is not None:
            return
        fd = os.open(self.base / INSTANCE_LOCK, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            os.close(fd)
            raise RuntimeError("session_root_already_in_use") from exc
        self._instance_lock_fd = fd

    def start_reaper(self) -> None:
        # TestClient can restart lifespan on the same store. Reacquire
        # exclusive ownership before serving traffic after shutdown.
        self._acquire_instance_lock()
        interval = self._reaper_interval_seconds
        if interval is None:
            interval = max(5.0, min(30.0, self.ttl_seconds / 4.0))
        with self._lock:
            if self._reaper_thread is not None and self._reaper_thread.is_alive():
                return
            self._reaper_stop.clear()
            self._reaper_thread = threading.Thread(
                target=self._reaper_loop,
                args=(float(interval),),
                name="venue-session-reaper",
                daemon=True,
            )
            self._reaper_thread.start()

    def stop_reaper(self) -> None:
        self._reaper_stop.set()
        thread = self._reaper_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._reaper_thread = None
        self.release_instance_lock()

    def release_instance_lock(self) -> None:
        """Explicitly surrender root ownership on clean shutdown."""
        fd, self._instance_lock_fd = self._instance_lock_fd, None
        if fd is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def _reaper_loop(self, interval: float) -> None:
        while not self._reaper_stop.wait(interval):
            try:
                self.cleanup_expired()
                self.retry_pending_deletions()
                self.retry_startup_cleanup()
            except Exception as exc:
                # No file paths, tokens, or document content in operational logs.
                with self._lock:
                    self.cleanup_failures += 1
                LOGGER.warning("session_reaper_retry_failed:%s", type(exc).__name__)

    def _remove_owned_root(self, root: Path) -> None:
        """Delete only a direct, non-symlink child of the owned session root."""
        try:
            if root.parent.resolve() != self.base.resolve() or not root.name.startswith(SESSION_DIR_PREFIX):
                raise SessionCleanupError("unsafe_session_cleanup_target")
            if root.is_symlink():
                raise SessionCleanupError("refusing_session_root_symlink")
            if root.exists():
                shutil.rmtree(root)
            if root.exists():
                raise SessionCleanupError("session_artifacts_still_present")
        except OSError as exc:
            raise SessionCleanupError("session_cleanup_incomplete_retry") from exc

    def _collect_expired_locked(self) -> list[Session]:
        now = self._elapsed_clock()
        expired: list[Session] = []
        for s in self._items.values():
            if s.active_operations == 0 and not s.delete_requested and not s.cleanup_pending and now >= s.monotonic_expires_at:
                # Inaccessible immediately; keep the trusted root record until
                # physical deletion has been independently confirmed.
                s.expired = True
                s.delete_requested = True
                s.cleanup_pending = True
                expired.append(s)
        return expired

    def _finish_cleanup(self, session: Session) -> bool:
        try:
            with session.lock:
                self._remove_owned_root(session.root)
        except SessionCleanupError:
            with self._lock:
                if self._items.get(session.session_id) is session:
                    session.cleanup_pending = True
                    session.delete_requested = False
                    self.cleanup_failures += 1
            raise
        with self._lock:
            if self._items.get(session.session_id) is session:
                self._items.pop(session.session_id, None)
        return True

    def _remove_roots(self, sessions: list[Session]) -> None:
        """Best-effort expiry cleanup that never discards a failed retry record."""
        for session in sessions:
            try:
                self._finish_cleanup(session)
            except SessionCleanupError:
                continue

    def cleanup_expired(self) -> int:
        with self._lock:
            expired = self._collect_expired_locked()
        completed = 0
        for session in expired:
            try:
                completed += int(self._finish_cleanup(session))
            except SessionCleanupError:
                continue
        return completed

    def retry_pending_deletions(self) -> int:
        """Retry incomplete explicit cleanup on the periodic reaper cycle.

        Keep pending sessions tracked until their owned directory is absent.
        Never hold the global map mutex while performing filesystem removal.
        """
        with self._lock:
            pending = [obj for obj in self._items.values()
                       if obj.cleanup_pending and not obj.delete_requested]
            for obj in pending:
                obj.delete_requested = True
        completed = 0
        for obj in pending:
            try:
                completed += int(self._finish_cleanup(obj))
            except SessionCleanupError:
                continue
        return completed

    def retry_startup_cleanup(self) -> int:
        """Retry only roots discovered as owned during startup recovery."""
        pending = list(self._startup_cleanup_pending)
        completed = 0
        for root in pending:
            try:
                self._remove_owned_root(root)
            except SessionCleanupError:
                self.cleanup_failures += 1
                continue
            self._startup_cleanup_pending.discard(root)
            completed += 1
        return completed

    def begin_intake(self, owner_key: str) -> str | None:
        """Pre-body reservation; reap confirmed expired roots before counting.

        Physical cleanup cannot run while holding the map mutex. A pending
        removal keeps occupying a slot until deletion is actually confirmed.
        """
        self.cleanup_expired()
        with self._lock:
            roots = self._collect_expired_locked()
            owned = (sum(s.owner_key == owner_key for s in self._items.values())
                     + self._pending_creates.get(owner_key, 0))
            pending = self._pending_intakes.get(owner_key, 0)
            if owned + pending >= self.per_owner_sessions:
                reason = "client_session_capacity_reached"
            elif len(self._items) + sum(self._pending_intakes.values()) + sum(self._pending_creates.values()) >= self.max_sessions:
                reason = "session_capacity_reached"
            elif pending >= self.max_parallel_intakes_per_owner or sum(self._pending_intakes.values()) >= self.max_parallel_intakes_global:
                reason = "upload_admission_busy"
            else:
                self._pending_intakes[owner_key] = pending + 1
                reason = None
        self._remove_roots(roots)
        return reason

    def finish_intake(self, owner_key: str) -> None:
        with self._lock:
            n = self._pending_intakes.get(owner_key, 0)
            if n <= 1:
                self._pending_intakes.pop(owner_key, None)
            else:
                self._pending_intakes[owner_key] = n - 1

    def create(self, filename: str, content: bytes, sha256: str, *, owner_key: str = "", reserved_intake: bool = False) -> Session:
        del filename
        with self._lock:
            roots = self._collect_expired_locked()
            pending_total = sum(self._pending_creates.values())
            owned = sum(item.owner_key == owner_key for item in self._items.values())
            pending_total_intakes = sum(self._pending_intakes.values())
            if reserved_intake and self._pending_intakes.get(owner_key, 0) <= 0:
                raise RuntimeError('upload_reservation_missing')
            owner_full = bool(owner_key) and (owned + self._pending_creates.get(owner_key, 0)
                                              + (0 if reserved_intake else self._pending_intakes.get(owner_key, 0))) >= self.per_owner_sessions
            global_full = (len(self._items) + pending_total
                           + (0 if reserved_intake else pending_total_intakes)) >= self.max_sessions
            if not (owner_full or global_full):
                self._pending_creates[owner_key] = self._pending_creates.get(owner_key, 0) + 1
        self._remove_roots(roots)
        if roots and (owner_full or global_full):
            # Expiry cleanup runs outside the mutex; re-evaluate capacity only
            # after confirmed removals before rejecting a legitimate create.
            with self._lock:
                pending_total = sum(self._pending_creates.values())
                owned = sum(item.owner_key == owner_key for item in self._items.values())
                owner_full = bool(owner_key) and (owned + self._pending_creates.get(owner_key, 0)
                                                  + (0 if reserved_intake else self._pending_intakes.get(owner_key, 0))) >= self.per_owner_sessions
                global_full = (len(self._items) + pending_total
                               + (0 if reserved_intake else sum(self._pending_intakes.values()))) >= self.max_sessions
                if not (owner_full or global_full):
                    self._pending_creates[owner_key] = self._pending_creates.get(owner_key, 0) + 1
        if owner_full or global_full:
            raise RuntimeError('client_session_capacity_reached' if owner_full else 'session_capacity_reached')
        root = None
        try:
            # Exclusive mkdir prevents collisions even with concurrent creation.
            # Reserve first; never hold the global map mutex during disk access.
            while True:
                sid = secrets.token_urlsafe(12)
                root = self.base / f'{SESSION_DIR_PREFIX}{sid}'
                try:
                    root.mkdir(mode=0o700, exist_ok=False)
                    break
                except FileExistsError:
                    continue
            token = secrets.token_urlsafe(32)
            _secure_write(root / SESSION_MARKER, b'venue-agent-session-v1\n')
            source = root / 'source.pptx'
            _secure_write(source, content)
            now = self._clock()
            session = Session(session_id=sid, root=root, source_path=source,
                              source_sha256=sha256, capability_hash=_capability_digest(token),
                              owner_key=owner_key, created_at=now, last_activity_at=now,
                              expires_at=now + self.provisional_ttl_seconds,
                              monotonic_expires_at=self._elapsed_clock() + self.provisional_ttl_seconds,
                              _issued_capability_token=token)
            with self._lock:
                self._items[sid] = session
            return session
        except BaseException:
            if root is not None:
                shutil.rmtree(root, ignore_errors=True)
            raise
        finally:
            with self._lock:
                remaining = self._pending_creates.get(owner_key, 0) - 1
                if remaining:
                    self._pending_creates[owner_key] = remaining
                else:
                    self._pending_creates.pop(owner_key, None)

    def authorize(self, sid: str, token: str) -> bool:
        roots: list[Path]
        with self._lock:
            roots = self._collect_expired_locked()
            s = self._items.get(sid)
            authorized = bool(
                s is not None
                and not s.delete_requested
                and not s.expired
                and token
                and secrets.compare_digest(s.capability_hash, _capability_digest(token))
            )
            if authorized and s is not None:
                now = self._clock()
                s.first_authenticated_at = s.first_authenticated_at or now
                s.last_activity_at = now
                s.expires_at = now + self.ttl_seconds
                s.monotonic_expires_at = self._elapsed_clock() + self.ttl_seconds
        self._remove_roots(roots)
        return authorized

    def get(self, sid: str) -> Session:
        roots: list[Path]
        with self._lock:
            roots = self._collect_expired_locked()
            s = self._items.get(sid)
        self._remove_roots(roots)
        if s is None or s.delete_requested or s.expired:
            raise KeyError(sid)
        return s

    @contextmanager
    def locked(self, sid: str):
        """Lease and serialize one live session without convoying other sessions.

        The global map lock is used only to reserve/release the lease; it is
        never held while waiting on the per-session lock. The idle TTL is
        refreshed on entry and completion, so an operation cannot succeed and
        immediately lose its session merely because it ran longer than the old
        absolute creation-time TTL.
        """
        roots: list[Path]
        with self._lock:
            roots = self._collect_expired_locked()
            s = self._items.get(sid)
            if s is None or s.delete_requested or s.cleanup_pending or s.expired:
                reserved = False
            elif s.active_operations >= 1 + self.max_waiters_per_session:
                reserved = False
                busy = True
            else:
                now = self._clock()
                s.active_operations += 1
                s.last_activity_at = now
                s.expires_at = now + self.ttl_seconds
                s.monotonic_expires_at = self._elapsed_clock() + self.ttl_seconds
                reserved = True
                busy = False
        self._remove_roots(roots)
        if not reserved or s is None:
            if locals().get("busy", False):
                raise SessionBusy("session_operation_queue_full")
            raise KeyError(sid)

        acquired = False
        valid = False
        try:
            acquired = s.lock.acquire(timeout=self.lock_wait_timeout_seconds)
            if not acquired:
                raise SessionBusy("session_operation_wait_timed_out")
            with self._lock:
                if self._items.get(sid) is s and not s.delete_requested and not s.expired:
                    now = self._clock()
                    s.last_activity_at = now
                    s.expires_at = now + self.ttl_seconds
                    s.monotonic_expires_at = self._elapsed_clock() + self.ttl_seconds
                    valid = True
            if not valid:
                raise KeyError(sid)
            yield s
        finally:
            if acquired:
                s.lock.release()
            with self._lock:
                s.active_operations = max(0, s.active_operations - 1)
                if self._items.get(sid) is s and not s.delete_requested and not s.expired:
                    now = self._clock()
                    s.last_activity_at = now
                    s.expires_at = now + self.ttl_seconds
                    s.monotonic_expires_at = self._elapsed_clock() + self.ttl_seconds

    def delete(self, sid: str) -> bool:
        with self._lock:
            roots = self._collect_expired_locked()
            session = self._items.get(sid)
            if session is None or session.delete_requested:
                found = False
            else:
                session.delete_requested = True
                found = True
        self._remove_roots(roots)
        if not found or session is None:
            return False
        # Existing session operations drain before removal; unrelated sessions
        # never wait behind a global lock during filesystem IO.
        return self._finish_cleanup(session)

    def atomic_begin_execution(self, sid: str, plan_hash: str, idem: str) -> Session:
        # Kept for compatibility with earlier tests/internal callers. Endpoint
        # execution uses the stronger locked() boundary directly.
        with self.locked(sid) as s:
            if idem in s.used_idempotency_keys:
                raise ValueError("idempotency_key_reused")
            if s.state != WorkflowState.AWAITING_APPROVAL or s.approved_plan_hash != plan_hash:
                raise ValueError("approval_missing_or_stale")
            s.used_idempotency_keys.add(idem)
            s.state = WorkflowState.EXECUTING
            return s
