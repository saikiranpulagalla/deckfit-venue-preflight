# Next Founders — Implementation & release report

**Status: candidate implementation in this archive; not deployed to Railway.**

## Implemented in this revision

- Protected PowerPoint relationship inventory, slide order and notes/comments part preservation checks. Applied to candidate simulation, combined-plan simulation and final independent verification. Deliberately tampered slide-navigation fixture no longer gets `VERIFIED`.
- Offloaded expensive upload validation, hashing and session creation into a bounded Starlette worker pool, keeping lightweight requests responsive. The existing upload reservation remains in force.
- Restricted LibreOffice subprocess environment (does not inherit `GEMINI_API_KEY` or arbitrary `VENUE_*` values) while retaining font/locale/profile settings.
- Refined Gemini circuit breaker: provider/transport failure opens it; invalid individual model proposals cause deterministic fallback without disabling other sessions.
- Improved cleanup-error logging without file paths/tokens.
- Simplified DeckFit AI customer-facing copy, corrected planner runtime label, separated structural-text assessment from full readability, clarified private speaker notes and measurement limitations. Advanced controls and JSON evidence remain available, but are not front-and-center.
- Guarded overlapping UI actions, enabled safe session replacement after the new file is accepted, and disabled stale approval when inputs change. Historical internal environment variable names remain unchanged.
- Migrated current homepage/smoke/claim checks to DeckFit wording, leaving historical ForgeHacks evidence untouched.
- Docker build gate for **Ubuntu USN-8868-1** patched LibreOffice version (`4:24.2.7-0ubuntu0.24.04.7` or newer); actual deployed package/version remains to be verified.

## Invariants

The original deck remains immutable. Titles, unsupported visible objects and uncertain analysis remain review-only. Authorized plans remain bound to the exact source and validated candidate evidence. A different package relationship or protected notes/comments content blocks an unqualified verified result. The product checks defined text geometry, **not contrast, lighting, person-specific readability, WCAG or AVIXA certification**.

## Coverage limits and non-goals

The new package check protects the relationship inventory, slide order, and notes/comments package parts. It is **not** a universal semantic equivalence checker for every PowerPoint extension, metadata field, macro, signature or complex interaction. Ordinary external hyperlinks are currently rejected at intake; no broad permission change was made.

No new candidate-ranking algorithm, chart/title mutation, general accessibility checker, storage cluster, payment gateway, batch event workflow or authenticated preview service was built. Aggregate storage quotas and per-job render cancellation were not implemented; the current session and render caps remain necessary. Live provider testing requires a user's actual `GEMINI_API_KEY` and a deliberately configured release.

## Local validation commands

From the project root:

```bash
python -m pip install -e './backend[dev,agent]'
python scripts/claim_lint.py
python scripts/check_frontend_js.py
python scripts/http_smoke.py
python scripts/release_gate.py --full
```

- Default acceptance: all non-resource unit/adversarial tests, mandatory isolated renderer tests, an end-to-end demo output, and no known false-verified regression.
- **Production pending:** confirm Ubuntu patched LibreOffice package *inside deployed container*, built image/source commit digest, and public screenshot/browser demo. Version strings on `/health` alone are not proof of source identity.
- **Browser pending:** run the actual full workflow on desktop/mobile in an unblocked Chromium environment; some restricted runners block local-browser networking.
- **Customer evidence pending:** independent real target-segment decks, manual comparison, customer interviews, and measured cost/job. Do not publish invented conversion rates, savings or paying users.

## Priorities still open for commercialization

1. Independently demonstrate useful results on at least six independently chosen text-heavy training decks; include refusals and comparison times.
2. Verify licensing route for PyMuPDF and confirm appropriate privacy/document-retention disclosures.
3. Improve measured aggregate workspace/storage and job-level render capacity, then introduce clean durable workers before batch operations.
4. If a market hypothesis survives customer interviews, test proposed credit-based and training-provider pricing. All prices remain hypothetical until validated.

**Do not equate this prototype's software test results with user adoption, commercial readiness or winning probability.**
