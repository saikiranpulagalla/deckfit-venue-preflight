from __future__ import annotations

from pathlib import Path
from contextlib import asynccontextmanager
import asyncio
import hashlib
import ipaddress
import logging
import os
import secrets
import shutil
import tempfile
import threading
import time
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response, JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from app.agent.planner import GeminiPlanner
from app.domain.models import PlanningContext, RepairConstraints, VenueProfile, WorkflowState
from app.pptx.mutations import ScaleMutation, apply_scale_plan
from app.pptx.renderer import MAX_CONCURRENT_RENDERS, RenderError, libreoffice_version, render_pptx_to_pdf
from app.repair.candidates import generate_candidates
from app.repair.simulation import simulate_candidate, simulate_plan
from app.repair.verifier import verify_output
from app.security.http import MAX_REQUEST_BODY_BYTES, RequestBodyLimitMiddleware, SecurityHeadersMiddleware
from app.security.intake import IntakeError, sha256_path, validate_pptx
from app.security.build_identity import source_fingerprint
from app.storage.sessions import SessionStore, SessionBusy, SessionCleanupError
from app.venue.analyzer import VenueAnalyzer
from app.venue.reference import PublicBDMReference


ROOT = Path(__file__).resolve().parents[2]
LOGGER = logging.getLogger(__name__)
REFERENCE = PublicBDMReference(ROOT / "reference" / "PUBLIC_BDM_REFERENCE_V1.json")
ANALYZER = VenueAnalyzer(REFERENCE)
def _resolve_session_root(raw: str | None) -> Path:
    value = (raw or "").strip()
    if not value:
        return Path(tempfile.gettempdir()) / "venue-agent-sessions"
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise RuntimeError("VENUE_SESSION_ROOT must be an absolute dedicated directory")
    resolved = path.resolve()
    if resolved in {Path("/"), Path.home().resolve()}:
        raise RuntimeError("VENUE_SESSION_ROOT cannot be the filesystem root or home directory")
    return resolved


SESSION_ROOT = _resolve_session_root(os.getenv("VENUE_SESSION_ROOT"))
STORE = SessionStore(
    SESSION_ROOT,
    ttl_seconds=int(os.getenv("VENUE_SESSION_TTL_SECONDS", "2700")),
    max_sessions=int(os.getenv("VENUE_MAX_SESSIONS", "24")),
    per_owner_sessions=int(os.getenv("VENUE_PER_CLIENT_SESSIONS", "8")),
    provisional_ttl_seconds=int(os.getenv("VENUE_PROVISIONAL_SESSION_TTL_SECONDS", "300")),
)
PLANNER = GeminiPlanner()
_CLIENT_OWNER_SALT = secrets.token_bytes(24)


def _client_owner_key(request: Request) -> str:
    """Use peer identity unless explicitly trusted proxy hops are configured.

    For a trusted peer, walk X-Forwarded-For from right to left and select the
    closest untrusted address. Do not trust the leftmost value (it may be
    user-injected at an ingress that appends rather than replaces headers).
    This does not auto-enable proxy trust on Railway; operator verification of
    the network boundary remains mandatory.
    """
    peer = request.client.host if request.client else "unknown"
    raw = [v.strip() for v in os.getenv("VENUE_TRUSTED_PROXY_IPS", "").split(",") if v.strip()]
    networks = []
    for value in raw:
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue  # Fail closed for invalid deployment configuration.

    def trusted(ip: str) -> bool:
        try:
            return any(ipaddress.ip_address(ip) in net for net in networks)
        except ValueError:
            return False

    if trusted(peer):
        chain = request.headers.get("x-forwarded-for", "")
        if len(chain) <= 2048:
            for part in reversed(chain.split(",")):
                try:
                    candidate = str(ipaddress.ip_address(part.strip()))
                except ValueError:
                    break  # Ambiguous proxy data is not a trusted identity.
                peer = candidate
                if not trusted(candidate):
                    break
    return hashlib.sha256(_CLIENT_OWNER_SALT + peer.encode("utf-8")).hexdigest()


def _enforce_single_worker_config() -> None:
    for name in ("WEB_CONCURRENCY", "UVICORN_WORKERS"):
        raw = os.getenv(name)
        if raw:
            try:
                if int(raw) > 1:
                    raise RuntimeError(f"{name} must be 1 because competition V1 session state is process-local")
            except ValueError as e:
                raise RuntimeError(f"{name} must be an integer") from e


_enforce_single_worker_config()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    STORE.start_reaper()
    try:
        yield
    finally:
        STORE.stop_reaper()


