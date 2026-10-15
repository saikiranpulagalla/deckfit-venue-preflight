from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass
class HttpResult:
    status: int
    body: bytes
    headers: dict[str, str]
    elapsed_ms: float


def _request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    token: str | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 45.0,
) -> HttpResult:
    headers: dict[str, str] = {"User-Agent": "venue-agent-release-check/1"}
    data: bytes | None = None
    if token:
        headers["X-Venue-Token"] = token
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method, headers=headers)
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            status = resp.status
            response_headers = {k.casefold(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = exc.code
        response_headers = {k.casefold(): v for k, v in exc.headers.items()}
    return HttpResult(
        status=status,
        body=body,
        headers=response_headers,
        elapsed_ms=round((time.perf_counter() - start) * 1000, 1),
    )



def _require_security_headers(result: HttpResult, label: str, *, require_no_store: bool = False) -> None:
    required = {
        "referrer-policy": "no-referrer",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
    }
    for name, expected in required.items():
        actual = result.headers.get(name)
        if actual != expected:
            raise RuntimeError(f"{label}: missing/incorrect {name}: expected {expected!r}, got {actual!r}")
    csp = result.headers.get("content-security-policy", "")
    if "frame-ancestors 'none'" not in csp or "object-src 'none'" not in csp:
        raise RuntimeError(f"{label}: expected restrictive content-security-policy, got {csp!r}")
    if require_no_store and "no-store" not in result.headers.get("cache-control", "").lower():
        raise RuntimeError(f"{label}: response is not no-store: {result.headers.get('cache-control')!r}")

def _json(result: HttpResult) -> dict[str, Any]:
    try:
        return json.loads(result.body.decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Expected JSON from HTTP {result.status}: {result.body[:200]!r}") from exc


def _expect(result: HttpResult, status: int, label: str) -> None:
    if result.status != status:
        detail = result.body[:500].decode("utf-8", errors="replace")
        raise RuntimeError(f"{label}: expected HTTP {status}, got {result.status}: {detail}")


def run_check(
    base_url: str,
    *,
    expected_release_id: str | None,
    require_gemini: bool,
    full: bool,
    expected_source_fingerprint: str | None = None,
) -> dict[str, Any]:
    if expected_release_id and 'rc5' in expected_release_id.casefold() and not expected_source_fingerprint:
        raise RuntimeError('rc5_source_fingerprint_required_for_release_attestation')
    report: dict[str, Any] = {
        "schema_version": 1,
        "base_url": base_url.rstrip("/"),
        "full_judge_path": full,
        "checks": {},
        "latency_ms": {},
    }

    health_r = _request(base_url, "/health", timeout=20)
    _expect(health_r, 200, "health")
    _require_security_headers(health_r, "health", require_no_store=True)
    health = _json(health_r)
    report["latency_ms"]["health"] = health_r.elapsed_ms
    report["release_id"] = health.get("release_id")
    report["planner_mode"] = health.get("planner_mode")
    if expected_release_id and health.get("release_id") != expected_release_id:
        raise RuntimeError(
            f"release mismatch: expected {expected_release_id!r}, got {health.get('release_id')!r}"
        )
    if expected_source_fingerprint:
        actual = health.get('source_fingerprint')
        if actual != expected_source_fingerprint:
            raise RuntimeError('deployment_source_fingerprint_mismatch')
        report['checks']['source_fingerprint'] = 'PASS'
    report['source_fingerprint'] = health.get('source_fingerprint')
    if require_gemini and health.get("planner_mode") != "gemini_configured_with_deterministic_fallback":
        raise RuntimeError(f"Gemini required but planner_mode={health.get('planner_mode')!r}")
    report["checks"]["health"] = "PASS"

    ready_r = _request(base_url, "/health/readiness", timeout=20)
    _expect(ready_r, 200, "readiness")
    _require_security_headers(ready_r, "readiness", require_no_store=True)
    ready = _json(ready_r)
    report["latency_ms"]["readiness"] = ready_r.elapsed_ms
    if ready.get("status") != "ready":
        raise RuntimeError(f"readiness degraded: {ready}")
    if ready.get("required_replica_count") != 1:
        raise RuntimeError(f"single-replica contract missing: {ready}")
    if ready.get("max_concurrent_renders") != 1:
        raise RuntimeError(f"expected one concurrent renderer for competition release: {ready}")
    report["checks"]["readiness"] = "PASS"

    deep_r = _request(base_url, "/health/deep-readiness", timeout=45)
    _expect(deep_r, 200, "deep readiness")
    _require_security_headers(deep_r, "deep readiness", require_no_store=True)
    deep = _json(deep_r)
    report["latency_ms"]["deep_readiness"] = deep_r.elapsed_ms
    if deep.get("status") != "ready" or not deep.get("renderer_version"):
        raise RuntimeError(f"deep readiness failed: {deep}")
    report["renderer_version"] = deep.get("renderer_version")
    report["checks"]["deep_readiness"] = "PASS"

    home_r = _request(base_url, "/", timeout=20)
    _expect(home_r, 200, "homepage")
    _require_security_headers(home_r, "homepage")
    homepage = home_r.body.decode("utf-8", errors="replace")
    for phrase in (
        "DeckFit AI · Presentation preflight",
        "Prepare your slides for the actual room.",
        "VERIFIED means only",
    ):
        if phrase not in homepage:
            raise RuntimeError(f"homepage missing judge-facing phrase: {phrase}")
    report["latency_ms"]["homepage"] = home_r.elapsed_ms
    report["checks"]["homepage"] = "PASS"
    report["checks"]["security_headers"] = "PASS"

    if not full:
        return report

    sid: str | None = None
    token: str | None = None
    try:
        demo_r = _request(base_url, "/api/demo", method="POST", timeout=20)
        _expect(demo_r, 200, "demo session")
        _require_security_headers(demo_r, "demo session", require_no_store=True)
        demo = _json(demo_r)
        sid = demo.get("session_id")
        token = demo.get("session_token")
        if not sid or not token or demo.get("state") != "UPLOADED":
            raise RuntimeError(f"invalid demo session response: {demo}")
        report["latency_ms"]["demo_session"] = demo_r.elapsed_ms
        report["source_sha256"] = demo.get("source_sha256")
        report["checks"]["demo_session"] = "PASS"

        analyze_r = _request(
            base_url,
            f"/api/sessions/{sid}/analyze",
            method="POST",
            token=token,
            json_body={
                "venue": {
                    "active_image_height_m": 1.8,
                    "farthest_viewer_distance_m": 10.8,
                    "measurement_basis": "MEASURED",
                }
            },
            timeout=60,
        )
        _expect(analyze_r, 200, "analyze")
        _require_security_headers(analyze_r, "analyze", require_no_store=True)
        analyze = _json(analyze_r)
        if analyze.get("state") != "ANALYZED":
            raise RuntimeError(f"demo did not reach ANALYZED: {analyze}")
        if analyze.get("analysis", {}).get("summary", {}).get("below_target_elements", 0) < 1:
            raise RuntimeError(f"demo has no below-target supported issue: {analyze}")
        report["latency_ms"]["analyze"] = analyze_r.elapsed_ms
        report["checks"]["analyze"] = "PASS"

        plan_r = _request(
            base_url,
            f"/api/sessions/{sid}/plan",
            method="POST",
            token=token,
            json_body={
                "constraints": {
                    "max_mutations": 2,
                    "max_scale_factor": 1.6,
                    "minimum_target_coverage": 0.9,
                    "protect_titles": True,
                    "semantic_rewrite": False,
                }
            },
            timeout=60,
        )
        _expect(plan_r, 200, "plan")
        _require_security_headers(plan_r, "plan", require_no_store=True)
        plan = _json(plan_r)
        if plan.get("state") != "AWAITING_APPROVAL":
            raise RuntimeError(f"demo did not reach AWAITING_APPROVAL: {plan}")
        ids = plan.get("decision", {}).get("selected_candidate_ids") or []
        plan_hash = plan.get("plan_hash")
        if not ids or not plan_hash:
            raise RuntimeError(f"planner returned no approvable plan: {plan}")
        report["latency_ms"]["plan"] = plan_r.elapsed_ms
        report["planner_used"] = plan.get("decision", {}).get("planner_used")
        report["fallback_used"] = bool(plan.get("decision", {}).get("fallback_used"))
        if require_gemini and (
            report["fallback_used"] or not str(report["planner_used"] or "").lower().startswith("gemini-")
        ):
            raise RuntimeError(f"Public judge path did not prove an actual Gemini decision: {plan}")
        report["checks"]["plan"] = "PASS"

        apply_r = _request(
            base_url,
            f"/api/sessions/{sid}/approve-and-apply",
            method="POST",
            token=token,
            json_body={
                "candidate_ids": ids,
                "plan_hash": plan_hash,
                "idempotency_key": str(uuid.uuid4()),
                "approve": True,
            },
            timeout=90,
        )
        _expect(apply_r, 200, "approve-and-apply")
        _require_security_headers(apply_r, "approve-and-apply", require_no_store=True)
        applied = _json(apply_r)
        if applied.get("state") != "VERIFIED":
            raise RuntimeError(f"judge fixture did not reach VERIFIED: {applied}")
        verification = applied.get("verification") or {}
        if not verification.get("source_sha256_unchanged"):
            raise RuntimeError(f"source immutability invariant failed: {verification}")
        verified_sha = verification.get("output_sha256")
        if not verified_sha:
            raise RuntimeError(f"verification did not expose output SHA-256: {verification}")
        report["latency_ms"]["approve_apply_verify"] = apply_r.elapsed_ms
        report["verified_output_sha256"] = verified_sha
        report["checks"]["approve_apply_verify"] = "PASS"

        output_r = _request(base_url, f"/api/sessions/{sid}/output", token=token, timeout=30)
        _expect(output_r, 200, "download")
        _require_security_headers(output_r, "download", require_no_store=True)
        if "private" not in output_r.headers.get("cache-control", "").lower():
            raise RuntimeError("download response is not marked private")
        if "presentationml.presentation" not in output_r.headers.get("content-type", ""):
            raise RuntimeError(f"download has unexpected content-type: {output_r.headers.get('content-type')!r}")
        if "attachment" not in output_r.headers.get("content-disposition", "").lower():
            raise RuntimeError("download is missing attachment Content-Disposition")
        downloaded_sha = hashlib.sha256(output_r.body).hexdigest()
        if downloaded_sha != verified_sha:
            raise RuntimeError(
                f"download hash mismatch: verified={verified_sha} downloaded={downloaded_sha}"
            )
        if output_r.headers.get("x-venue-output-sha256") != downloaded_sha:
            raise RuntimeError("download response hash header does not match downloaded artifact")
        report["latency_ms"]["download"] = output_r.elapsed_ms
        report["downloaded_output_sha256"] = downloaded_sha
        report["checks"]["download_hash_binding"] = "PASS"

        report["judge_path_total_ms"] = round(
            sum(
                report["latency_ms"].get(k, 0.0)
                for k in ("demo_session", "analyze", "plan", "approve_apply_verify", "download")
            ),
            1,
        )

        delete_r = _request(base_url, f"/api/sessions/{sid}", method="DELETE", token=token, timeout=10)
        _expect(delete_r, 200, "session delete")
        _require_security_headers(delete_r, "session delete", require_no_store=True)
        deleted = _json(delete_r)
        if deleted.get("deleted") is not True:
            raise RuntimeError(f"session delete did not confirm deletion: {deleted}")
        post_delete_r = _request(base_url, f"/api/sessions/{sid}/output", token=token, timeout=10)
        if post_delete_r.status != 404:
            raise RuntimeError(f"deleted session remained accessible: HTTP {post_delete_r.status}")
        _require_security_headers(post_delete_r, "post-delete access", require_no_store=True)
        report["checks"]["session_delete"] = "PASS"
        sid = None
        token = None
        return report
    finally:
        if sid and token:
            try:
                _request(base_url, f"/api/sessions/{sid}", method="DELETE", token=token, timeout=10)
            except Exception:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a deployed Venue Agent release and optional full judge path.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expected-release-id")
    parser.add_argument("--expected-source-fingerprint", help="SHA-256 computed independently from exported RC5 source")
    parser.add_argument("--require-gemini", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    report = run_check(
        args.base_url,
        expected_release_id=args.expected_release_id,
        require_gemini=args.require_gemini,
        full=args.full,
        expected_source_fingerprint=args.expected_source_fingerprint,
    )
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
