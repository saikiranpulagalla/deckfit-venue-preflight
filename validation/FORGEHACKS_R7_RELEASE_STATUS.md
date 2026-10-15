# ForgeHacks R7 — Corrective Release Status

## Product scope
R7 keeps the R6 deterministic text-only mutation boundary and closes the outlined text-bearing shape regression. No new mutation authority or arbitrary AI tools were introduced.

## Added regression gates
- Populated 100pt outlined text box is inventoried as unsupported visible content; real analyzer/plan/apply must not return whole-deck VERIFIED.
- Normal unpainted demo and empty unpainted editing text box remain supported.
- Slow/incomplete upload-body receipt produces HTTP 408 and releases admission reservations.
- HTTP 413/429 and ordinary responses retain site-wide security headers.
- Forwarded client identity uses explicitly configured trusted proxy hops; untrusted clients cannot spoof X-Forwarded-For.
- Pending plans may be retrieved only with a valid capability; their exact hash/candidates are checked before being returned. Old plans are invalidated by reanalysis.

## Pending external gates
- Publish the **exact** frozen source to GitHub, verify CI, and deploy exactly one worker and replica on Railway.
- Configure `VENUE_RELEASE_ID` to the frozen R7 release ID and a real Gemini credential privately.
- Validate Railway ingress peer identity and trusted-proxy configuration using separate real clients; do not trust forwarding headers indiscriminately.
- Run full public judge-path and five independent public Gemini planner checks with zero fallback.
- Complete fresh-browser approval-resume check, source provenance, 2–4-minute public demo, and Devpost submission.

A local pass cannot substitute for any of the public checks. The full isolated gate and release digest are recorded in the accompanying R7 evidence JSON.
