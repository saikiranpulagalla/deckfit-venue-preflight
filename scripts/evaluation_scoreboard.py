from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

FAST_GROUPS = {
    "safety": [
        "tests/unit/test_domain.py",
        "tests/unit/test_forge_contract.py",
        "tests/unit/test_plan_integrity.py",
        "tests/adversarial/test_planner_boundary.py",
        "tests/unit/test_v14_http_security.py",
    ],
    "model_validity": [
        "tests/unit/test_analyzer_boundary.py",
        "tests/unit/test_reference.py",
        "tests/unit/test_reference_properties.py",
        "tests/unit/test_parser_safety_contract.py",
    ],
    "ai_boundary": [
        "tests/unit/test_gemini_planner_adapter.py",
        "tests/unit/test_forge_contract.py",
    ],
}

RESOURCE_GROUPS = {
    "utility": [
        "tests/integration/test_vertical_slice.py::test_full_vertical_slice_small_text",
        "tests/integration/test_multi_plan_demo.py::test_demo_requires_and_verifies_multi_issue_plan",
        "tests/integration/test_no_action_and_range.py::test_safe_deck_generates_no_repair_at_moderate_ratio",
        "tests/integration/test_holdout_contract.py::test_hand_authored_holdout_contract",
    ],
    "safety_artifact": [
        "tests/integration/test_vertical_slice.py::test_image_only_is_never_green",
        "tests/integration/test_v12_safety_roundtrip.py::test_opaque_visual_overlay_blocks_whole_deck_verified",
        "tests/integration/test_v12_safety_roundtrip.py::test_unknown_content_remaining_after_successful_target_repair_cannot_be_verified",
    ],
}


def run_node(node: str, resource: bool, timeout: int) -> dict:
    session_root = Path(tempfile.gettempdir()) / f"venue-scoreboard-{os.getpid()}-{time.time_ns()}"
    env = os.environ.copy()
    env["VENUE_SESSION_ROOT"] = str(session_root)
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if resource:
        cmd += ["-m", "resource"]
    cmd.append(node)
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=BACKEND, env=env, capture_output=True, text=True, timeout=timeout)
        status = "PASS" if p.returncode == 0 else "FAIL"
        return {
            "node": node,
            "status": status,
            "returncode": p.returncode,
            "duration_s": round(time.perf_counter() - t0, 2),
            "tail": ((p.stdout or "") + "\n" + (p.stderr or ""))[-1200:].strip(),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "node": node,
            "status": "TIMEOUT",
            "returncode": None,
            "duration_s": round(time.perf_counter() - t0, 2),
            "tail": str(exc),
        }


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a release scoreboard without collapsing safety, utility, model-validity and AI-boundary evidence into one accuracy number.")
    ap.add_argument("--include-resource", action="store_true")
    ap.add_argument("--resource-only", action="store_true", help="Run only isolated resource/LibreOffice evidence nodes.")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    if args.resource_only:
        args.include_resource = True

    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": "PASS means the mapped evidence nodes passed; it is not a universal readability/accessibility claim.",
        "groups": {},
    }
    if not args.resource_only:
        for group, nodes in FAST_GROUPS.items():
            rows = [run_node(n, False, 60) for n in nodes]
            report["groups"][group] = {
                "status": "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL",
                "nodes": rows,
            }
    else:
        for group in FAST_GROUPS:
            report["groups"][group] = {"status": "NOT_RUN", "nodes": []}
    if args.include_resource:
        for group, nodes in RESOURCE_GROUPS.items():
            rows = [run_node(n, True, 120) for n in nodes]
            report["groups"][group] = {
                "status": "PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL",
                "nodes": rows,
            }
    else:
        for group in RESOURCE_GROUPS:
            report["groups"][group] = {"status": "NOT_RUN", "nodes": []}

    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if any(v["status"] == "FAIL" for v in report["groups"].values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