RELEASE_ID = os.getenv("VENUE_RELEASE_ID", "deckfit-nextfounders-rc5-local")

app = FastAPI(title="DeckFit AI — Room-aware presentation preflight", version="1.1.0-nextfounders", lifespan=lifespan)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)


class _UploadBodyTimeout(Exception):
    """The multipart body did not arrive inside the configured wire budget."""


class EarlyUploadAdmissionMiddleware:
    """Reject before multipart parsing and bound only upload *body receipt*.

    Do not time out the entire downstream application: canceling a worker while
    it mutates a session could break the mutation/approval invariants. When the
    last request-body chunk is received, downstream parsing/processing proceeds
    normally; the intake reservation is released in all exit paths.
    """

    def __init__(self, application):
        self.application = application
        self.idle_seconds = max(1.0, float(os.getenv("VENUE_UPLOAD_IDLE_SECONDS", "12")))
        self.absolute_seconds = max(self.idle_seconds, float(os.getenv("VENUE_UPLOAD_BODY_SECONDS", "45")))

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") != "/api/upload" or scope.get("method") != "POST":
            await self.application(scope, receive, send)
            return
        owner = _client_owner_key(Request(scope))
        reason = STORE.begin_intake(owner)
        if reason:
            status = 429 if reason == "client_session_capacity_reached" else 503
            await JSONResponse({"detail": reason}, status_code=status,
                               headers={"Retry-After": "3", "Cache-Control": "no-store"})(scope, receive, send)
            return

        deadline = asyncio.get_running_loop().time() + self.absolute_seconds
        body_complete = False
        response_started = False

        async def bounded_receive():
            nonlocal body_complete
            if body_complete:
                return await receive()
            budget = min(self.idle_seconds, deadline - asyncio.get_running_loop().time())
            if budget <= 0:
                raise _UploadBodyTimeout
            try:
                message = await asyncio.wait_for(receive(), timeout=budget)
            except asyncio.TimeoutError as exc:
                raise _UploadBodyTimeout from exc
            if message.get("type") == "http.request" and not message.get("more_body", False):
                body_complete = True
            return message

        async def tracked_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.application(scope, bounded_receive, tracked_send)
        except _UploadBodyTimeout:
            if not response_started:
                await JSONResponse(
                    {"detail": "upload_body_timeout"}, status_code=408,
                    headers={"Cache-Control": "no-store"},
                )(scope, receive, send)
            else:
                raise
        finally:
            STORE.finish_intake(owner)


app.add_middleware(EarlyUploadAdmissionMiddleware)
# Last registered = outermost in Starlette. Every early 408/413/429/503 must
# traverse the same security-header layer as normal responses.
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(SessionBusy)
async def session_busy_handler(_request: Request, exc: SessionBusy):
    return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "3"})


def _busy_render(exc: Exception) -> bool:
    return isinstance(exc, RenderError) and "capacity is busy" in str(exc)


def _stage_failure(exc: Exception, *, phase: str) -> HTTPException:
    if _busy_render(exc):
        return HTTPException(503, f"{phase}_renderer_busy_retry", headers={"Retry-After": "3"})
    return HTTPException(422, f"{phase}_could_not_complete:{type(exc).__name__}")

MAX_REPAIRABLE_ISSUES = 20
MAX_CANDIDATE_SIMULATIONS = 18


def _analysis_review_reasons(summary) -> list[str]:
    reasons: list[str] = []
    if summary.analyzed_elements == 0:
        reasons.append("no_analyzable_text_elements")
    if summary.not_analyzed_elements:
        reasons.append("not_analyzed_elements_present")
    if summary.boundary_review_elements:
        reasons.append("estimated_measurement_boundary_present")
    if summary.outside_reference_elements:
        reasons.append("outside_reference_elements_present")
    if summary.unsupported_visible_content_elements:
        reasons.append("unsupported_visible_content_present")
    return reasons


def _no_action_is_proven(summary) -> bool:
    return (
        summary.analyzed_elements > 0
        and summary.below_target_elements == 0
        and not _analysis_review_reasons(summary)
    )


def _verification_output_is_mechanically_safe(report) -> bool:
    # REVIEW_REQUIRED may mean either "safe mutation, unrelated unknown coverage"
    # or "the mutation itself failed a hard invariant". Only the former may
    # remain available as a review copy.
    return all([
        report.source_sha256_unchanged,
        report.protected_text_unchanged,
        report.output_reopens,
        report.target_improved,
        report.analysis_universe_preserved,
        report.layout_safe,
    ])


