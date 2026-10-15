# ForgeHacks R2 Release Status

## Release intent

This is the ForgeHacks 2026 · AI + Creativity hardening release of Venue Agent. The safety model stays deliberately narrow: automatic mutation is limited to supported ordinary BODY text and `SCALE_TEXT`; titles/headings, semantic rewriting, unsupported visible content, and uncertain cases remain non-automatic.

## Verified in this build environment

- Test collection: **116 tests**.
- Fast/non-resource suite: **92/92 PASS**.
- Critical isolated LibreOffice/resource gates exercised after the Forge changes: **13/13 PASS**:
  - real PPTX vertical slice: 2/2;
  - multi-issue constrained plan + exact approval + fresh verification: 1/1;
  - duplicate-text rendered-identity mapping: 1/1;
  - v12 wrap/font/table/target-seeking/unknown-content/opaque-overlay safety cases: 6/6;
  - image-only/outside-reference terminal-state API: 2/2;
  - deep real-render readiness: 1/1.
- Forge contract unit coverage includes:
  - `/plan` requires the session capability;
  - `protect_titles=False` is rejected by schema;
  - title issues never produce automatic candidates;
  - model proposal schema cannot claim verifier authority;
  - only BODY text is automatically repairable;
  - planner candidates contain privacy-safe visual-region/box-area metadata.
- HTTP production-command smoke: **PASS**.
- Observed multi-issue round-trip command: **28.32s pytest time / 30.89s wall time**, maximum reported RSS **205,284 kB** in this build environment. This is local process evidence, not a claim about total Railway container memory.
- `/health/readiness`: **PASS**, includes release identity, one-replica contract and renderer concurrency.
- `/health/deep-readiness`: **PASS**, including a real project-owned demo render.
- Frontend inline JavaScript syntax: **PASS**.
- Forge judge-facing claim lint: **PASS**.
- `git diff --check`: **PASS**.

## Forge-specific failures closed

1. **Session authorization:** planning now requires the same capability token as the other session operations.
2. **Title authority:** title protection is an invariant, not a user option; titles/headings never auto-mutate.
3. **Semantic-scope regression:** automatic repair remains BODY-only `SCALE_TEXT`; no shortening, rewriting, split-slide, or move-to-notes operation was introduced.
4. **Opaque visual omission:** visible non-text slide objects and explicit layout/master visuals are represented as unsupported coverage, so they cannot silently disappear while whole-deck verification goes green.
5. **AI authority boundary:** Gemini returns only bounded candidate IDs plus a short rationale. Coverage, review state, safety and verification are reconstructed server-side.
6. **AI privacy boundary:** no raw PPTX, slide screenshot, speaker notes, or slide text is sent to the planner. It receives only candidate metadata, constraints and aggregate planning context.
7. **Judge-facing claim scope:** `VERIFIED` is explicitly limited to supported structural postconditions; no readability, accessibility/WCAG, PowerPoint identity, AVIXA certification, or universal-viewer claim is made.
8. **Forge identity:** public UI/docs use ForgeHacks 2026 · AI + Creativity framing rather than the prior competition branding.
9. **Deployment identity:** health/readiness/deep-readiness expose `VENUE_RELEASE_ID`; the page footer displays the live release/planner mode.
10. **Low-memory default:** LibreOffice rendering defaults to one concurrent render. Competition V1 still requires one worker and one deployment replica because session state is process-local.
11. **Release tooling:** mandatory resource tests are isolated one pytest process per critical node to avoid cross-test LibreOffice finalization contamination in constrained runners.
12. **CI:** GitHub Actions installs LibreOffice and runs compile, claim lint, frontend syntax, mandatory release gate and production-command HTTP smoke.

## R2 evaluation hardening

- Added a machine-readable evaluation scoreboard that keeps safety, utility, model-validity and AI-boundary evidence separate.
- Added privacy-safe synthetic planner-study cases and a live-Gemini study harness.
- Added a blank human-ratings template; the release explicitly forbids claiming AI superiority until real blinded preference ratings exist.
- Added stronger estimated-measurement boundary tests on both sides of the decision margin.
- Added a release contract test binding the public reference profile to the documented AVIXA source/table shape.
- Confirmed the core utility artifact paths still pass independently after R2 changes: single-issue vertical slice, multi-issue demo, already-good no-action path, and hand-authored holdout.
- Confirmed critical artifact safety cases still pass independently: image-only never green, opaque overlay blocks whole-deck verification, and unresolved unknown content blocks `VERIFIED`.

## Evaluation scoreboards

### Safety — zero-tolerance

- false/unsupported `VERIFIED`: target **0**;
- unauthorized mutation/access: target **0**;
- source/original mutation: target **0**;
- automatic title mutation: target **0**;
- illegal AI candidate execution: target **0**;
- stale/tampered approval acceptance: target **0**.

### Utility

Safety is not counted as success by refusing everything. The project-owned supported demo must remain repairable and reach the expected terminal result after the safety hardening. The multi-issue demo currently passes that gate.

### Model validity / claims

`VERIFIED` means the supported saved-artifact structural postconditions passed against the selected reference profile. It does **not** predict individual human readability or certify accessibility, WCAG, Microsoft PowerPoint rendering identity, AVIXA compliance, lighting/glare/contrast, or unsupported visual content.

### AI contribution

The live model is useful only as a bounded preference layer among server-generated, already-simulated alternatives. `scripts/planner_probe.py` measures repeated live selection stability/latency for one probe scenario. `scripts/planner_study.py` adds multiple frozen synthetic cases and records the deterministic baseline beside optional live Gemini runs. Neither script is evidence that AI is better until independent blinded human preference ratings are collected.

## Not verified in this execution environment

1. the complete 24-test resource suite in one uninterrupted outer wrapper after the Forge changes; critical resource nodes above were run independently and passed;
2. Docker/Podman image build/runtime (container runtime availability is environment-dependent);
3. the public Railway deployment after this Forge release is pushed;
4. live Gemini planner calls with the user's real credential, including stability/usefulness measurements;
5. real user-research evidence;
6. unrestricted Chromium/Playwright browser E2E;
7. actual Railway RAM/CPU headroom under concurrent LibreOffice load;
8. multi-replica operation — explicitly unsupported by competition V1;
9. final ForgeHacks video/Devpost submission.

## Release commands

```bash
python scripts/claim_lint.py
python scripts/check_frontend_js.py
python scripts/release_gate.py
python scripts/release_gate.py --full
python scripts/http_smoke.py
python scripts/release_candidate.py
# Optional, requires a real key and sends only synthetic candidate metadata:
python scripts/planner_probe.py --runs 10
python scripts/planner_study.py --runs 5 --output validation/evaluation/planner-study-live.json
python scripts/evaluation_scoreboard.py --output validation/evaluation/offline-scoreboard-fast.json
```

The long release gate intentionally uses fresh pytest processes for LibreOffice/resource nodes. In constrained wrappers, run the resource nodes independently rather than treating an outer-wrapper timeout as a product test failure.
