# RC5.3 FINAL-01 r2 source publication

This repository imports the existing qualified DeckFit AI release. It preserves third-party notices, prior-research/tool disclosures, historical documentation and regression fixtures. It does not invent development history or claim the software originated entirely in this new repository.

## Exact source provenance

- Distribution: `deckfit-ai-next-founders-rc5-3-final01-r2.zip`.
- Distribution SHA-256: `3d6bc28d81a5423f35d41b262bb9ba15885fcc5eb16b304dcfa8ff8e7df90479`.
- Expected Linux application-source fingerprint: `0d84f135419cdb1b9e3c5918fb04da5c40c4a9e591213c332f580670b43ead53`.
- Qualified application, frontend, reference, Dockerfile, Railway configuration, dependency declarations, tests and fixtures are unchanged from that archive.
- README clarification, repository ignore/byte-preservation rules and this handoff are publication-only metadata; the original qualified ZIP was not edited.
- The fingerprint is a source checksum, not a dependency lock, signed container attestation or deployment label. Its unchanged native-Path sorting is platform-dependent; verify the qualified value on Linux/POSIX.

## Safety and qualification

FINAL-01 fixed a real RC5.2 verification-coverage defect: visible `mc:AlternateContent` could escape structural inventory. R2 rejects namespace-qualified wrappers in slide/layout/master XML, including content-type-identified relocated parts, before accepting a session. See the compatibility policy for the deliberately narrowed support scope. RC5.2 is not a safe replacement for this candidate.

Prior exact-archive local qualification on October 15, 2026 recorded 208 non-resource tests plus 46 isolated LibreOffice/resource tests: **254/254 and RELEASE GATE PASS**. This is historical qualification of that archive, not proof that every fresh clone or subsequent dependency resolution has independently rerun it.

Additional actual evidence included native installed-Edge localhost recording, independently hashed downloaded PPTX, refresh recovery, immutable completed-session refusals, wrapped-content refusal, native Docker health at the default port, and a controlled missing-renderer negative. Actual Gemini execution remained unverified; deterministic operation and a separately labeled SDK-to-local-503 fallback test were exercised. No customer, revenue or readability-guarantee claims follow from those tests.

## Runtime limitations

- One worker, one replica, ephemeral process-local sessions; replacement can discard active sessions and undownloaded artifacts.
- The Dockerfile's native HEALTHCHECK targets port 8000 while startup honors PORT. Default port 8000 was healthy; PORT=8080 reproduced a Docker-native unhealthy state despite healthy HTTP. This frozen-source limitation was not silently patched.
- Railway's separately configured `/health/deep-readiness` gate is independent. New services may not load legacy railway.json automatically; verify effective platform settings rather than assuming the file is applied. This publication does not change any Railway resource or source connection.
- The configured runtime release label is generic and not source proof. Verify the full fingerprint and actual deployment metadata.
- Genuine Gemini invocation, quota and cost must be established separately before claiming provider-backed planning.

## Publication scope

Included: application, frontend, dependencies/build configuration, CI/release tooling, all tests and required fixtures, demo/reference data, legitimate documentation and notices, historical validation Markdown, and evaluation definitions/holdouts needed by tests.

Excluded: generated `backend/venue_agent.egg-info`, obsolete generated evaluation-result JSON, a historical generated gate JSON, local credentials/.env, caches, sessions, browser recordings, temporary diagnostic scripts/logs and deployment credentials. Excluded local files were not deleted. No frozen release archive or private runtime artifacts were committed.

The retained R8/ForgeHacks documents are historical provenance and regression contracts, not current r2 runtime evidence. Use this handoff for the publication's current identity and limitations.