def _require_session_capability(
    sid: str,
    x_venue_token: Annotated[str | None, Header(alias="X-Venue-Token")] = None,
) -> None:
    # Capability failures intentionally look identical to unknown session IDs so
    # a non-secret public ID cannot be used as an enumeration oracle.
    if not x_venue_token or not STORE.authorize(sid, x_venue_token):
        raise HTTPException(404, "Unknown session")


_READINESS_LOCK = threading.Lock()
_READINESS_LAST_PROBE_AT = 0.0
_READINESS_LAST_SUCCESS_AT = 0.0
_READINESS_LAST_DETAIL = "not_probed"
_READINESS_LAST_RESULT = False
_READINESS_PROBE_TTL_S = max(30.0, float(os.getenv("VENUE_READINESS_PROBE_TTL_SECONDS", "300")))
_READINESS_SUCCESS_GRACE_S = max(_READINESS_PROBE_TTL_S, float(os.getenv("VENUE_READINESS_SUCCESS_GRACE_SECONDS", "900")))


def _deep_renderer_readiness() -> tuple[bool, str]:
    global _READINESS_LAST_PROBE_AT, _READINESS_LAST_SUCCESS_AT, _READINESS_LAST_DETAIL, _READINESS_LAST_RESULT
    now = time.monotonic()
    with _READINESS_LOCK:
        cache_ttl = _READINESS_PROBE_TTL_S if _READINESS_LAST_SUCCESS_AT else min(10.0, _READINESS_PROBE_TTL_S)
        if _READINESS_LAST_PROBE_AT and now - _READINESS_LAST_PROBE_AT < cache_ttl:
            return _READINESS_LAST_RESULT, _READINESS_LAST_DETAIL
        demo = ROOT / "demo" / "venue-agent-demo.pptx"
        if not demo.exists():
            _READINESS_LAST_PROBE_AT = now
            _READINESS_LAST_DETAIL = "demo_fixture_missing"
            _READINESS_LAST_RESULT = False
            return False, _READINESS_LAST_DETAIL
        try:
            with tempfile.TemporaryDirectory(prefix="venue-readiness-") as td:
                pdf = render_pptx_to_pdf(demo, Path(td), timeout_s=10)
                if not pdf.exists() or pdf.stat().st_size <= 0:
                    raise RenderError("empty readiness PDF")
            _READINESS_LAST_PROBE_AT = now
            _READINESS_LAST_SUCCESS_AT = now
            _READINESS_LAST_DETAIL = "real_demo_render_pass"
            _READINESS_LAST_RESULT = True
            return True, _READINESS_LAST_DETAIL
        except RenderError as e:
            _READINESS_LAST_PROBE_AT = now
            if "capacity is busy" in str(e) and _READINESS_LAST_SUCCESS_AT and now - _READINESS_LAST_SUCCESS_AT <= _READINESS_SUCCESS_GRACE_S:
                _READINESS_LAST_DETAIL = "render_busy_using_recent_success"
                _READINESS_LAST_RESULT = True
                return True, _READINESS_LAST_DETAIL
            _READINESS_LAST_DETAIL = f"render_probe_failed:{type(e).__name__}"
            _READINESS_LAST_RESULT = False
            return False, _READINESS_LAST_DETAIL


class AnalyzeRequest(BaseModel):
    venue: VenueProfile


class PlanRequest(BaseModel):
    constraints: RepairConstraints = RepairConstraints()


class ApproveRequest(BaseModel):
    candidate_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=18)
    candidate_id: str | None = Field(default=None, min_length=1, max_length=128)  # backwards-compatible single-candidate input
    plan_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    approve: bool = True

    @model_validator(mode="after")
    def normalize_candidate_ids(self):
        if not self.candidate_ids and self.candidate_id:
            self.candidate_ids = [self.candidate_id]
        elif self.candidate_id and self.candidate_ids != [self.candidate_id]:
            raise ValueError("candidate_id and candidate_ids disagree")
        if self.approve and not self.candidate_ids:
            raise ValueError("approved request requires candidate_ids")
        return self


@app.get("/health")
def health():
    return {
        "status": "ok",
        "reference_profile": REFERENCE.profile_id,
        "release_id": RELEASE_ID,
        "source_fingerprint": source_fingerprint(ROOT),
        "planner_mode": "gemini_configured_with_deterministic_fallback" if PLANNER.api_key else "deterministic_fallback",
    }


