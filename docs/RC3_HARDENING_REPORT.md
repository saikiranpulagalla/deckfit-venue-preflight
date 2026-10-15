# DeckFit AI RC3 — controlled remediation

This release is based on the original, unmodified `deckfit-ai-next-founders-rc2.zip` (SHA-256 `2284449dbf92986ab96a1b389910801acbf6cc0a868c356c7d4ab1f914b2ff01`). It is not a new presentation editor and does not expand supported font mutations.

## Technical changes

1. **Conservative package preservation:** `package_integrity_reasons` compares the entire OOXML ZIP inventory, non-slide XML semantically, and non-XML parts byte-for-byte. Slide XML changes may only contain increased `a:rPr/@sz` attributes in explicitly approved shape IDs; simulations and the application verifier also compare the expected approved scale. The check rejects altered backgrounds, text color, style, hyperlinks, notes, slide order and package inventory. XML differences that cannot be classified fail closed. The method does *not* prove color contrast or universal Office-renderer equivalence.
2. **Revision-specific approval:** session-owned `analysis_revision` and unpredictable `plan_nonce` are included in the existing approval hash, so an old approval reference cannot become current again after a new plan or analysis. No approval capability or authorization header was removed.
3. **Accurate restore:** authenticated status returns the server's analyzed venue and pending-plan constraints. The browser restores these values before displaying a recoverable approval, and refuses recovered approval if the authoritative venue is missing.
4. **Transactional last-good recovery:** a failed reanalysis can preserve the previously checked output and its original room provenance. The former plan is invalidated. A successful replacement analysis clears the prior output. Recovered output is downloadable only while its SHA-256 remains identical to the recorded verified artifact.
5. **Status/download consistency:** `/api/sessions/{sid}` validates the stored output hash before claiming a currently available artifact. Download still checks the hash independently under the session lock.
6. **Safer execution errors and retries:** unexpected mutation/verification exceptions generate the generic public code `repair_execution_failed`; the log records only the exception type. After an ambiguous approval response, the browser reads session state rather than issuing a second mutation automatically.
7. **Bounded session admission:** unclaimed sessions expire after a shorter configurable provisional TTL (default 300 s; never more than the normal TTL). Successfully authenticated requests retain the normal idle lease. Public readiness caches the LibreOffice version check for the lifetime of the server process.
8. **Embedded SVG URL check:** inert SVGs remain supported, but SVGs containing explicit external `href/src`, CSS remote resource URLs, or external style imports are refused at intake. The previous finding was a classification gap, **not** proof of SSRF; this change is conservative defense in depth.
9. **Release gates:** new adversarial tests cover appearance tampering, exact-scale enforcement, stale plan revisions, original-venue recovery, expired unclaimed sessions, hash-status consistency, fixed SVG behavior and an actual `verify_output` regression.

## Deliberately unchanged

- Mutation algorithm, candidate cap, source immutability, existing deterministic/Gemini fallback architecture and the human-approval path.
- Titles, charts, tables, images and unknown content are **not** newly eligible for automatic editing.
- Deployment topology remains single-replica/process-local. Uploaded decks are not sanitized for hidden notes, personal information, or links that the intake policy does not accept.

## Deployment limitations

This is a local release candidate. The current Railway service and GitHub repository remain unchanged until an authorized deployment. A full real Chrome/Edge public run, Railway container package inventory, provider configuration, and independent customer-deck usefulness testing are separate release gates.

The Python/LibreOffice environment running the local tests need not match Ubuntu 24.04 used in the Dockerfile. Successful local tests cannot certify the deployed Ubuntu package version. PyMuPDF's AGPL/commercial licensing remains a business decision requiring separate compliance review.

## Local verification snapshot (October 12, 2026)

- Existing and new **non-resource tests:** 161 passed.
- **All isolated renderer-backed tests:** 39 passed in the full release gate (prior to the final frontend-only session-acknowledgment tweak).
- The subsequent frontend-only change passed JavaScript syntax, claim lint, all 161 non-resource tests, and local HTTP smoke including a real LibreOffice deep readiness render.
- The final exported ZIP is independently re-extracted and retested; the handoff report records its exact SHA-256 and any remaining unverified stages.

**Not performed:** deployment to Railway, remote Gemini invocation, native public browser E2E, formal production security audit, customer interviews, or paid customer validation.
