# DeckFit AI RC4 — bounded remediation release

Date: 2026-10-13 (India). Baseline: `deckfit-ai-next-founders-rc3-fixed.zip` SHA-256 `8b80262df97ad258dc69d2a5b63e94ab7aeaf42f73b13fc062397e5c5db7a65d`.

## Changes

1. **OOXML relationship intake** (`backend/app/security/intake.py`): reject duplicate or malformed relationship identifiers, incorrect relationship root/namespace/element, absent required attributes, invalid target modes, and dangling targets. Validate logical `p:sldIdLst` identities, typed presentation-to-slide relationships, unique slide targets, and report actual declared slide count before allocating a session. Keep pre-existing ZIP, media, path, size, and external-resource limits.
2. **Failed-replan output retention** (`backend/app/main.py`): invalidate prior approval on replanning but retain the verified artifact until the proposed replacement plan passes combined simulation. On an ordinary planning or combined-simulation exception, restore the previous terminal state without restoring the old approval. Non-feasible/no-action results may retain the previous output and explicitly return `previous_output_retained`.
3. **Decision provenance** (`backend/app/storage/sessions.py`, `backend/app/main.py`, frontend): preserve the original server-validated `PlanDecision` and restore it in `pending_plan` instead of manufacturing a generic `saved_plan` rationale.
4. **Admission cleanup**: clean physically expired session roots before using their old count to reject first-attempt upload admission, keeping atomic quotas and cleanup retry semantics.
5. **Exclusive session-root ownership**: acquire an OS advisory lock before startup cleanup and refuse a second live store on the same root. Release on clean lifespan shutdown; reacquire on lifespan restart. The Windows locking path is implemented but has not been executed in this Linux test environment.
6. **Operational contracts**: degraded `/health/readiness` returns 503 rather than HTTP 200; HTML app shell explicitly requests cache revalidation.
7. **Complete font-scale verification**: each eligible explicit run on an approved shape must receive its expected scale when precise expected scales are supplied, rather than accepting an unchanged run. All unrelated appearance and package changes remain prohibited.
8. **Release identity**: default local ID `deckfit-nextfounders-rc4-local`; use a unique immutable deployed commit/image ID in `VENUE_RELEASE_ID`.

## Executed checks

- **174/174 non-resource tests** passed locally (41 resource-marked tests excluded).
- Newly added tests: malformed OPC variants, logical-slide inventory, valid slide reordering, failed replan retention and invalidated prior approval, recovered plan decision parity, first admission after expiry, live shared-root refusal, degraded readiness, application HTML revalidation, and partial font-scaling tampering.
- Independently passed renderer-backed `test_failed_replan_keeps_verified_artifact_and_invalidates_old_approval`, `test_pending_plan_recovery_preserves_exact_planner_decision`, `test_full_vertical_slice_small_text`, and `test_demo_requires_and_verifies_multi_issue_plan` during this remediation effort; isolated guard tests also passed.
- Claim lint, frontend syntax checker, local HTTP smoke, and real LibreOffice deep-readiness probe passed.
- **Full isolated resource gate is NOT certified:** one combined gate attempt stopped during the multi-issue case due to an execution limit; that case subsequently passed in its own process. Do not report 215/215 or `RELEASE GATE PASS` for RC4 until all 41 resource tests pass on the exact extracted ZIP.
- Chromium native-browser test, Railway deployment, real Gemini usage, representative customer-deck usefulness, and pricing evidence were not checked in this release.

## Scope / remaining boundaries

- Single worker, single replica, process-local ephemeral session store. Advisory locking prevents accidental shared-root cleanup, but is not a distributed storage implementation.
- User artifact semantics are still bounded to explicit font-size modifications. Contrast, arbitrary Office interaction, media edits, real-room perceptual results, and full AVIXA conformance are not claimed.
- A successful new replacement plan intentionally retires the old output at plan commitment; previously verified output is retained on failed planning, not guaranteed across every later user-initiated workflow transition.
- Existing provider API and file-processing dependency licensing/security updates require validation in the **actual deployed image**.

## Required promotion gates

1. Run the full 41-node isolated renderer gate from an independent extraction, alongside the 174 deterministic tests.
2. Run native Chrome/Edge direct to the deployed origin for upload → analyze → plan → approve → download → verify hash → delete, including refresh and failed-replan recovery.
3. Confirm one-worker/one-replica Railway deployment, patch level, source/image identity, and Gemini provenance if advertised.
4. Measure real-deck usefulness and preserve an honest record of unsupported and refused cases before claims in the five-minute video.