@app.get("/health/readiness")
def readiness():
    renderer = libreoffice_version() if (shutil.which("libreoffice") or shutil.which("soffice")) else None
    demo_exists = (ROOT / "demo" / "venue-agent-demo.pptx").exists()
    planner_mode = "gemini_configured_with_deterministic_fallback" if PLANNER.api_key else "deterministic_fallback"
    ready = bool(renderer and demo_exists)
    payload = {
        "status": "ready" if ready else "degraded",
        "reference_profile": REFERENCE.profile_id,
        "release_id": RELEASE_ID,
        "source_fingerprint": source_fingerprint(ROOT),
        "renderer_version": renderer,
        "demo_fixture": demo_exists,
        "planner_mode": planner_mode,
        "session_ttl_seconds": STORE.ttl_seconds,
        "max_sessions": STORE.max_sessions,
        "per_client_session_limit": STORE.per_owner_sessions,
        "session_backend": "process_local_ephemeral",
        "required_replica_count": 1,
        "max_concurrent_renders": MAX_CONCURRENT_RENDERS,
    }
    return JSONResponse(content=payload, status_code=200 if ready else 503)


@app.get("/health/deep-readiness")
def deep_readiness():
    renderer = libreoffice_version()
    probe_ok, probe_detail = _deep_renderer_readiness()
    ready = bool(renderer and probe_ok)
    payload = {
        "status": "ready" if ready else "degraded",
        "reference_profile": REFERENCE.profile_id,
        "release_id": RELEASE_ID,
        "source_fingerprint": source_fingerprint(ROOT),
        "renderer_version": renderer,
        "renderer_probe": probe_detail,
        "session_backend": "process_local_ephemeral",
        "required_replica_count": 1,
        "max_concurrent_renders": MAX_CONCURRENT_RENDERS,
    }
    return JSONResponse(content=payload, status_code=200 if ready else 503)


def _output_is_current(s) -> bool:
    """Never advertise an artifact that download would reject."""
    if not s.output_path:
        return False
    try:
        valid = bool(s.output_sha256 and s.output_path.is_file()
                     and sha256_path(s.output_path) == s.output_sha256)
    except OSError:
        valid = False
    if not valid:
        # Fail closed under session lock; never expose filesystem details.
        if s.output_path is not None:
            try:
                s.output_path.unlink(missing_ok=True)
            except OSError:
                pass
        s.output_path = None
        s.output_sha256 = None
        s.output_venue = None
        s.state = WorkflowState.FAILED
    return valid


@app.get("/api/sessions/{sid}")
def session_status(sid: str, _cap: None = Depends(_require_session_capability)):
    try:
        with STORE.locked(sid) as s:
            has_output = _output_is_current(s)
            return {
                "session_id": s.session_id,
                "state": s.state,
                "source_sha256": s.source_sha256,
                "expires_at": s.expires_at,
                "has_output": has_output,
                "output_sha256": s.output_sha256 if has_output else None,
                "analysis_revision": s.analysis_revision,
                "analysis_venue": ((s.analysis.venue if s.analysis else s.output_venue).model_dump(mode="json")
                                   if (s.analysis or s.output_venue) else None),
                "pending_plan": (
                    {
                        "plan_hash": s.plan_hash,
                        "analysis_revision": s.analysis_revision,
                        "venue": s.analysis.venue.model_dump(mode="json") if s.analysis else None,
                        "constraints": s.selected_constraints.model_dump(mode="json"),
                        "candidate_ids": list(s.selected_candidate_ids),
                        "plan_simulation": s.plan_simulation.model_dump(mode="json"),
                        "decision": s.plan_decision.model_dump(mode="json") if s.plan_decision else None,
                        "candidates": [c.model_dump(mode="json") for c in s.candidates],
                    }
                    if (
                        s.state == WorkflowState.AWAITING_APPROVAL
                        and s.plan_hash
                        and s.selected_constraints is not None
                        and s.plan_simulation is not None
                        and s.plan_simulation.safe
                        and s.selected_candidate_ids
                        and all(cid in {c.candidate_id for c in s.candidates if c.safe}
                                for cid in s.selected_candidate_ids)
                        and s.plan_hash == s.compute_plan_hash(
                            s.selected_candidate_ids, s.selected_constraints, s.plan_simulation)
                    ) else None
                ),
            }
    except KeyError:
        raise HTTPException(404, "Unknown session")


@app.post("/api/demo")
def create_demo_session(request: Request):
    demo = ROOT / "demo" / "venue-agent-demo.pptx"
    if not demo.exists():
        raise HTTPException(500, "Demo fixture missing")
    content = demo.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    try:
        s = STORE.create("venue-agent-demo.pptx", content, digest, owner_key=_client_owner_key(request))
        token = s.take_issued_capability_token()
    except RuntimeError as e:
        raise HTTPException(429 if str(e) == "client_session_capacity_reached" else 503, str(e))
    return {
        "session_id": s.session_id,
        "session_token": token,
        "source_sha256": s.source_sha256,
        "state": s.state,
        "expires_at": s.expires_at,
    }


