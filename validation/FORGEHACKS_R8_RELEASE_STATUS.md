# ForgeHacks R8 — Corrective Release Status

This is a local corrective release of the same bounded competition product, not a scope expansion.

## Acceptance conditions
- Theme-inherited paint is recorded as unsupported: no false whole-deck VERIFIED.
- Hidden slides do not shift visible PDF page mapping; an unknown PDF page count is fail-closed.
- A slow new session write does not convoy unrelated session operations; pending allocations count toward limits.
- Filesystem deletion must be confirmed before acknowledgement; retry remains authorized after cleanup failure.
- Browser preserves capabilities when deletion fails.
- Invalid required Content_Types XML or ZIP media corruption is rejected before session allocation.
- Existing safety, utility and agent boundaries remain enforced.

## External completion gates
Source-bound release test results belong in the accompanying evidence JSON and build report, not self-certified here. Deploy exactly one worker and one replica, prove the exact release ID in the public service, check real Gemini calls (zero fallback), browser deletion/approval recovery, GitHub CI, and record the final video and Devpost form.
