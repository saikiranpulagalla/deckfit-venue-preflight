# R6 Corrective Design and Failure-Proof Matrix

This document records the corrective architecture for R5's third and fourth independent hunts. Tests live under `backend/tests/adversarial/test_r6_corrective_gates.py` and `backend/tests/unit/test_r6_public_probe_contract.py`, in addition to all retained R5 and earlier safety suites.

| Problem | Fix | Negative case | Positive / non-regression case |
|---|---|---|---|
| Painted empty text-box false `VERIFIED` | Inventory visible fill, line, or advanced effects before skipping empty text | Filled black empty textbox over body text blocks whole-deck VERIFIED | Empty unpainted text box and text-only demo remain supported |
| Hidden master false review | Check per-slide `showMasterSp` for inherited shapes only | Hidden master sentinel not inventoried | Existing inherited visual tests and background-image tests retained |
| Invalid referenced layout | Bounded XML parse for referenced layout/master/theme parts | Malformed layout rejected as upload HTTP 400 | Original demo and valid fixtures accepted |
| Degraded readiness returns 200 | Convert deep-readiness response status to 503 on actual degradation | Renderer self-test failed -> HTTP 503 | Recovery -> HTTP 200; liveness separate |
| Temporary renderer saturation poisons state | Distinguish retryable capacity from file errors; stage complete analysis before commit | Candidate simulation fails at first/middle/last index -> HTTP 503 with uploaded source preserved | Retry same session succeeds after capacity is released |
| Failed replanning leaves stale `AWAITING_APPROVAL` | Invalidate previous plan then transition to `ANALYZED` before planner/combined simulation | Exception -> no plan hash or selected candidate IDs | Happy-path plan awaits exact approval; stale plan rejected |
| Upload quota enforced after multipart | ASGI pre-body admission reservation plus atomic creation check | Full owner rejected before `validate_pptx` | Malformed request releases reservation; another owner can proceed |
| Unbounded same-session waiters | Bounded waiter count and finite lock-acquisition wait | Burst overload receives retryable rejection and no leaked leases | Independent sessions and subsequent owner operations continue |
| Unlimited approval identifier work | Hash/ID field format, size/count limits; bounded replay-key set | Oversized inputs rejected with HTTP 422 | Compact IDs and SHA-256 hashes still accepted |
| Failed session write leaves orphan directory | Exclusive owned directory with rollback on marker/source write failures | Inject I/O failure -> no stored session and no orphan path | Normal session create and delete work |
| Five successful local Gemini calls counted as deployed reliability | Probe five fresh public demo sessions through public `/analyze` and `/plan` with valid session capability | Non-Gemini/no fallback flag contradictions rejected | Synthetic public-HTTP test confirms five independent authenticated sessions and clean deletion |

## Rollback and race philosophy

- Never publish partial candidate or selected-plan evidence to the session. Stale output is explicitly invalidated before a new analysis or plan.
- Keep global store-map lock brief when waiting on per-session execution; entry lease reservations have finite capacity and are decremented on failure and timeout.
- Only remove a newly allocated directory if this process successfully created it exclusively. Never delete a generic unowned directory on error.
- Reject oversized inputs during Pydantic request validation rather than after approval-hash comparison.
- Continue using the saved output artifact and independent verifier as the authoritative source for `VERIFIED`, not an AI assertion or simulation-only result.

## Known limitations

No general proof is claimed for every Office drawing object, multi-renderer equivalence, adversarial traffic under a distributed botnet, third-party cloud availability or the absence of all implementation bugs. Public Gemini usage and Railway provenance must be observed externally after deployment; no local report can substitute for those live gates.
