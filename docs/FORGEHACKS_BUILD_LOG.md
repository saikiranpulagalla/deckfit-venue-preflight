# ForgeHacks Build Log

Purpose: preserve honest event-period provenance for the Oct. 3–10, 2026 build window.

## Baseline carried into Forge-specific hardening

The source tree used for this build came from the project's v14 archive/evidence line. Preserve the historical evidence files rather than rewriting history.

## Forge-specific hardening implemented in this worktree

- ForgeHacks AI + Creativity positioning and judge-facing copy;
- capability enforcement added to `/plan` in the archived v14 baseline;
- title protection made non-disableable and enforced again during candidate generation;
- model output narrowed from the full `PlanDecision` schema to `candidate IDs + rationale` only;
- unsupported non-text visual shapes represented explicitly so opaque overlays cannot disappear from the verification universe;
- inherited layout/master visuals represented conservatively as unsupported/review-only;
- project-owned demo branding updated without expanding mutation scope;
- claim boundary and release/evaluation documents added.

Before submission, append the final repository commit SHA/tag and measured release report generated from the exact submitted source.

## R1 measured validation

- test collection after Forge hardening: **110**;
- fast/non-resource suite: **86/86 PASS**;
- critical isolated LibreOffice/resource nodes: **13/13 PASS**;
- production-command HTTP smoke: **PASS**;
- Forge claim lint: **PASS**;
- frontend inline JavaScript syntax: **PASS**;
- multi-issue round-trip observed at 28.32s pytest time (30.89s wall), maximum reported RSS 205,284 kB in this local build environment;
- live Gemini with a real key, public Railway resource headroom, browser E2E and real user research remain explicitly unverified here.

The final submitted tag/commit and archive digest are recorded in the external release evidence after the worktree is frozen, avoiding a self-referential source change.

## R2 measured validation

- test collection: **116**;
- fast/non-resource suite: **92/92 PASS**;
- Forge claim lint: **PASS**;
- frontend inline JavaScript syntax: **PASS**;
- production-command HTTP smoke: **PASS**, including real demo-render deep readiness and `forgehacks-r2-dev` release identity;
- utility artifact evidence independently rerun after R2: **4/4 PASS** (single-issue vertical slice, multi-issue plan, already-good no-action path, hand-authored holdout);
- critical artifact safety evidence independently rerun after R2: **3/3 PASS** (image-only never green, opaque overlay blocks `VERIFIED`, unresolved unknown coverage blocks `VERIFIED`);
- offline planner study generated with deterministic baseline; no `GEMINI_API_KEY` was present in this environment, so no live-AI superiority/stability claim is made;
- live Railway deployment, real Gemini calls, browser E2E, production resource headroom and human preference/user research remain explicit external gates.

R2 does not broaden automatic mutation scope. It improves evaluation honesty and release reproducibility around the R1 safety core.

## R4 — submission-gate freeze

R4 intentionally does not broaden the mutation envelope. It adds final public-release evidence controls: stricter live-deployment checking (security headers, no-store/private output, post-delete inaccessibility), persisted planner-probe evidence, and a fail-closed `submission_freeze.py` gate that cannot emit `SUBMISSION_READY` without real hosted Gemini evidence for the exact release ID. Product-core planner/parser/verifier/mutation/analyzer files remain byte-identical to R3.

## Oct 8 — R5 adversarial repair

Independent failure hunts reproduced false `VERIFIED` through opaque text-bearing shapes, slide background images, and populated picture placeholders, as well as the 18pt manual-title mutation, stale readiness, dangling relationship intake, fabricated local submission evidence, anonymous session exhaustion, font substring matching and refresh UX. R5 adds regression fixtures and bounded fixes. Hosting, live Gemini, GitHub CI and fresh-browser results remain external and must not be invented.

## Oct 8 — R6 adversarial corrective release

R5 independent hunts discovered an empty painted text-box false-`VERIFIED`, degraded readiness incorrectly returning HTTP 200, transient renderer capacity poisoning analysis, suppressed master-shape false review, malformed referenced slide-layout XML, expensive admission after quota expiry, unbounded per-session lock waiters, simulation and replanning state inconsistencies, oversized approval fields, orphan directories on failed creation, and local rather than public Gemini stability evidence. R6 implements targeted corrections with new executable regressions and retains prior R5 fixtures. Public live execution remains a separate gate.

## Oct 8 — R7 outlined-surface and publication hardening

An independent R6 audit reproduced an unsafe whole-deck VERIFIED result with a 100pt border on a populated text box obscuring body text. R7 unifies painted-surface classification for both populated and empty text frames, adds the original adversarial PPTX to mandatory isolated real-artifact regression tests, bounds upload-body receipt with idle and absolute deadlines, places security-header middleware outside early admission, adds explicit proxy-chain parsing protections, and allows capability-protected plan recovery after refresh. External Railway ingress fairness and live Gemini remain unverified and should not be presented as measured.

## Oct 9 — R8 theme, integrity and lifecycle corrections

After two R7 adversarial audits, the next release adds theme-style surface inventory, hidden-slide-to-PDF index verification, non-convoying pending session reservations, acknowledged byte deletion with retry, frontend deletion retry, required OPC content-type validation and bounded ZIP member integrity checks. Previous R7 source remains frozen; new fixtures are included with R8 tests. Public hosted checks and Gemini are not claimed.