def _validate_and_create_upload(content: bytes, filename: str, owner_key: str) -> dict:
    """Runs in Starlette's bounded worker pool, never on the HTTP event loop."""
    digest = hashlib.sha256(content).hexdigest()
    with tempfile.TemporaryDirectory(prefix="venue-intake-") as td:
        path = Path(td) / "upload.pptx"
        path.write_bytes(content)
        try:
            report = validate_pptx(path)
        except IntakeError as exc:
            raise HTTPException(400, str(exc)) from exc
        if report.has_external_relationships:
            raise HTTPException(400, "External linked resources are not supported")
    try:
        s = STORE.create(filename, content, digest, owner_key=owner_key, reserved_intake=True)
        token = s.take_issued_capability_token()
    except RuntimeError as exc:
        raise HTTPException(429 if str(exc) == "client_session_capacity_reached" else 503, str(exc)) from exc
    return {"session_id": s.session_id, "session_token": token,
            "source_sha256": s.source_sha256, "state": s.state,
            "expires_at": s.expires_at}


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large")
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(400, "Only .pptx is supported")
    return await run_in_threadpool(
        _validate_and_create_upload, content, file.filename or "source.pptx", _client_owner_key(request))


@app.post("/api/sessions/{sid}/analyze")
def analyze(sid: str, req: AnalyzeRequest, _cap: None = Depends(_require_session_capability)):
    try:
        with STORE.locked(sid) as s:
            if s.state in {WorkflowState.VERIFIED, WorkflowState.REVIEW_REQUIRED} and _output_is_current(s):
                raise HTTPException(409, "Completed output is immutable; create a new session to analyze again")
            # Any new analysis invalidates all plan/approval/output state from
            # the previous analysis revision. This is intentionally explicit
            # rather than relying on a later hash mismatch.
            previous_terminal = s.state if s.state in {WorkflowState.VERIFIED, WorkflowState.REVIEW_REQUIRED} else None
            previous_output = bool(s.output_path and _output_is_current(s))
            s.clear_derived_state(remove_output=False)
            s.analysis = None
            s.state = WorkflowState.UPLOADED
            try:
                analysis = ANALYZER.analyze(s.source_path, req.venue, s.root / "analysis")
                if analysis.summary.below_target_elements == 0:
                    staged_state = (WorkflowState.NO_ACTION_REQUIRED
                                    if _no_action_is_proven(analysis.summary) else WorkflowState.REVIEW_REQUIRED)
                    simulated = []
                    reasons = _analysis_review_reasons(analysis.summary)
                elif analysis.summary.below_target_elements > MAX_REPAIRABLE_ISSUES:
                    staged_state = WorkflowState.REVIEW_REQUIRED
                    simulated = []
                    reasons = [f"repairable_issue_budget_exceeded:{MAX_REPAIRABLE_ISSUES}"]
                else:
                    candidates = generate_candidates(analysis)
                    if len(candidates) > MAX_CANDIDATE_SIMULATIONS:
                        staged_state = WorkflowState.REVIEW_REQUIRED
                        simulated = []
                        reasons = ([f"candidate_simulation_budget_exceeded:{MAX_CANDIDATE_SIMULATIONS}"]
                                   + _analysis_review_reasons(analysis.summary))
                    else:
                        simulated = [simulate_candidate(s.source_path, analysis, c, ANALYZER)
                                     for c in candidates]
                        staged_state = WorkflowState.ANALYZED
                        reasons = _analysis_review_reasons(analysis.summary)
            except Exception as exc:
                # No partially prepared candidate/approval state is published.
                # Retain a formerly verified copy on transient reanalysis failure.
                # The old plan stays revoked; the saved artifact is still bound
                # to its original output digest, not the failed new venue.
                if previous_output and previous_terminal is not None:
                    s.state = previous_terminal
                else:
                    s.state = WorkflowState.UPLOADED if _busy_render(exc) else WorkflowState.FAILED
                raise _stage_failure(exc, phase="analysis") from exc
            s.clear_derived_state(remove_output=True)
            s.analysis_revision += 1
            s.analysis = analysis
            s.candidates = simulated
            s.state = staged_state
            return {"state": s.state, "analysis": analysis,
                    "candidates": simulated, "review_reasons": reasons}
    except KeyError as e:
        if e.args == (sid,):
            raise HTTPException(404, "Unknown session")
        raise


