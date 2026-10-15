# Final Judge Runbook — ForgeHacks 2026

This runbook is intentionally short. Do not add features once the R4 submission gate exists.

## Public release preconditions

1. Deploy the exact frozen source snapshot.
2. Keep exactly one Railway replica and one Uvicorn worker.
3. Set `VENUE_MAX_CONCURRENT_RENDERS=1`.
4. Set `VENUE_RELEASE_ID=forgehacks-r8-<source-prefix>`.
5. Configure `GEMINI_API_KEY` as a host secret and use the validated public planner model `GEMINI_MODEL=gemini-3.5-flash-lite`.
6. Confirm `/health` reports `planner_mode=gemini_configured_with_deterministic_fallback` and the exact release ID.

## Evidence commands

```bash
python scripts/live_deployment_check.py \
  --base-url https://YOUR-SERVICE.up.railway.app \
  --expected-release-id forgehacks-r8-<source-prefix> \
  --require-gemini --full \
  --output validation/evaluation/live-deployment-final.json

python scripts/planner_probe.py \
  --runs 10 \
  --output validation/evaluation/planner-probe-final.json

python scripts/submission_freeze.py \
  --base-url https://YOUR-SERVICE.up.railway.app \
  --expected-release-id forgehacks-r8-<source-prefix>
```

Do not record the final video until the third command returns `SUBMISSION_READY`.

## Fresh-browser manual pass

Use a logged-out/incognito browser and verify:

- homepage loads without authentication;
- release ID and `Runtime planner: Gemini bounded` are visible;
- project-owned demo starts with one click;
- no capability token appears in the URL/history;
- analysis shows at least one supported below-target BODY issue;
- plan exposes bounded candidate selection and a concise rationale;
- approval is explicit;
- final state is `VERIFIED` only after save/reopen/re-analysis;
- the visible limitation states that `VERIFIED` is a supported structural claim only;
- repaired-copy download succeeds;
- deleting the session makes the prior output unavailable;
- refresh within the same tab behaves as documented.

## Judge story

Use one sentence per rubric:

- **Impact:** presentations that look fine on a laptop can fail in a physical room.
- **AI:** Gemini chooses among pre-simulated safe repair alternatives using privacy-safe hierarchy metadata.
- **Innovation:** physical viewing geometry becomes an input to presentation design — a bounded first step toward room-responsive media.
- **Execution:** original stays immutable; approval is exact; output is reopened and independently rechecked.
- **Communication:** show the entire loop before explaining implementation details.

## Claim boundary

Never say DeckFit AI proves universal human readability, accessibility/WCAG compliance, AVIXA certification, or identical Microsoft PowerPoint rendering. `VERIFIED` means only the saved copy satisfies the implemented supported structural postconditions against the selected reference profile. The live interface may retain the internal Venue Agent name.

R5: `planner_mode=gemini_configured_with_deterministic_fallback` means a key was configured, **not** that a request succeeded. The full checker records actual `planner_used` and `fallback_used`.
