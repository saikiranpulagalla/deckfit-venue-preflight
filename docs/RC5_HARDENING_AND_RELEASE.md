# DeckFit AI RC5 — bounded hardening and release protocol

## Source-bound identity

RC5 computes `source_fingerprint` at runtime from its Python application modules, frontend HTML, reference JSON, Dockerfile, and Railway configuration. The value is independent of `VENUE_RELEASE_ID`, which remains an operator-configurable display label.

Run in the **exact extracted RC5 archive**:

```bash
python scripts/compute_source_fingerprint.py
```

To verify a deployment, compare the separately computed value to `/health` and invoke:

```bash
python scripts/live_deployment_check.py \
  --base-url 'https://YOUR-SERVICE.up.railway.app' \
  --expected-release-id 'deckfit-nextfounders-rc5-local' \
  --expected-source-fingerprint 'PASTE_LOCAL_SHA256' \
  --full
```

The `--expected-source-fingerprint` option is required to certify RC5 by name. A deployment running RC3/RC4 with RC5's display label alone will fail. This is source identity comparison, **not a signature or cryptographic proof of the deployed container image**. Independently review Railway's deployment ID, source commit, build logs and image digest.

## Changes

- Strict bounded XML parsing rejects DTD/entities, excessive nesting/element counts, and unsupported ZIP compression methods at PPTX intake.
- Embedded SVG security inspection uses a linear URL scanner and per-value/per-file budgets. External references remain refused.
- PPTX mutation respects logical reordered slides without renumbering slide relationship targets; final preservation checks resolve those identities through the source relationships.
- A session with an existing byte-verified output in `VERIFIED` or `REVIEW_REQUIRED` is **immutable**. New analysis or replanning returns HTTP 409. To test another set of room dimensions, create a fresh session. This prioritizes reliable retention over in-place revision history.
- A Gemini request success cannot clear a newer, different request's failure-open circuit; each failure increments the breaker generation.
- Pending upload reservations count against session capacity even while upload bodies are arriving. The admitted upload redeems its own reservation; competing demo sessions cannot steal that slot.
- In-process TTL uses monotonic elapsed time; API timestamps remain wall-clock values.
- Readiness checks the current presence of LibreOffice as well as its cached version. Deep readiness continues to render a real fixture.

## Operational constraints

- Single worker and one replica; process-local, ephemeral sessions.
- No claim of slide readability, contrast compliance, universal PowerPoint compatibility, or end-to-end accessibility.
- Public Railway deployment, live provider selection and actual browser-to-Railway flow must be tested separately.
- For URLs behind ingress, validate the actual proxy-hop IPs before configuring `VENUE_TRUSTED_PROXY_IPS`; never trust unverified `X-Forwarded-For` headers.
- The verified output must be downloaded before session expiry. Session storage is not a durable user-account vault.

## Acceptance checks

`python -m pytest backend/tests -m 'not resource'` runs all deterministic tests. Resource tests are isolated via `python scripts/release_gate.py` or `--full`. Record outcomes for the **exact exported ZIP**. A subset pass must never be advertised as the whole gate.
