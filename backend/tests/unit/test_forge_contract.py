from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.planner import PlannerProposal
from app.domain.models import (
    AnalysisCapability,
    AnalysisResult,
    AnalysisSummary,
    ComparisonState,
    ElementResult,
    MappingConfidence,
    MutationCapability,
    RepairConstraints,
    TextElement,
    VenueProfile,
)
from app.main import app
from app.repair.candidates import generate_candidates


def test_plan_endpoint_requires_session_capability():
    with TestClient(app) as client:
        created = client.post('/api/demo')
        assert created.status_code == 200
        sid = created.json()['session_id']
        token = created.json()['session_token']

        missing = client.post(f'/api/sessions/{sid}/plan', json={})
        wrong = client.post(f'/api/sessions/{sid}/plan', headers={'X-Venue-Token': 'wrong'}, json={})
        authorized = client.post(f'/api/sessions/{sid}/plan', headers={'X-Venue-Token': token}, json={})

        assert missing.status_code == 404
        assert wrong.status_code == 404
        # Authenticated request reaches the workflow precondition instead.
        assert authorized.status_code == 409


def test_title_protection_cannot_be_disabled_by_client():
    with pytest.raises(ValidationError):
        RepairConstraints(protect_titles=False)


def test_title_issue_never_generates_automatic_candidate():
    element = TextElement(
        element_id='s1-sh2',
        slide_index=0,
        shape_id=2,
        source_text='Important title',
        normalized_text='important title',
        role='TITLE',
        rendered_height_percent=1.0,
        analysis_capability=AnalysisCapability.ANALYZABLE,
        mutation_capability=MutationCapability.SAFE_MUTATION,
        mapping_confidence=MappingConfidence.EXACT,
        explicit_font_sizes_pt=[24.0],
    )
    result = AnalysisResult(
        source_sha256='0' * 64,
        reference_profile_id='test',
        venue=VenueProfile(active_image_height_m=1.8, farthest_viewer_distance_m=10.8, measurement_basis='MEASURED'),
        results=[ElementResult(
            element=element,
            state=ComparisonState.BELOW_TARGET,
            required_percent=2.0,
            actual_percent=1.0,
            deficit_ratio=2.0,
        )],
        summary=AnalysisSummary(
            total_detected_text_elements=1,
            analyzed_elements=1,
            not_analyzed_elements=0,
            below_target_elements=1,
            meets_target_elements=0,
            outside_reference_elements=0,
        ),
    )
    assert generate_candidates(result) == []


def test_model_proposal_schema_has_no_authority_fields():
    with pytest.raises(ValidationError):
        PlannerProposal.model_validate({
            'selected_candidate_ids': ['safe-1'],
            'rationale': 'Pick the candidate.',
            'planner_used': 'pretend-verifier',
            'requires_human_review': False,
        })


def test_model_proposal_rationale_is_bounded():
    with pytest.raises(ValidationError):
        PlannerProposal(selected_candidate_ids=[], rationale='x' * 601)


def test_only_body_text_is_eligible_for_automatic_candidates():
    results = []
    for idx, role in enumerate(['BODY', 'FOOTER', 'OTHER'], start=1):
        element = TextElement(
            element_id=f's1-sh{idx}', slide_index=0, shape_id=idx,
            source_text=role, normalized_text=role.lower(), role=role,
            rendered_height_percent=1.0,
            analysis_capability=AnalysisCapability.ANALYZABLE,
            mutation_capability=MutationCapability.SAFE_MUTATION,
            mapping_confidence=MappingConfidence.EXACT,
            explicit_font_sizes_pt=[12.0],
            structural_bbox=(0.1, 0.2 * idx, 0.8, 0.2 * idx + 0.1),
        )
        results.append(ElementResult(
            element=element, state=ComparisonState.BELOW_TARGET,
            required_percent=2.0, actual_percent=1.0, deficit_ratio=2.0,
        ))
    analysis = AnalysisResult(
        source_sha256='1' * 64,
        reference_profile_id='test',
        venue=VenueProfile(active_image_height_m=1.8, farthest_viewer_distance_m=10.8, measurement_basis='MEASURED'),
        results=results,
        summary=AnalysisSummary(
            total_detected_text_elements=3, analyzed_elements=3,
            not_analyzed_elements=0, below_target_elements=3,
            meets_target_elements=0, outside_reference_elements=0,
        ),
    )
    candidates = generate_candidates(analysis)
    assert candidates
    assert {c.issue_element_id for c in candidates} == {'s1-sh1'}
    assert all(c.visual_region in {'UPPER', 'MIDDLE', 'LOWER'} for c in candidates)
    assert all(c.box_area_fraction is not None for c in candidates)