@app.post("/api/sessions/{sid}/plan")
def plan(sid: str, req: PlanRequest = PlanRequest(), _cap: None = Depends(_require_session_capability)):
    try:
        with STORE.locked(sid) as s:
            if s.state in {WorkflowState.VERIFIED, WorkflowState.REVIEW_REQUIRED} and _output_is_current(s):
                raise HTTPException(409, "Completed output is immutable; create a new session to replan")
            if s.analysis is None:
                raise HTTPException(409, "Analyze first")
            last_good_state = (s.state if s.state in {WorkflowState.VERIFIED, WorkflowState.REVIEW_REQUIRED}
                               and s.output_path is not None and _output_is_current(s) else None)
            if s.analysis.summary.below_target_elements == 0:
                s.clear_plan_state(remove_output=False)
                clean = _no_action_is_proven(s.analysis.summary)
                outcome = WorkflowState.NO_ACTION_REQUIRED if clean else WorkflowState.REVIEW_REQUIRED
                s.state = last_good_state or outcome
                return {
                    "state": outcome,
                    "previous_output_retained": last_good_state is not None,
                    "decision": {
                        "selected_candidate_ids": [],
                        "rationale": (
                            "No supported below-target elements require repair." if clean
                            else "No automated repair is justified because analysis coverage is incomplete or outside the modeled reference."
                        ),
                        "requires_human_review": not clean,
                        "unresolved_issue_ids": [],
                        "projected_target_coverage": s.analysis.summary.target_coverage,
                        "planner_used": "deterministic",
                        "fallback_used": False,
                    },
                    "review_reasons": _analysis_review_reasons(s.analysis.summary),
                }
            if s.analysis.summary.below_target_elements > MAX_REPAIRABLE_ISSUES:
                s.clear_plan_state(remove_output=False)
                s.state = last_good_state or WorkflowState.REVIEW_REQUIRED
                return {
                    "state": WorkflowState.REVIEW_REQUIRED,
                    "previous_output_retained": last_good_state is not None,
                    "decision": {
                        "selected_candidate_ids": [],
                        "rationale": "Repair issue count exceeds the bounded competition V1 simulation budget.",
                        "requires_human_review": True,
                        "unresolved_issue_ids": [r.element.element_id for r in s.analysis.results if r.state.value == "BELOW_TARGET"],
                        "projected_target_coverage": s.analysis.summary.target_coverage,
                        "planner_used": "deterministic",
                        "fallback_used": False,
                    },
                }

            # Re-planning invalidates any previously approvable plan before the
            # new decision is computed. Candidate simulations remain bound to
            # the current analysis revision.
            s.clear_plan_state(remove_output=False)
            s.state = WorkflowState.ANALYZED
            summary = s.analysis.summary
            below_issue_ids = [
                r.element.element_id for r in s.analysis.results
                if r.state.value == "BELOW_TARGET"
            ]
            repairable_issue_ids = sorted({
                c.issue_element_id for c in s.candidates if c.safe and c.simulation_fingerprint
            })
            context = PlanningContext(
                analyzed_elements=summary.analyzed_elements,
                meets_target_elements=summary.meets_target_elements,
                below_target_elements=summary.below_target_elements,
                current_target_coverage=summary.target_coverage,
                below_target_issue_ids=below_issue_ids,
                repairable_issue_ids=repairable_issue_ids,
            )
            try:
                decision = PLANNER.choose(s.candidates, req.constraints, context)
            except Exception as exc:
                if last_good_state is not None:
                    s.state = last_good_state
                raise _stage_failure(exc, phase="planning") from exc
            if not decision.selected_candidate_ids:
                review_reasons = _analysis_review_reasons(s.analysis.summary)
                if s.analysis.summary.target_coverage + 1e-12 >= req.constraints.minimum_target_coverage:
                    if decision.requires_human_review or review_reasons:
                        s.state = WorkflowState.REVIEW_REQUIRED
                        if decision.unresolved_issue_ids:
                            review_reasons.append("below_target_issues_remain_unresolved")
                    else:
                        s.state = WorkflowState.TARGET_ALREADY_SATISFIED
                else:
                    s.state = WorkflowState.NO_FEASIBLE_PLAN
                outcome = s.state
                if last_good_state is not None:
                    s.state = last_good_state
                return {"state": outcome, "previous_output_retained": last_good_state is not None,
                        "decision": decision, "review_reasons": sorted(set(review_reasons))}

            by_id = {c.candidate_id: c for c in s.candidates}
            try:
                selected = [by_id[cid] for cid in decision.selected_candidate_ids]
            except KeyError:
                raise HTTPException(500, "Planner selected an unknown candidate")
            if any(not c.safe for c in selected):
                raise HTTPException(500, "Planner selected an unsafe candidate")
            if len({c.issue_element_id for c in selected}) != len(selected):
                raise HTTPException(500, "Planner selected multiple candidates for one issue")

            try:
                combined = simulate_plan(s.source_path, s.analysis, selected, ANALYZER)
            except Exception as exc:
                if last_good_state is not None:
                    s.state = last_good_state
                raise _stage_failure(exc, phase="planning_simulation") from exc
            if not combined.safe:
                s.state = last_good_state or WorkflowState.NO_FEASIBLE_PLAN
                return {
                    "state": WorkflowState.NO_FEASIBLE_PLAN,
                    "previous_output_retained": last_good_state is not None,
                    "decision": decision,
                    "plan_simulation": combined,
                    "review_reasons": _analysis_review_reasons(s.analysis.summary),
                }
            if combined.target_coverage_after + 1e-12 < req.constraints.minimum_target_coverage:
                s.state = last_good_state or WorkflowState.NO_FEASIBLE_PLAN
                combined.reasons.append("combined_plan_below_requested_target_coverage")
                combined.safe = False
                return {
                    "state": WorkflowState.NO_FEASIBLE_PLAN,
                    "previous_output_retained": last_good_state is not None,
                    "decision": decision,
                    "plan_simulation": combined,
                    "review_reasons": _analysis_review_reasons(s.analysis.summary),
                }

            # The replacement plan is now independently simulated and safe;
            # only now retire the old checked output and commit new approval.
            s.clear_plan_state(remove_output=True)
            s.plan_nonce = secrets.token_hex(16)
            s.selected_candidate_ids = list(decision.selected_candidate_ids)
            s.selected_constraints = req.constraints
            s.plan_simulation = combined
            s.plan_decision = decision
            s.plan_hash = s.compute_plan_hash(s.selected_candidate_ids, req.constraints, combined)
            s.state = WorkflowState.AWAITING_APPROVAL
            return {
                "state": s.state,
                "plan_hash": s.plan_hash,
                "decision": decision,
                "plan_simulation": combined,
            }
    except KeyError as e:
        if e.args == (sid,):
            raise HTTPException(404, "Unknown session")
        raise


