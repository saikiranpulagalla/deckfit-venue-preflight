# Venue Agent R8 — Current Local Release Evidence

## Source identity

This is an exported R8 source snapshot, not a Git worktree. No commit, branch, tag, or Git diff can be truthfully reported from this archive. The runtime default release ID is `forgehacks-r8-local`; a hosted release ID must be supplied by the operator and proven by the public checker.

## Executed local and Linux remediation evidence

- Collection: **183 tests collected**.
- Session lifecycle/documentation suite: **18 passed, 0 failed** (`backend/tests/unit/test_session_store.py` and `test_r8_release_documentation.py`).
- Additional deterministic parser/domain/plan/transition subset: **28 passed, 0 failed**.
- Broad Windows-safe deterministic partition: **66 passed, 0 failed, 1 skipped**; the skipped renderer child-process test requires POSIX shell process-group semantics.
- Claim lint: **passed**.
- Frontend JavaScript syntax: **passed**.
- Python compilation: **passed**.
- TTL cleanup fault injection: **passed**: expiry revoked API access, retained internal cleanup state after no-op and `PermissionError` deletion failures, and later retry removed the owned directory.
- Linux/WSL2, Python 3.12.3, LibreOffice 24.2.7.2: **`python scripts/release_gate.py --full` passed (exit 0)**. This ran **147 non-resource tests** and every collected resource node in isolated processes; the earlier fixture-only holdout failure was corrected without weakening mapping policy and the complete rerun passed.
- Linux production-command HTTP smoke: **passed (exit 0)** with real renderer deep readiness; its response reported `forgehacks-r8-local`, `LibreOffice 24.2.7.2`, deterministic fallback planner mode, one required replica, and capability authorization PASS.

The release gate is the authoritative complete local Linux result. Its test phases must not be compressed into an invented aggregate count.
These are not a full-suite result when cited independently: the Windows subsets and any single resource case must always be read together with the complete Linux release-gate outcome.

## Not executed / externally unverified

- Windows-only FastAPI `TestClient` partition remains blocked by the Windows sandbox's asyncio socket-pair restriction, but the same HTTP/resource paths executed in the passing Linux gate.
- Docker image/runtime and browser E2E.
- Public Railway service, one-replica configuration, browser E2E, and proxy behavior.
- Live Gemini calls, planner stability, and human preference evidence.
- Devpost form and public video.

`SUBMISSION_READY` is not justified. The existing submission freeze remains the required public evidence gate.
