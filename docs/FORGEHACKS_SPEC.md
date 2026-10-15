# DeckFit AI — ForgeHacks 2026 Product Specification

DeckFit AI is the public product identity. Venue Agent is retained as the historical internal engineering name.

## Track

**AI + Creativity**

Product thesis: **responsive design for physical presentation spaces**.

DeckFit AI explores a new way to create/repair presentation media by making physical viewing geometry an explicit design input.

## Supported V1 loop

1. Securely ingest a PPTX or project-owned demo.
2. Accept active displayed-image height, farthest-viewer distance, and measurement basis.
3. Render and structurally map supported text.
4. Evaluate supported text against the versioned public BDM-derived reference profile.
5. Generate bounded `SCALE_TEXT` candidates for eligible body text only.
6. Simulate every candidate and discard candidates that regress protected text, analysis coverage, or layout.
7. Let the configured bounded planner choose only from remaining candidate IDs.
8. Show the exact plan and simulation evidence.
9. Require explicit approval bound to source + candidates + constraints + simulation.
10. Mutate a copy only.
11. Reopen, rerender, reanalyze, and verify the saved copy.

## Frozen exclusions

- no semantic rewriting;
- no title/heading auto-mutation;
- no arbitrary AI-generated PowerPoint commands;
- no full accessibility/readability guarantee;
- no AVIXA/WCAG certification claim;
- no OCR/image-text repair;
- no chart/SmartArt/table/media repair;
- no multi-replica deployment in competition V1.

## Runtime AI contract

Gemini is a bounded selector, not an authority. It receives derived candidate/context metadata only. It does not receive raw uploaded slide text/screenshots in V1. Its response contains only candidate IDs + rationale; every consequential field is recomputed/validated server-side.

## Release metrics

### Safety
- unsafe `VERIFIED` observed: **must be 0**;
- unauthorized mutation: **must be 0**;
- source mutation: **must be 0**;
- stale/mismatched approval accepted: **must be 0**;
- illegal AI candidate executed: **must be 0**.

### Utility
- project-owned judge demo completes end-to-end repeatedly;
- supported repairable holdout cases must not all collapse to `REVIEW_REQUIRED`;
- a clean supported deck can reach `NO_ACTION_REQUIRED`.

### Model validity
- estimated-boundary cases remain review-only;
- unknown/unsupported visible content cannot reach whole-deck `VERIFIED`;
- public copy never describes `VERIFIED` as human readability/accessibility/certification.

### AI boundary
- schema-invalid/unknown/duplicate candidate output fails closed or falls back;
- planner provenance is exposed;
- live model stability/usefulness is measured separately from safety before final submission.