@app.post("/api/sessions/{sid}/approve-and-apply")
def approve_and_apply(sid: str, req: ApproveRequest, _cap: None = Depends(_require_session_capability)):
    try:
        with STORE.locked(sid) as s:
            if not req.approve:
                if s.state != WorkflowState.AWAITING_APPROVAL:
                    raise HTTPException(409, "No plan is awaiting approval")
                if s.plan_hash != req.plan_hash:
                    raise HTTPException(409, "Stale or mismatched rejection")
                if req.candidate_ids and s.selected_candidate_ids != req.candidate_ids:
                    raise HTTPException(409, "Rejected candidate list does not match current plan")
                s.state = WorkflowState.REJECTED_BY_USER
                return {"state": s.state, "plan_hash": s.plan_hash}
            if req.idempotency_key in s.used_idempotency_keys:
                raise HTTPException(409, "idempotency_key_reused")
            if len(s.used_idempotency_keys) >= 128:
                raise HTTPException(429, "session_idempotency_budget_exhausted")
            if s.state != WorkflowState.AWAITING_APPROVAL:
                raise HTTPException(409, "approval_missing_or_stale")
            if s.plan_hash != req.plan_hash or s.selected_candidate_ids != req.candidate_ids:
                raise HTTPException(409, "Stale or mismatched approval")
            if s.selected_constraints is None or s.plan_simulation is None:
                raise HTTPException(409, "Missing selected plan evidence")
            if s.analysis is None or s.analysis.source_sha256 != s.source_sha256:
                raise HTTPException(409, "Analysis is not bound to the uploaded source")
            if sha256_path(s.source_path) != s.source_sha256:
                raise HTTPException(409, "Source artifact changed after upload")
            try:
                current_hash = s.compute_plan_hash(s.selected_candidate_ids, s.selected_constraints, s.plan_simulation)
            except ValueError as e:
                raise HTTPException(409, str(e))
            if current_hash != s.plan_hash:
                raise HTTPException(409, "Plan evidence changed after planning")
            if not s.plan_simulation.safe or not all([
                s.plan_simulation.source_unchanged,
                s.plan_simulation.protected_text_unchanged,
                s.plan_simulation.rendered_text_unchanged,
                s.plan_simulation.analysis_universe_preserved,
                s.plan_simulation.layout_safe,
                s.plan_simulation.output_reopens,
                bool(s.plan_simulation.simulation_fingerprint),
            ]):
                raise HTTPException(409, "Plan simulation evidence is no longer executable")
            s.approved_plan_hash = req.plan_hash
            s.used_idempotency_keys.add(req.idempotency_key)
            s.state = WorkflowState.EXECUTING

            by_id = {c.candidate_id: c for c in s.candidates if c.safe}
            selected = [by_id.get(cid) for cid in req.candidate_ids]
            if any(c is None for c in selected) or s.analysis is None:
                s.state = WorkflowState.FAILED
                raise HTTPException(409, "Candidate plan no longer executable")

            mutations: list[ScaleMutation] = []
            target_ids: list[str] = []
            for c in selected:
                assert c is not None
                issue = next((r for r in s.analysis.results if r.element.element_id == c.issue_element_id), None)
                if issue is None or issue.element.shape_id is None:
                    s.state = WorkflowState.FAILED
                    raise HTTPException(409, "Candidate target no longer resolvable")
                mutations.append(ScaleMutation(
                    slide_index=issue.element.slide_index,
                    shape_id=issue.element.shape_id,
                    scale=float(c.parameters["scale"]),
                ))
                target_ids.append(c.issue_element_id)

            output = s.root / "output.pptx"
            try:
                apply_scale_plan(s.source_path, output, mutations)
                report = verify_output(
                    s.source_path,
                    output,
                    s.analysis,
                    target_ids,
                    ANALYZER,
                    s.root / "verification",
                    expected_scales={(m.slide_index, m.shape_id): m.scale for m in mutations},
                )
            except Exception as e:
                output.unlink(missing_ok=True)
                s.output_path = None
                s.output_sha256 = None
                s.output_venue = None
                s.state = WorkflowState.FAILED
                LOGGER.warning("repair_execution_failed type=%s", type(e).__name__)
                raise HTTPException(422, "repair_execution_failed") from e
            if _verification_output_is_mechanically_safe(report):
                s.output_path = output
                s.output_sha256 = report.output_sha256
                s.output_venue = s.analysis.venue
            else:
                output.unlink(missing_ok=True)
                s.output_path = None
                s.output_sha256 = None
                s.output_venue = None
            s.state = report.final_state
            return {"state": s.state, "verification": report}
    except KeyError as e:
        if e.args == (sid,):
            raise HTTPException(404, "Unknown session")
        raise


