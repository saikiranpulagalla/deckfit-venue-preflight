from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]


def _live_report(release_id: str) -> dict:
    return {
        "full_judge_path": True,
        "release_id": release_id,
        "planner_mode": "gemini_bounded",
        "fallback_used": False,
        "verified_output_sha256": "a" * 64,
        "downloaded_output_sha256": "a" * 64,
        "judge_path_total_ms": 35000.0,
        "checks": {
            "health": "PASS",
            "readiness": "PASS",
            "deep_readiness": "PASS",
            "homepage": "PASS",
            "demo_session": "PASS",
            "analyze": "PASS",
            "plan": "PASS",
            "approve_apply_verify": "PASS",
            "download_hash_binding": "PASS",
            "security_headers": "PASS",
            "session_delete": "PASS",
        },
    }


def _probe(fallback_count: int = 0) -> dict:
    rows = [
        {
            "run": i + 1,
            "selected_candidate_ids": ["upper-conservative", "lower-conservative"],
            "planner_used": "gemini-3.8-flash",
            "fallback_used": fallback_count > 0 and i == 0,
            "fallback_reason": "test" if fallback_count > 0 and i == 0 else None,
            "latency_ms": 100.0,
        }
        for i in range(5)
    ]
    return {
        "runs": 5,
        "model": "gemini-3.8-flash",
        "selection_counts": [{"candidate_ids": ["upper-conservative", "lower-conservative"], "count": 5}],
        "fallback_count": fallback_count,
        "rows": rows,
    }


def test_submission_freeze_rejects_fabricated_local_evidence_without_live_url(tmp_path: Path) -> None:
    release_id = "forgehacks-r4-test"
    live = tmp_path / "live.json"
    probe = tmp_path / "probe.json"
    out = tmp_path / "ready.json"
    live.write_text(json.dumps(_live_report(release_id)), encoding="utf-8")
    probe.write_text(json.dumps(_probe()), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/submission_freeze.py",
            "--expected-release-id",
            release_id,
            "--live-report",
            str(live),
            "--planner-probe",
            str(probe),
            "--output",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert not out.exists()


def test_submission_freeze_rejects_live_planner_fallback(tmp_path: Path) -> None:
    release_id = "forgehacks-r4-test"
    live = tmp_path / "live.json"
    probe = tmp_path / "probe.json"
    out = tmp_path / "ready.json"
    live.write_text(json.dumps(_live_report(release_id)), encoding="utf-8")
    probe.write_text(json.dumps(_probe(fallback_count=1)), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/submission_freeze.py",
            "--expected-release-id",
            release_id,
            "--live-report",
            str(live),
            "--planner-probe",
            str(probe),
            "--output",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode != 0
    assert not out.exists()
    assert "base-url" in (result.stdout + result.stderr).lower()
