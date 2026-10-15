from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.domain.models import MutationCapability
from app.pptx.parser import _font_matches, parse_pptx_shapes
from app.security.intake import IntakeError, validate_pptx

ROOT = Path(__file__).resolve().parents[3]
FIX = ROOT / "backend/tests/fixtures/r5"


@pytest.mark.parametrize("filename", [
    "opaque_text_overlay.pptx", "background-image.pptx", "picture-placeholder-repair.pptx",
])
def test_unsupported_visuals_never_disappear_from_inventory(filename):
    records = parse_pptx_shapes(FIX / filename)
    assert any(r.unsupported_visible_content and r.force_not_analyzable for r in records)
    assert all(r.mutation_capability == MutationCapability.NO_MUTATION
               for r in records if r.unsupported_visible_content)


def test_small_manual_title_is_protected():
    recs = parse_pptx_shapes(FIX / "title-exec-simple.pptx")
    assert recs[0].text == "FY27 Financial Overview"
    assert recs[0].role == "TITLE"
    assert recs[1].role == "BODY"


def test_normal_demo_stays_supported():
    recs = parse_pptx_shapes(ROOT / "demo/venue-agent-demo.pptx")
    assert [r.role for r in recs] == ["TITLE", "BODY", "BODY"]
    assert not any(r.unsupported_visible_content for r in recs)


def test_font_family_matching_is_identity_not_substring():
    assert _font_matches("DejaVu Sans", "DejaVuSans-Bold")
    assert _font_matches("AAAAAA+LiberationSans", "Liberation Sans")
    assert not _font_matches("DejaVu Sans", "DejaVu Sans Mono")
    assert not _font_matches("DejaVu Sans", "DejaVu Sans Condensed")
    assert not _font_matches("Liberation Sans", "Liberation Sans Narrow")


def test_broken_presentation_relationship_is_intake_error():
    with pytest.raises(IntakeError, match="missing relationship ID"):
        validate_pptx(FIX / "orphan-slide-relations.pptx")


def test_broken_relationship_rejected_over_http_before_session_creation():
    from app.main import app
    path = FIX / "orphan-slide-relations.pptx"
    with TestClient(app) as c, path.open("rb") as f:
        result = c.post("/api/upload", files={"file": (path.name, f)})
        assert result.status_code == 400, result.text
        assert "relationship" in str(result.json()).lower()


@pytest.mark.resource
@pytest.mark.parametrize("filename", [
    "opaque_text_overlay.pptx", "background-image.pptx", "picture-placeholder-repair.pptx",
])
def test_real_analyzer_rejects_whole_deck_coverage_with_unsupported_visuals(filename, tmp_path):
    from app.venue.analyzer import VenueAnalyzer
    from app.venue.reference import PublicBDMReference
    from app.domain.models import VenueProfile
    a = VenueAnalyzer(PublicBDMReference(ROOT / "reference/PUBLIC_BDM_REFERENCE_V1.json"))
    result = a.analyze(FIX / filename,
                       VenueProfile(active_image_height_m=1.8, farthest_viewer_distance_m=10.8,
                                    measurement_basis="MEASURED"), tmp_path / "analysis")
    assert result.summary.unsupported_visible_content_elements >= 1
    assert result.summary.not_analyzed_elements >= 1

@pytest.mark.resource
@pytest.mark.parametrize("filename", [
    "opaque_text_overlay.pptx", "background-image.pptx", "picture-placeholder-repair.pptx",
])
def test_public_api_never_verifies_deck_with_unmodeled_visual_content(filename):
    from app.main import app
    path = FIX / filename
    with TestClient(app) as client:
        with path.open("rb") as f:
            response = client.post("/api/upload", files={"file": (path.name, f)})
        assert response.status_code == 200, response.text
        sid = response.json()["session_id"]
        auth = {"X-Venue-Token": response.json()["session_token"]}
        try:
            r = client.post(f"/api/sessions/{sid}/analyze", headers=auth,
                json={"venue": {"active_image_height_m": 1.8,
                                "farthest_viewer_distance_m": 10.8,
                                "measurement_basis": "MEASURED"}})
            assert r.status_code == 200, r.text
            payload = r.json()
            assert payload["analysis"]["summary"]["unsupported_visible_content_elements"] > 0
            if payload["state"] != "ANALYZED":
                assert payload["state"] == "REVIEW_REQUIRED"
                return
            plan = client.post(f"/api/sessions/{sid}/plan", headers=auth,
                json={"constraints": {"max_mutations": 2,
                    "max_scale_factor": 1.6, "minimum_target_coverage": 0.75,
                    "protect_titles": True, "semantic_rewrite": False}})
            assert plan.status_code == 200, plan.text
            body = plan.json()
            if body["state"] != "AWAITING_APPROVAL":
                assert body["state"] == "REVIEW_REQUIRED"
                return
            r = client.post(f"/api/sessions/{sid}/approve-and-apply", headers=auth,
                json={"candidate_ids": body["decision"]["selected_candidate_ids"],
                      "plan_hash": body["plan_hash"], "idempotency_key": "r5-adversarial",
                      "approve": True})
            assert r.status_code == 200, r.text
            assert r.json()["state"] == "REVIEW_REQUIRED", r.json()
        finally:
            client.delete(f"/api/sessions/{sid}", headers=auth)
