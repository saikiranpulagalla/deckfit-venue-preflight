from __future__ import annotations

import json
from pathlib import Path

from app.domain.models import RepairCandidate, RepairConstraints, PlanningContext
from app.agent.planner import DeterministicPlanner


def test_planner_study_cases_are_privacy_safe_and_schema_valid(project_root: Path):
    path = project_root / "validation/evaluation/planner_study_cases.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    forbidden = {"source_text", "slide_text", "speaker_notes", "image_bytes", "pptx_bytes", "screenshot"}
    assert raw["cases"]
    for case in raw["cases"]:
        assert not (forbidden & set(case))
        assert not (forbidden & set(case.get("context", {})))
        for candidate in case["candidates"]:
            assert not (forbidden & set(candidate))
        constraints = RepairConstraints.model_validate(case["constraints"])
        context = PlanningContext.model_validate(case["context"])
        candidates = [RepairCandidate.model_validate(c) for c in case["candidates"]]
        # The deterministic baseline must be able to consume every frozen study
        # case; live Gemini is optional and is never needed for release safety.
        DeterministicPlanner().choose(candidates, constraints, context)


def test_planner_ratings_template_does_not_prepopulate_subjective_winners(project_root: Path):
    raw = json.loads((project_root / "validation/evaluation/planner_ratings_template.json").read_text(encoding="utf-8"))
    for rating in raw["ratings"]:
        assert rating["preferred_candidate_ids"] == []


def test_current_release_identity_is_visible_in_server_source(project_root: Path):
    source = (project_root / "backend/app/main.py").read_text(encoding="utf-8")
    assert 'deckfit-nextfounders-rc5-local' in source
    assert '1.1.0-nextfounders' in source


def test_reference_profile_is_bound_to_public_avixa_source(project_root: Path):
    raw = json.loads((project_root / "reference/PUBLIC_BDM_REFERENCE_V1.json").read_text(encoding="utf-8"))
    assert raw["source"] == "https://www.avixa.org/resources/display-image-size-calculators/learn-more-about-display-size"
    assert raw["claim"].lower().startswith("reference profile only")
    assert len(raw["table"]) == 11
    assert raw["table"][0] == {"min_ratio": 0.8, "max_ratio": 1.0, "min_element_percent": 0.5}
    assert raw["table"][-1] == {"min_ratio": 9.0, "max_ratio": 10.0, "min_element_percent": 5.0}