@app.delete("/api/sessions/{sid}")
def delete_session(sid: str, _cap: None = Depends(_require_session_capability)):
    try:
        deleted = STORE.delete(sid)
    except SessionCleanupError:
        raise HTTPException(503, "session_cleanup_incomplete_retry", headers={"Retry-After": "3"})
    if not deleted:
        raise HTTPException(404, "Unknown session")
    return {"deleted": True}


@app.get("/api/sessions/{sid}/output")
def download_output(sid: str, _cap: None = Depends(_require_session_capability)):
    try:
        with STORE.locked(sid) as s:
            if s.output_path is None or not s.output_path.exists():
                raise HTTPException(404, "No output available")
            if s.state not in {WorkflowState.VERIFIED, WorkflowState.REVIEW_REQUIRED}:
                raise HTTPException(409, "Output is not in a downloadable terminal state")
            # Snapshot the bounded output while the session lock is held. A
            # concurrent re-analysis or explicit delete may remove the ephemeral
            # file immediately after this point, but it cannot truncate an
            # already-approved download response.
            content = s.output_path.read_bytes()
            current_sha256 = hashlib.sha256(content).hexdigest()
            if not s.output_sha256 or current_sha256 != s.output_sha256:
                # A downloadable artifact must remain byte-identical to the
                # artifact that the verifier inspected. Fail closed if the
                # ephemeral output changes after verification.
                s.output_path.unlink(missing_ok=True)
                s.output_path = None
                s.output_sha256 = None
                s.output_venue = None
                s.state = WorkflowState.FAILED
                raise HTTPException(409, "Output artifact changed after verification")
            verified_sha256 = s.output_sha256
    except KeyError:
        raise HTTPException(404, "Unknown session")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={
            "Content-Disposition": 'attachment; filename="venue-repaired-copy.pptx"',
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "X-Venue-Output-SHA256": verified_sha256,
        },
    )


STATIC_DIR = ROOT / "frontend" / "static"
if STATIC_DIR.exists():
    class ReleaseAwareStaticFiles(StaticFiles):
        async def get_response(self, path, scope):
            response = await super().get_response(path, scope)
            # Inlined application JavaScript must be revalidated after an API
            # deployment; prevent a cached old shell from approving new plans.
            if path in {"", ".", "index.html"} or path.endswith("/index.html"):
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response

    app.mount("/", ReleaseAwareStaticFiles(directory=STATIC_DIR, html=True), name="static")
