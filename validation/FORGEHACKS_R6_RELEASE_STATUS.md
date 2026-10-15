# ForgeHacks R6 — Corrective Release Status

**Date:** 2026-10-08. **Track:** AI + Creativity. **Build type:** corrective, not feature expansion.

## Scope of R6

R6 responds to independently reproduced R5 failures. The primary safety correction recognizes painted empty text boxes as unsupported visible content; this specifically prevents a black opaque box from hiding presentation text while the verifier returns `VERIFIED`. Separate regressions preserve standard unpainted empty text boxes and the baseline demo. Slide-level `showMasterSp=0` suppresses inherited-shape unknowns, without bypassing distinct background-image inventory.

Other changes: degraded deep-readiness now returns HTTP 503; renderer-capacity failures preserve a retryable source session; reanalysis and replanning publish complete snapshots, not partial approvals; per-client intake reservation happens before multipart parsing; session-lock waiters have a finite count and timeout; approval identifiers and retained idempotency keys are bounded; session-creation failures roll back their own directories; additional XML parts are validated before session allocation; and final Gemini stability checks are directed to the deployed public application rather than a local SDK instance.

## Product correctness boundaries

- `VERIFIED` is not a PowerPoint or human readability certification. Structural mapping remains intentionally narrow; unknown objects block whole-deck verification.
- Manually styled headings with ambiguous semantics remain difficult to classify; the R5 small-title regression is retained, but no universal semantic-heading guarantee is asserted.
- On an unsupported object, `REVIEW_REQUIRED` is an acceptable safe result; the normal demo must still be repairable.
- One worker/replica and process-local, ephemeral sessions remain explicit deployment requirements.
- Global rate-limiting/WAF, distributed persistence, multi-replica operation, broad human evaluation and cross-renderer equivalence are beyond this corrective scope.

## Verification

The accompanying evidence JSON reports exact local test outcomes and source/archive SHA-256 hashes. The acceptance criteria are:

1. All non-resource tests pass.
2. Every discovered `resource` test passes in an isolated renderer process, including the new painted-empty-box exploit.
3. Prior unsafe visual exploits and plan/approval/source tamper tests remain green.
4. Compiled code, frontend JavaScript, judge-facing claim lint and local HTTP smoke pass.
5. Source and ZIP content match the frozen source manifest; no secrets are packaged.
6. No claim of public submission readiness unless the real R6 Railway deployment, actual Gemini planning, public multi-run probe, browser demonstration and submission freeze have passed.

## Deployment-only gates still pending

- Public Railway service deployed from the exact R6 source tree with one worker and one replica.
- Real Gemini key configured privately; `/health` configured is not proof of actual model success.
- `scripts/live_deployment_check.py --require-gemini --full` executed against the public HTTPS service and actual R6 release ID.
- `scripts/public_planner_probe.py --runs 5` exercised five fresh public sessions, each with `planner_used` matching a Gemini model and `fallback_used=false`.
- Fresh/incognito browser upload/demo, approval and verified download; public GitHub CI and 2–4-minute video; final Devpost project submission.

**Release status:** locally validated when the attached automated evidence shows all required local gates passing; **NOT `SUBMISSION_READY`** until public evidence exists.
