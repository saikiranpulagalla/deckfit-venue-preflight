# ForgeHacks R4 Release Status

## Verdict

**R4 LOCAL SUBMISSION-GATE: PASS WITH EXTERNAL PUBLIC-DEPLOYMENT EVIDENCE STILL REQUIRED**

R4 does not expand automatic mutation scope. It tightens the final public evidence path and refuses to declare the submission ready until the exact hosted release and live Gemini planner are measured.

## Measured R4 local evidence

- `121` pytest tests collected.
- Non-resource suite: **97/97 PASS**.
- ForgeHacks claim lint: **PASS**.
- Frontend JavaScript syntax check: **PASS**.
- Source-secret scan: **PASS** with zero findings.
- Required release documents: **PASS**.
- Python compileall for backend/scripts: **PASS**.
- Full production-style local judge path: **PASS**.
  - health/readiness/deep-readiness: PASS;
  - security headers: PASS;
  - judge-facing ForgeHacks homepage claims: PASS;
  - project-owned demo session: PASS;
  - analyze: PASS;
  - plan: PASS;
  - approve/apply/fresh verify: PASS;
  - verifier SHA-256 equals downloaded PPTX SHA-256: PASS;
  - explicit session delete: PASS;
  - post-delete output access: correctly unavailable.
- Local production-style judge-path request time after demo-session creation in the R4 check: **31.75 s**.
- Real-artifact vertical-slice rerun after R4 metadata/tooling changes: **PASS**.
- `scripts/submission_freeze.py` unit contract: complete external evidence accepted; planner fallback evidence rejected.
- Actual repository freeze gate without public evidence: **correctly FAILS CLOSED** and does not create `FINAL_SUBMISSION_READY.json`.

## Product-core inheritance from R3

R4 changes release/evidence tooling and release identifiers, not the repair engine. The following product-core files are byte-identical to the R3 frozen release:

- `backend/app/agent/planner.py`
- `backend/app/pptx/parser.py`
- `backend/app/repair/verifier.py`
- `backend/app/pptx/mutations.py`
- `backend/app/venue/analyzer.py`

`backend/app/main.py` differs from R3 only in the default release ID and FastAPI version string. The R3 artifact/adversarial evidence therefore remains directly relevant to the unchanged product core, while R4 additionally validates the stricter public judge checker and submission-freeze tooling.

## R4 additions

1. `scripts/live_deployment_check.py` now validates restrictive security headers, private/no-store download behavior, PPTX response type, explicit session deletion, and post-delete inaccessibility in addition to the R3 judge path.
2. `scripts/planner_probe.py` can persist a source-independent live planner-stability report with `--output`.
3. `scripts/submission_freeze.py` is a fail-closed final gate. It requires a full public judge-path report for the exact release ID, bounded Gemini with no fallback, artifact hash binding, security/deletion checks, acceptable judge-path latency, and a multi-run live planner probe with zero fallbacks.
4. `docs/FINAL_JUDGE_RUNBOOK.md` provides the exact deployment/evidence sequence.
5. `docs/DEVPOST_SUBMISSION_TEMPLATE.md` keeps public claims tied to measured evidence rather than placeholders or inferred numbers.

## Deliberately unchanged product scope

- automatic mutation: supported BODY text `SCALE_TEXT` only;
- titles/headings: review-only;
- semantic rewriting: disabled;
- Gemini authority: legal candidate IDs and concise rationale only;
- whole-deck `VERIFIED`: impossible while unsupported/unknown coverage remains unresolved.

## External gates that remain open

R4 must not be called `SUBMISSION_READY` until all of the following exist for the final public URL:

- exact R4 source snapshot deployed;
- Railway one-replica setting manually confirmed;
- real Gemini credential active (`planner_mode=gemini_bounded`);
- `validation/evaluation/live-deployment-final.json` from `--require-gemini --full`;
- `validation/evaluation/planner-probe-final.json` from repeated live calls with zero fallback;
- fresh/incognito manual browser pass;
- final public/unlisted 2–4 minute video;
- reachable public source repository.

The repository intentionally contains no fabricated public-deployment PASS record.
