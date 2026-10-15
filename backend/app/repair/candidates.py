from __future__ import annotations

from app.domain.models import AnalysisResult, ComparisonState, MutationCapability, RepairCandidate


def generate_candidates(analysis: AnalysisResult) -> list[RepairCandidate]:
    out: list[RepairCandidate] = []
    for r in analysis.results:
        if r.state != ComparisonState.BELOW_TARGET:
            continue
        if r.element.mutation_capability != MutationCapability.SAFE_MUTATION:
            continue
        # Competition V1 auto-mutates ordinary BODY text only. Titles,
        # footers, and other semantic roles remain review-only even if their
        # typography is structurally analyzable.
        if r.element.role != "BODY":
            continue
        if not r.deficit_ratio:
            continue
        # Server-generated bounded options. The model never invents mutation values.
        # Include a modest, medium, and target-seeking option so planning has tradeoffs.
        # Estimated venue measurements use a 5% decision boundary in the analyzer.
        # The target-seeking option therefore needs margin beyond that boundary;
        # otherwise a mathematically improved repair can land in BOUNDARY_REVIEW.
        target_margin = 1.08 if analysis.venue.measurement_basis == "ESTIMATED" else 1.04
        raw_scales = [1.10, 1.25, min(max(r.deficit_ratio * target_margin, 1.0), 1.60)]
        bbox = r.element.structural_bbox
        if bbox is not None:
            x0, y0, x1, y1 = bbox
            cy = (y0 + y1) / 2.0
            visual_region = "UPPER" if cy < 1 / 3 else "LOWER" if cy > 2 / 3 else "MIDDLE"
            box_area_fraction = max(0.0, min(1.0, (x1 - x0) * (y1 - y0)))
        else:
            visual_region = None
            box_area_fraction = None
        seen = set()
        for scale in raw_scales:
            scale = round(scale, 3)
            if scale <= 1.0 or scale > 1.60 or scale in seen:
                continue
            seen.add(scale)
            out.append(RepairCandidate(
                candidate_id=f"{r.element.element_id}-scale-{scale}",
                issue_element_id=r.element.element_id,
                operation="SCALE_TEXT",
                parameters={"scale": scale},
                issue_role=r.element.role,
                deficit_ratio=r.deficit_ratio,
                visual_region=visual_region,
                box_area_fraction=box_area_fraction,
            ))
    return out
