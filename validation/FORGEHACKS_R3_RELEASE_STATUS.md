# ForgeHacks R3 Release Status

## Verdict

**R3 LOCAL RELEASE GATE: PASS WITH EXTERNAL DEPLOYMENT LIMITATIONS**

R3 preserves the bounded V1 product scope and adds deployment/judge-path integrity rather than new mutation features.

## Measured local evidence

- `119` pytest tests collected.
- Fast non-resource suite: **95/95 PASS**.
- Production-command HTTP smoke: **PASS**.
- Frontend JavaScript syntax: **PASS**.
- ForgeHacks claim lint: **PASS**.
- Offline planner study: **PASS** with no live Gemini calls when no credential is configured.
- Offline evaluation scoreboard: fast safety/model-validity/AI-boundary groups **PASS**.
- Local production-style full judge-path check: **PASS**.
  - health/readiness/deep-readiness: PASS;
  - project demo creation: PASS;
  - analyze: PASS;
  - plan: PASS;
  - approve/apply/fresh verify: PASS;
  - verified-output SHA-256 equals downloaded-output SHA-256: PASS;
  - local measured judge-path request time after session creation: ~24.5 s in the validation environment.

## Isolated real-artifact evidence rerun after R3 changes

The environment can stall when many LibreOffice pytest subprocesses are chained in one outer command, so resource cases were also run as isolated nodes. The following passed after the R3 changes:

- full closed-loop API flow including output download and post-verification tamper rejection;
- multi-issue demo plan and verification;
- duplicate text rendered-identity mapping;
- overlap/wrap false-VERIFIED prevention;
- missing-font automatic-mutation refusal;
- table text explicit not-analyzed handling;
- target-seeking scale overlap/wrap rejection;
- unresolved unknown content blocking whole-deck VERIFIED;
- opaque visual overlay blocking whole-deck VERIFIED;
- image-only REVIEW_REQUIRED behavior;
- outside-reference REVIEW_REQUIRED behavior;
- real-render deep readiness;
- holdout contract;
- prompt-injection content treated as data;
- no-action/outside-range handling.

## R3 closures

1. **Verified/downloaded artifact binding** — verifier output SHA-256 is retained with the session and the output bytes are re-hashed immediately before download. A mismatch deletes the output, clears its digest, marks the session failed, and returns HTTP 409.
2. **Download evidence surface** — successful output responses expose `X-Venue-Output-SHA256`, allowing the external deployment checker to prove byte-for-byte equality with the verifier report.
3. **Deployment reproducibility** — `railway.json` fixes Dockerfile build, deep-readiness deployment health check, and restart policy.
4. **Live deployment verifier** — `scripts/live_deployment_check.py` checks release identity, renderer readiness, homepage claims, the exact demo/analyze/plan/approve/verify loop, source immutability, and downloaded-artifact hash binding.
5. **Planner provenance visibility** — judge UI visibly distinguishes `Gemini bounded` from `deterministic fallback`.
6. **One-replica runbook** — deployment documentation explicitly requires one Railway replica and one worker because session state is process-local.

## Intentionally unchanged scope

- automatic mutation remains ordinary supported BODY text only;
- automatic operation remains bounded `SCALE_TEXT` only;
- titles/headings remain review-only;
- semantic rewriting remains disabled;
- Gemini may select only legal server-generated candidate IDs and may not certify output;
- unknown/unsupported content cannot be promoted to whole-deck `VERIFIED`.

## Not verified in this execution environment

These remain external gates and must not be presented as completed evidence until measured on the final public deployment:

- Railway deployment of the exact frozen R3 tree;
- actual Railway memory/CPU headroom under LibreOffice load;
- confirmed Railway service scale setting of exactly one replica;
- live Gemini planner with the real competition credential;
- repeated live Gemini planner stability/usefulness measurements;
- fresh/incognito browser E2E against the final public URL;
- real user-research findings;
- final 2–4 minute video and Devpost links.

## Release rule

Do not record the final submission video until `scripts/live_deployment_check.py --require-gemini --full` passes against the exact public release ID used in the submission.
