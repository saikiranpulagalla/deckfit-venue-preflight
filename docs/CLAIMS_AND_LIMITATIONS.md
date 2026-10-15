# DeckFit AI — Claims and Limitations

DeckFit AI is the public ForgeHacks product identity. Venue Agent remains the internal engineering name used by the deployed service and code.

DeckFit AI compares structurally supported rendered text against a selected, versioned public BDM-derived reference profile and user-supplied venue geometry.

## What the product may claim

- it measured supported rendered text under the supplied venue/reference model;
- a supported element is below/meets that named reference target;
- a bounded candidate is mechanically safe under implemented simulation checks;
- an exact approved mutation was applied to a copy;
- the saved output passed or failed the implemented verification postconditions.

## What `VERIFIED` does not mean

It is **not**:

- a guarantee that every person can read the slide;
- accessibility or WCAG conformance;
- AVIXA certification or conformance with the complete current ANSI/AVIXA standard;
- proof that LibreOffice renders identically to Microsoft PowerPoint;
- evaluation of individual acuity, viewer age, luminance, contrast, glare, ambient lighting, all viewing angles, or every visual task.

## Unsupported/review-only presentation content

V1 does not auto-repair OCR/image text, tables, charts, SmartArt/diagrams, media/OLE content, grouped/unsupported visuals, unsupported rotations, RTL/non-Latin shaping, inherited/uncertain typography, AutoFit uncertainty, font substitution, ambiguous rendered mapping, or inherited layout/master visuals.

These are represented conservatively where detectable and prevent a whole-deck `VERIFIED` state.

## Measurement uncertainty

`ESTIMATED` venue measurements use a decision boundary around the reference threshold. Near-boundary elements become `BOUNDARY_REVIEW` rather than receiving false certainty. Users remain responsible for entering active displayed-image height rather than merely physical screen dimensions.
