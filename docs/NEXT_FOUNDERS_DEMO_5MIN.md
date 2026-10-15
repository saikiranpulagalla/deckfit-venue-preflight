# Next Founders — Five-minute video shooting script

**Use a real run from the candidate source/deployment. Never simulate an app success or splice fake output.**

| Time | Footage / proof | Narration direction |
|---|---|---|
| 0:00–0:35 | Show a real text-heavy deck on a known projection setup | Trainers make slides on laptops; distant viewers see the same slides in a very different geometry. |
| 0:35–2:00 | Open DeckFit, select the demo or permitted deck, enter measured screen height and distance, analyze, review a server-simulated candidate, approve, download the verified copy | Explain the user outcome and what remained review-only. If final state is not VERIFIED, show the actual result transparently. |
| 2:00–3:05 | Show codebase diagram + API boundaries | FastAPI/Pydantic intake, python-pptx structure, independent LibreOffice/PyMuPDF render, bounded optional Gemini plan, human-bound hash and final package preservation verification. Explain the AI does not edit arbitrary content. |
| 3:05–4:10 | One real target customer, alternative methods, price/cost hypothesis with explicit assumption labels | The buyer is a recurring text-heavy training provider. Compare time and usefulness to manual editing using measured trials; do not fabricate paying users. |
| 4:10–4:45 | Current constraints and future architecture | Current one-instance ephemeral workflow. Explain that durable storage, queue/worker isolation and per-deck metering are future scaling work, not already delivered. Mention external-link/complex-slide limitations. |
| 4:45–5:00 | The checked PPTX and source-aligned release evidence | Close with the narrowly defensible promise: prepare supported slide text for a specific room and know what still needs manual review. |

Before recording: capture deployment source hash, real `/health`, successful result file hash, server-reported planner choice (`gemini-*` or `deterministic_fallback`), and delete the disposable demo session. Avoid displaying private deck notes or tokens.
