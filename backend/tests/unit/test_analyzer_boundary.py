from pathlib import Path

from app.domain.models import (
    AnalysisCapability, ComparisonState, MappingConfidence, MutationCapability,
    TextElement, VenueProfile,
)
from app.venue import analyzer as analyzer_module
from app.venue.analyzer import VenueAnalyzer
from app.venue.reference import PublicBDMReference


def test_estimated_measurement_near_threshold_requires_boundary_review(monkeypatch, project_root, tmp_path):
    reference = PublicBDMReference(project_root / 'reference' / 'PUBLIC_BDM_REFERENCE_V1.json')
    required = reference.required_percent(6.0)
    assert required is not None
    element = TextElement(
        element_id='e1', slide_index=0, shape_id=1,
        source_text='x', normalized_text='x', role='BODY',
        rendered_height_percent=required,
        analysis_capability=AnalysisCapability.ANALYZABLE,
        mutation_capability=MutationCapability.SAFE_MUTATION,
        mapping_confidence=MappingConfidence.EXACT,
        structural_bbox=(0,0,1,1), rendered_bbox=(0.1,0.1,0.2,0.2),
        rendered_span_count=1, rendered_line_count=1,
    )
    source = tmp_path / 'source.pptx'; source.write_bytes(b'fixture')
    monkeypatch.setattr(analyzer_module, 'render_pptx_to_pdf', lambda *_: tmp_path/'fake.pdf')
    monkeypatch.setattr(analyzer_module, 'map_elements', lambda *_: [element])
    monkeypatch.setattr(analyzer_module, 'libreoffice_version', lambda: 'fake')

    a = VenueAnalyzer(reference)
    estimated = a.analyze(source, VenueProfile(active_image_height_m=1.0, farthest_viewer_distance_m=6.0, measurement_basis='ESTIMATED'), tmp_path/'e')
    measured = a.analyze(source, VenueProfile(active_image_height_m=1.0, farthest_viewer_distance_m=6.0, measurement_basis='MEASURED'), tmp_path/'m')

    assert estimated.results[0].state == ComparisonState.BOUNDARY_REVIEW
    assert estimated.summary.boundary_review_elements == 1
    assert estimated.summary.analyzed_elements == 0
    assert measured.results[0].state == ComparisonState.MEETS_TARGET


def _analyze_single_percent(monkeypatch, project_root, tmp_path, actual: float, basis: str):
    reference = PublicBDMReference(project_root / 'reference' / 'PUBLIC_BDM_REFERENCE_V1.json')
    element = TextElement(
        element_id='edge', slide_index=0, shape_id=1,
        source_text='x', normalized_text='x', role='BODY',
        rendered_height_percent=actual,
        analysis_capability=AnalysisCapability.ANALYZABLE,
        mutation_capability=MutationCapability.SAFE_MUTATION,
        mapping_confidence=MappingConfidence.EXACT,
        structural_bbox=(0,0,1,1), rendered_bbox=(0.1,0.1,0.2,0.2),
        rendered_span_count=1, rendered_line_count=1,
    )
    source = tmp_path / f'{basis}-{actual}.pptx'; source.write_bytes(b'fixture')
    monkeypatch.setattr(analyzer_module, 'render_pptx_to_pdf', lambda *_: tmp_path/'fake.pdf')
    monkeypatch.setattr(analyzer_module, 'map_elements', lambda *_: [element])
    monkeypatch.setattr(analyzer_module, 'libreoffice_version', lambda: 'fake')
    return VenueAnalyzer(reference).analyze(
        source,
        VenueProfile(active_image_height_m=1.0, farthest_viewer_distance_m=6.0, measurement_basis=basis),
        tmp_path / f'work-{basis}-{actual}',
    )


def test_estimated_boundary_is_conservative_on_both_sides(monkeypatch, project_root, tmp_path):
    reference = PublicBDMReference(project_root / 'reference' / 'PUBLIC_BDM_REFERENCE_V1.json')
    required = reference.required_percent(6.0)
    assert required is not None
    for factor in (0.951, 1.049):
        result = _analyze_single_percent(monkeypatch, project_root, tmp_path, required * factor, 'ESTIMATED')
        assert result.results[0].state == ComparisonState.BOUNDARY_REVIEW
        assert result.summary.analyzed_elements == 0


def test_estimated_case_outside_boundary_can_be_classified(monkeypatch, project_root, tmp_path):
    reference = PublicBDMReference(project_root / 'reference' / 'PUBLIC_BDM_REFERENCE_V1.json')
    required = reference.required_percent(6.0)
    assert required is not None
    below = _analyze_single_percent(monkeypatch, project_root, tmp_path, required * 0.94, 'ESTIMATED')
    above = _analyze_single_percent(monkeypatch, project_root, tmp_path, required * 1.06, 'ESTIMATED')
    assert below.results[0].state == ComparisonState.BELOW_TARGET
    assert above.results[0].state == ComparisonState.MEETS_TARGET
