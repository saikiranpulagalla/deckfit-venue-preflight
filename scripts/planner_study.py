from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.planner import DeterministicPlanner, GeminiPlanner
from app.domain.models import PlanningContext, RepairCandidate, RepairConstraints

DEFAULT_CASES = ROOT / "validation" / "evaluation" / "planner_study_cases.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _decision_row(planner, candidates, constraints, context) -> dict[str, Any]:
    t0 = time.perf_counter()
    decision = planner.choose(candidates, constraints, context)
    return {
        "selected_candidate_ids": decision.selected_candidate_ids,
        "requires_human_review": decision.requires_human_review,
        "unresolved_issue_ids": decision.unresolved_issue_ids,
        "projected_target_coverage": decision.projected_target_coverage,
        "planner_used": decision.planner_used,
        "fallback_used": decision.fallback_used,
        "fallback_reason": decision.fallback_reason,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Run privacy-safe planner study cases against deterministic baseline and optional live Gemini.")
    p.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    p.add_argument("--runs", type=int, default=1, help="Live Gemini repetitions per case; deterministic baseline is run once.")
    p.add_argument("--output", type=Path)
    args = p.parse_args()

    raw = _load(args.cases)
    live_enabled = bool(os.getenv("GEMINI_API_KEY"))
    rows: list[dict[str, Any]] = []
    for case in raw["cases"]:
        constraints = RepairConstraints.model_validate(case["constraints"])
        context = PlanningContext.model_validate(case["context"])
        candidates = [RepairCandidate.model_validate(c) for c in case["candidates"]]
        row: dict[str, Any] = {
            "case_id": case["case_id"],
            "description": case["description"],
            "deterministic": _decision_row(DeterministicPlanner(), candidates, constraints, context),
            "gemini_runs": [],
        }
        if live_enabled:
            for _ in range(max(1, args.runs)):
                # New planner instance per repetition prevents one transient failure
                # from opening a circuit that would bias all later study runs.
                row["gemini_runs"].append(_decision_row(GeminiPlanner(), candidates, constraints, context))
        rows.append(row)

    report = {
        "schema_version": 1,
        "privacy_boundary": raw["privacy_boundary"],
        "live_gemini_enabled": live_enabled,
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash") if live_enabled else None,
        "important_interpretation": (
            "This study characterizes planner choices and stability. It does not claim the AI is better than the deterministic baseline "
            "until blinded human preference ratings are collected separately."
        ),
        "cases": rows,
    }
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
