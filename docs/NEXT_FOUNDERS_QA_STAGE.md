# Next Founders — release acceptance and deployment handoff

**Date:** 12 October 2026. **Status:** local release candidate; NOT a Railway deployment and NOT proof of public Gemini use.

## Scope of this increment

The preceding Next Founders implementation corrected package integrity, async upload validation, renderer environment inheritance, Gemini fallback, and customer wording. This follow-up adds **input-revision guards** to the browser UI. If room measurements or repair limits change while an analysis or plan request is outstanding, its later response cannot re-enable a stale repair approval. A completed approval from earlier inputs carries an explicit warning. The active GitHub Actions workflow's displayed title now reads DeckFit AI.

## Source-bound QA

Run from the project root:

```bash
python scripts/claim_lint.py
python scripts/check_frontend_js.py
python scripts/http_smoke.py
python scripts/release_gate.py --full
```

The `--full` suite is source-bound and runs LibreOffice tests in separate processes. Preserve its final console log with the exact release commit or archive digest. A successful test run does not prove that the Railway container runs these exact bytes.

The QA investigator also exercised the unchanged server API from an actual Chromium DOM with a **local Python HTTP bridge** because direct Chromium navigation was blocked by the execution environment. The bridged test is useful evidence for real UI event handling and response-state transitions, but **not a substitute for a normal browser-to-production E2E test**.

Two browser scenarios are required for every future frontend change:

1. Demo → Analyze → Plan → Approve → `VERIFIED`, with a genuine downloaded output.
2. Change active image height while an analysis request is in flight. When the old reply arrives, planning must remain disabled and the UI must require reanalysis. Similarly, changing constraints during planning must not revive approval.

## Deployment, separate from local QA

1. Commit and push this exact source to the intended GitHub repository. Do not accidentally overwrite another Railway service or deploy the historical ForgeHacks release.
2. In Railway, select the correct service and GitHub branch. Use the root `Dockerfile`, **one replica and one Uvicorn worker**; the session store is process-local. Set `VENUE_RELEASE_ID` to a unique release/commit identifier. `GEMINI_API_KEY` is optional; do not include it in the repository or screenshots.
3. Confirm that Docker builds and the Ubuntu 24.04 LibreOffice security-version floor is met **inside the actual deployed image**. `/health/deep-readiness` does not attest to the Ubuntu security package version.
4. Verify `/health`, `/health/readiness`, `/health/deep-readiness`, the homepage, and a genuine new-session demo. Then run the source-provided live check:

```bash
python scripts/live_deployment_check.py --base-url https://YOUR-ACTUAL-SERVICE.up.railway.app --expected-release-id YOUR_EXACT_RELEASE_ID --full --output validation/next-founders-public-check.json
```

5. In an ordinary browser, check desktop/mobile upload and demo, analyze, plan, approval, download, deletion, refresh and rejected/unsupported files. Verify the real downloaded PPTX SHA-256. If claiming actual Gemini runtime in the video, independently inspect the selected plan's `planner_used` provenance; configuration alone is not evidence of Gemini use.
6. Capture authentic screenshots and record the five-minute Next Founders video **only from the verified deployed build**. Do not invent customer interviews, pricing validation, contrast assessments or certification.

## Remaining release blockers external to this archive

- Railway deploy identity, container security packages, production URLs and public browser flow have not been independently established.
- Native direct-network browser acceptance is still required; the local Chromium bridge does not cover browser network/CORS conditions.
- Real target-customer deck usefulness, third-party licensing strategy, cost per customer job, and buyer feedback remain unverified.

The initial business segment is **repeat presenters and text-heavy training providers**. A conference-wide batch workflow is a future direction, not an implemented capability.
