# FINAL-01 independent qualification — October 15, 2026

**GO — exact RC5.3 FINAL-01 r2 candidate qualified locally.** No new application correction was necessary. This record describes completed local execution, not a production deployment or a real Gemini invocation.

## Release identity

- Original archive: `deckfit-ai-next-founders-rc5-3-final01-r2.zip`.
- ZIP SHA-256: `3d6bc28d81a5423f35d41b262bb9ba15885fcc5eb16b304dcfa8ff8e7df90479`.
- Independently computed Linux source fingerprint: `0d84f135419cdb1b9e3c5918fb04da5c40c4a9e591213c332f580670b43ead53`.
- Fresh native-WSL extraction; all 178 distributed files remained byte-identical afterward. Neither original RC5.2 nor r2 archive was modified.
- The archive is not bundled in this Git repository. README and evidence publication metadata do not change the defined application-source fingerprint.
- Windows native-path ordering remains platform-dependent. ZIP identity, application-source identity, dependency inventory and deployment/image identity are separate evidence scopes.

## Actual before/after reproduction

| Fixture | RC5.2 | R2 |
|---|---|---|
| Direct visible rectangle with supported body text | Unsupported inventory 1; REVIEW_REQUIRED | Unsupported inventory 1; REVIEW_REQUIRED |
| Equivalent Choice/Fallback-wrapped rectangle | Unsupported inventory 0; false VERIFIED | Upload 400; explicit mc:AlternateContent refusal |
| Ordinary supported demo | VERIFIED | VERIFIED |

Both versions used fixture package payloads that matched entry-for-entry. Real LibreOffice rendering of the RC5.2 source and downloaded false-verified output showed the red rectangle in both PDFs. The defect was not inferred from XML alone.

Root cause: python-pptx shape traversal omitted compatibility-wrapped content, so both baseline/output inventories omitted the same object. Preserved package XML and equal rendered text did not establish complete visual coverage.

R2's existing `_refuse_visual_compatibility_content()` in `backend/app/security/intake.py` refuses namespace-qualified wrappers throughout bounded slide/layout/master XML trees, including relocated layout/master parts identified by content type. It does not flatten branches, alter final status labels, or weaken comparison rules.

The separate differing-branch fixture rendered one blue Fallback object and no red Choice object. We did not assume both branches were visible. R2 refused it regardless of branch selection.

Evidence: [RC5.2 reproduction](../validation/rc53-r2-independent/reproduction-rc52.json), [r2 reproduction](../validation/rc53-r2-independent/reproduction-r2.json), [supplemental matrix](../validation/rc53-r2-independent/matrix.json).

## Fresh execution results

| Check | Outcome |
|---|---|
| Complete unchanged release gate | PASS; exit 0; RELEASE GATE PASS; 383.141 seconds |
| Non-resource subprocess | 208 passed, 46 deselected, 1 warning in 7.35 seconds |
| Isolated renderer/resource subprocesses | 46 distinct cases passed; no incomplete cases |
| Complete gate total | **254/254** |
| Claim lint / frontend syntax / HTTP smoke | PASS / PASS / PASS |
| Source-bound full loopback HTTP verifier | PASS |
| Supplemental compatibility refusals | 18/18 |
| Ordinary supplemental intake controls | 4/4 |
| Real repaired-output tampering test | PASS: download rejected with 409 and state FAILED |

The supplemental cases are not added to the 254-test count. Gate assertions, timeouts, source, dependencies and configuration were unchanged. The existing FINAL-01 regression contributed 22 non-resource cases and three real API/render controls within that gate.

Commands ran from the fresh extraction with its absolute backend directory on `PYTHONPATH`, bytecode/cache writing disabled, unrelated pytest plugin autoload disabled, default system Fontconfig and no Gemini credential supplied:

```bash
python scripts/release_gate.py --full
python scripts/claim_lint.py
python scripts/check_frontend_js.py
python scripts/http_smoke.py
python scripts/live_deployment_check.py \
  --base-url http://127.0.0.1:46299 \
  --expected-source-fingerprint 0d84f135419cdb1b9e3c5918fb04da5c40c4a9e591213c332f580670b43ead53 \
  --full
```

That loopback server was stopped afterward; the recorded port is evidence of the run, not a currently available service.

