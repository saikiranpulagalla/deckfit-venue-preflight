from __future__ import annotations

import argparse
import json
import subprocess
import sys
from urllib.parse import urlsplit
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing required evidence: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"Invalid JSON evidence {path}: {exc}") from exc


def _run(args: list[str], timeout: int = 120) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True, timeout=timeout)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail-closed final ForgeHacks submission gate.")
    parser.add_argument("--expected-release-id", required=True)
    parser.add_argument("--base-url", required=True, help="Public HTTPS deployment checked live on every run")
    parser.add_argument(
        "--live-report",
        type=Path,
        default=ROOT / "validation" / "evaluation" / "live-deployment-final.json",
    )
    parser.add_argument(
        "--planner-probe",
        type=Path,
        default=ROOT / "validation" / "evaluation" / "planner-probe-final.json",
    )
    parser.add_argument("--min-planner-runs", type=int, default=5)
    parser.add_argument("--max-judge-path-ms", type=float, default=120000.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "validation" / "evaluation" / "FINAL_SUBMISSION_READY.json",
    )
    args = parser.parse_args()

    # Local judge-facing claims must still be clean at the exact source snapshot
    # that consumes the external evidence.
    _run([sys.executable, "scripts/claim_lint.py"], timeout=30)
    _run([sys.executable, "scripts/check_frontend_js.py"], timeout=30)

    # Evidence files are OUTPUTS of checks performed in this invocation.
    # Previously arbitrary files could claim success without a single HTTP
    # request or Gemini call. Never trust their existing contents.
    uri = urlsplit(args.base_url)
    _require(uri.scheme == "https" and bool(uri.hostname) and not uri.username and not uri.password,
             "Submission freeze requires a public HTTPS deployment")
    _require(uri.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}
             and not uri.hostname.lower().endswith((".local", ".localhost")),
             "Submission freeze refuses loopback/local deployments")
    _require(not uri.path.strip("/") and not uri.query and not uri.fragment,
             "Base URL must be an HTTPS origin without path or query")
    _require(args.min_planner_runs >= 5, "At least five live planner calls required")
    _require(args.live_report.resolve() != args.planner_probe.resolve(), "Evidence output paths must differ")
    _require(args.output.resolve() not in {args.live_report.resolve(), args.planner_probe.resolve()},
             "Submission result must not overwrite evidence")
    # Never unlink arbitrary CLI paths. Freeze evidence is restricted to
    # dedicated release files beneath the project's evaluation directory.
    evaluation_dir = (ROOT / "validation/evaluation").resolve()
    for candidate, exact_name in (
        (args.live_report, "live-deployment-final.json"),
        (args.planner_probe, "planner-probe-final.json"),
        (args.output, "FINAL_SUBMISSION_READY.json"),
    ):
        _require(candidate.parent.resolve() == evaluation_dir and candidate.name == exact_name
                 and not candidate.is_symlink(), "Release evidence paths must use designated evaluation files")
    args.output.unlink(missing_ok=True)
    args.live_report.unlink(missing_ok=True)
    args.planner_probe.unlink(missing_ok=True)
    _run([sys.executable, "scripts/live_deployment_check.py",
          "--base-url", args.base_url, "--expected-release-id", args.expected_release_id,
          "--require-gemini", "--full", "--output", str(args.live_report)], timeout=240)
    # The local SDK probe cannot establish deployed Gemini reliability. Probe
    # fresh *public sessions* against the same release, not the local key.
    _run([sys.executable, "scripts/public_planner_probe.py", "--runs", str(args.min_planner_runs),
          "--base-url", args.base_url, "--expected-release-id", args.expected_release_id,
          "--output", str(args.planner_probe)], timeout=max(300, args.min_planner_runs * 120))
    live = _load(args.live_report)
    probe = _load(args.planner_probe)
    _require(live.get("base_url", "").rstrip("/") == args.base_url.rstrip("/"),
             "Live report origin mismatch")

    _require(live.get("full_judge_path") is True, "Live report is not a full judge-path run")
    _require(live.get("release_id") == args.expected_release_id, "Live release ID does not match the frozen submission release")
    _require(live.get("planner_mode") == "gemini_configured_with_deterministic_fallback", "Live deployment is not configured for bounded Gemini planning")

    required_live_checks = {
        "health",
        "readiness",
        "deep_readiness",
        "homepage",
        "demo_session",
        "analyze",
        "plan",
        "approve_apply_verify",
        "download_hash_binding",
        "security_headers",
        "session_delete",
    }
    checks = live.get("checks") or {}
    missing = sorted(k for k in required_live_checks if checks.get(k) != "PASS")
    _require(not missing, f"Live deployment evidence missing PASS checks: {missing}")
    _require(live.get("fallback_used") is False, "Judge-path planning fell back instead of using Gemini")
    _require(bool(live.get("verified_output_sha256")), "Live verifier output SHA-256 missing")
    _require(live.get("verified_output_sha256") == live.get("downloaded_output_sha256"), "Verified/downloaded artifact SHA mismatch")
    _require(float(live.get("judge_path_total_ms") or 1e18) <= args.max_judge_path_ms, "Live judge path exceeds configured maximum latency")

    _require(probe.get("model") not in (None, ""), "Planner probe does not identify a live model")
    _require(probe.get("model") == live.get("planner_used"), "Public planner model changed between judge-path and probe")
    _require(probe.get("origin") == args.base_url.rstrip("/"), "Planner runs were not performed against public deployment")
    _require(probe.get("release_id") == args.expected_release_id, "Planner runs did not use the frozen release")
    _require(probe.get("proof_mode") == "public_fresh_sessions", "Local planner calls are not deployed evidence")
    runs = int(probe.get("runs") or 0)
    _require(runs >= args.min_planner_runs, f"Planner probe has only {runs} runs; need at least {args.min_planner_runs}")
    _require(int(probe.get("fallback_count") or 0) == 0, "Planner probe observed fallback(s)")
    rows = probe.get("rows") or []
    _require(len(rows) == runs, "Planner probe row count does not match declared runs")
    _require(all(row.get("fallback_used") is False for row in rows), "Planner probe contains a fallback run")
    _require(all(str(row.get("planner_used", "")).startswith("gemini-") for row in rows),
             "Planner probe did not confirm Gemini execution")
    _require(all(row.get("selected_candidate_ids") for row in rows), "Planner probe contains an empty selection")

    selection_counts = probe.get("selection_counts") or []
    top_selection_count = max((int(r.get("count") or 0) for r in selection_counts), default=0)
    stability = (top_selection_count / runs) if runs else 0.0

    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": "SUBMISSION_READY",
        "release_id": args.expected_release_id,
        "verified_public_origin": args.base_url.rstrip("/"),
        "proof_mode": "live_checks_executed_this_invocation",
        "live_report": str(args.live_report),
        "planner_probe": str(args.planner_probe),
        "live_judge_path_ms": live.get("judge_path_total_ms"),
        "verified_output_sha256": live.get("verified_output_sha256"),
        "planner_model": probe.get("model"),
        "planner_runs": runs,
        "planner_fallback_count": probe.get("fallback_count"),
        "planner_modal_selection_share": round(stability, 4),
        "important_interpretation": (
            "SUBMISSION_READY records successful checks performed during this invocation, not independent cryptographic remote-build attestation. "
            "It does not claim universal human readability, accessibility certification, PowerPoint-identical rendering, or that Gemini is superior to the deterministic baseline."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
