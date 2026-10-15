from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.planner import GeminiPlanner
from app.domain.models import ComparisonState, PlanningContext, RepairCandidate, RepairConstraints


def candidate(cid: str, issue: str, scale: float, region: str, area: float, after: float) -> RepairCandidate:
    return RepairCandidate(
        candidate_id=cid,
        issue_element_id=issue,
        issue_role="BODY",
        operation="SCALE_TEXT",
        parameters={"scale": scale},
        safe=True,
        policy_reasons=[],
        predicted_state=ComparisonState.MEETS_TARGET,
        actual_percent_before=0.016,
        actual_percent_after=after,
        simulation_fingerprint=f"probe-{cid}",
        visual_region=region,
        box_area_fraction=area,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe live Gemini bounded-planner stability without presentation content.")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is required; probe does not use mock credentials.")

    candidates = [
        candidate("upper-conservative", "body-upper", 1.15, "UPPER", 0.10, 0.021),
        candidate("lower-conservative", "body-lower", 1.15, "LOWER", 0.18, 0.021),
        candidate("upper-strong", "body-upper", 1.30, "UPPER", 0.10, 0.026),
        candidate("lower-strong", "body-lower", 1.30, "LOWER", 0.18, 0.026),
    ]
    constraints = RepairConstraints(max_mutations=2, max_scale_factor=1.6, minimum_target_coverage=1.0)
    context = PlanningContext(
        analyzed_elements=2,
        meets_target_elements=0,
        below_target_elements=2,
        current_target_coverage=0.0,
        below_target_issue_ids=["body-upper", "body-lower"],
    )
    planner = GeminiPlanner()
    rows = []
    for i in range(args.runs):
        t0 = time.perf_counter()
        decision = planner.choose(candidates, constraints, context)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        rows.append({
            "run": i + 1,
            "selected_candidate_ids": decision.selected_candidate_ids,
            "planner_used": decision.planner_used,
            "fallback_used": decision.fallback_used,
            "fallback_reason": decision.fallback_reason,
            "latency_ms": latency_ms,
        })
    selections = Counter(tuple(r["selected_candidate_ids"]) for r in rows)
    latencies = [r["latency_ms"] for r in rows]
    report = {
        "runs": args.runs,
        "model": planner.model,
        "privacy_boundary": "synthetic candidate metadata only; no slide text/images/files",
        "selection_counts": [{"candidate_ids": list(k), "count": v} for k, v in selections.most_common()],
        "fallback_count": sum(1 for r in rows if r["fallback_used"]),
        "median_latency_ms": statistics.median(latencies) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
        "rows": rows,
    }
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")


if __name__ == "__main__":
    main()