Raw evidence: [full gate](../validation/rc53-r2-independent/full-release-gate.raw.log), [claim lint](../validation/rc53-r2-independent/claim-lint.raw.log), [frontend syntax](../validation/rc53-r2-independent/frontend-syntax.raw.log), [HTTP smoke](../validation/rc53-r2-independent/http-smoke.raw.log), [full verifier](../validation/rc53-r2-independent/full-verifier.json).

Runtime: Python 3.12.3, LibreOffice 24.2.7.2, Ubuntu Impress package `4:24.2.7-0ubuntu0.24.04.7`, PyMuPDF 1.28.2, python-pptx 1.0.2 and pytest 9.1.1. See [actual environment inventory](../validation/rc53-r2-independent/identity-and-environment.json). Non-fatal deprecation warnings were not hidden or resolved by dependency changes.

## Coverage and integrity

The supplemental real API matrix refused slide/layout/master wrappers, empty/metadata-only wrappers, Choice/Fallback variants, nested wrappers, grouped/placeholder wrappers, hidden-slide wrappers and content over editable text. Repeated refusals left admission accounting clean; a subsequent demo could be created and deleted. Relocated layout/master refusals were also exercised through real loopback HTTP.

Ordinary small-text and demo repairs reached VERIFIED; the direct rectangle remained REVIEW_REQUIRED. Upload, analysis, planning, approval/application and downloads returned 200 for those accepted controls. Download hashes matched the verifier and response header. Completed replan/reanalysis returned 409 without losing the artifact; deletion returned 200 and subsequent output access 404. See [HTTP workflows and output hashes](../validation/rc53-r2-independent/http-workflows.json).

A separate actual repaired demo rejected stale approval and replay, preserved its download through completed-session refusals, then detected deliberately changed disposable output bytes. Its independently computed download hash matched the server:

```text
966dbefa9db9a1f65e721852fb838f6dd61e8c56968dc7c620393fc6407ac609
```

Existing regression cases covering source tampering, exact font-only edits, relationships/package preservation, titles/notes, slide order, duplicate text, candidate/approval authority, capabilities, SVG/XML/ZIP limits, concurrency and deterministic fallback passed. Unit checks and actual render/API checks are distinct forms of evidence; neither is presented as universal proof over OOXML.

The application-source difference from RC5.2 remains exactly the original r2 correction: `backend/app/security/intake.py`, the added FINAL-01 regression test and compatibility-policy document. No new application files were changed during this independent run. See [post-run distribution integrity](../validation/rc53-r2-independent/final-integrity.json).

## Limitations and release decision

- Conservative refusal intentionally rejects some legitimate empty/metadata-only wrappers and hidden/unused visual parts. No automatic normalization is implemented.
- Planning was deterministic. A provider call was not attempted; Gemini success is not claimed.
- Docker image/build attestation, native-browser recording, production source identity, public workflow, production logs and capacity were not requalified by this local run.
- The frozen Docker native healthcheck targets port 8000 while startup honors PORT. Effective hosting probes must be independently checked.
- Sessions remain ephemeral, single-worker and single-replica. VERIFIED is not a universal readability or accessibility guarantee.

Retain the existing qualified r2 archive; do not substitute RC5.2. A future separately authorized deployment must use a separate service, check credits/capacity, explicitly target the existing project and new service ID, preserve venue-agent, and verify the actual deployment/image identity plus public health, FINAL-01 refusal, repair, hash binding and deletion. No Railway or GitHub mutations were part of the qualification run; this evidence publication is a subsequent repository-only action.

## Evidence scope

This directory publishes a focused textual subset of the completed local evidence. Values were checked for credential patterns; session capabilities, credentials, session stores, generated PPTX/PDF downloads, screenshots, caches and source archives are not published here. Original local environment paths remain in raw logs as execution provenance.

The complete external evidence bundle contained 78 files and had SHA-256 `7148e6cb38494c292b0862213269bd3b0a0c20eced9706a19ab48548114475ca`. It is not included in Git; that digest identifies the external bundle, not these selected files. The original detailed report had SHA-256 `b31141234a071fe507c8c807e1401e4c928f7efa7cb46b90c87c35f035d18084`. Neither checksum is a signed attestation.
