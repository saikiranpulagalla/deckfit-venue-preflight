# ForgeHacks Deployment Runbook

This runbook deploys the frozen competition build without weakening its process-local session assumptions.

## Required service shape

- exactly **one Railway replica**;
- exactly **one Uvicorn worker**;
- Dockerfile deployment from repository root;
- public HTTPS networking;
- Railway health check: `/health/deep-readiness`;
- `VENUE_MAX_CONCURRENT_RENDERS=1`.

Railway does not provide sticky sessions across replicas. Competition V1 therefore must remain one replica because the session/capability state and ephemeral artifacts are process-local.

## Required variables

In Railway Variables, add the secret `GEMINI_API_KEY` without writing its value into source files. Configure the remaining non-secret variables as:

```text
GEMINI_MODEL=gemini-3.5-flash-lite
VENUE_RELEASE_ID=forgehacks-r8-<source-prefix>
VENUE_MAX_CONCURRENT_RENDERS=1
WEB_CONCURRENCY=1
```

Recommended unchanged bounds:

```text
VENUE_SESSION_TTL_SECONDS=2700
VENUE_MAX_SESSIONS=24
VENUE_PER_CLIENT_SESSIONS=8
GEMINI_TIMEOUT_MS=10000
GEMINI_CIRCUIT_COOLDOWN_SECONDS=60
```

Client quota source: by default, only the direct socket peer address is trusted. If the hosting reverse proxy forwards all visitors through one peer, verify the per-client identity behavior. Set `VENUE_TRUSTED_PROXY_IPS` to individually trusted direct proxy addresses only, never a wildcard or a client-controlled value. Do not copy random `X-Forwarded-For` headers into trusted identity. Quotas are process-local best effort, not DDoS protection.

The final submission script **reruns** the public full checker and five or more live planner calls. Earlier JSON files are not proof and are overwritten only inside `validation/evaluation/`.

Do not put `GEMINI_API_KEY` into `.env.example`, source control, screenshots, release evidence, or demo video.

## Railway settings that must be manually confirmed

`railway.json` fixes Dockerfile build, deep-readiness deployment health check, and restart behavior. Replica count still must be confirmed in the Railway service Scale settings: **1**.

## Post-deploy verification

First verify the release identity without consuming a full demo render cycle:

```bash
python scripts/live_deployment_check.py \
  --base-url https://YOUR-SERVICE.up.railway.app \
  --expected-release-id forgehacks-r8-<source-prefix> \
  --require-gemini
```

Then exercise the exact judge loop:

```bash
python scripts/live_deployment_check.py \
  --base-url https://YOUR-SERVICE.up.railway.app \
  --expected-release-id forgehacks-r8-<source-prefix> \
  --require-gemini \
  --full \
  --output validation/evaluation/live-deployment-final.json
```

The full check requires:

1. `/health`, `/health/readiness`, and a real-render `/health/deep-readiness` pass;
2. ForgeHacks judge-facing homepage claims are present;
3. project-owned demo session is created;
4. deterministic analysis finds the intended below-target issue(s);
5. the configured Gemini planner produces an approvable bounded plan without fallback;
6. exact human approval applies the saved-copy mutation;
7. fresh verification reaches `VERIFIED`;
8. source SHA remains unchanged;
9. downloaded output bytes exactly match the verifier's output SHA-256;
10. judge-facing/API responses expose the expected security/no-store headers;
11. ephemeral demo session is deleted and cannot be accessed afterward.

## Release acceptance

Do not record the final video until the full live check passes repeatedly from the production URL. If Gemini fails, show the fallback honestly; do not label a deterministic fallback run as Gemini-planned.

## Final submission freeze

After the live full checker passes, record planner stability without slide content:

```bash
python scripts/planner_probe.py --runs 10 --output validation/evaluation/planner-probe-final.json
```

Then run:

```bash
python scripts/submission_freeze.py \
  --base-url https://YOUR-SERVICE.up.railway.app \
  --expected-release-id forgehacks-r8-<source-prefix>
```

The final gate is intentionally fail-closed. Missing public evidence, any live Gemini fallback, hash mismatch, missing security/deletion check, or a judge path over the configured maximum prevents `SUBMISSION_READY`.
