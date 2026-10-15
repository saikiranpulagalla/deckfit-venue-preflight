# DeckFit AI — AI / Tool Disclosure

DeckFit AI is the public ForgeHacks identity. The deployed application and internal engineering code retain the historical name Venue Agent.

## Runtime AI

- Planner: Google Gemini API when `GEMINI_API_KEY` is configured; validated public model `gemini-3.5-flash-lite`.
- Role: select among server-generated, already-simulated legal candidate IDs and provide a short rationale.
- Response authority: **candidate IDs + rationale only**.
- The server recomputes legality, coverage, unresolved issues, plan simulation, approval integrity, mutation and final verification.
- Unknown/duplicate/unsafe model candidate IDs are rejected and trigger deterministic fallback.
- Timeout/circuit-breaker fallback keeps the core bounded workflow available.

### Runtime data boundary

Competition V1 does **not** send raw uploaded PPTX bytes, slide screenshots, speaker notes, or slide text to Gemini. The model receives derived candidate/simulation metadata, aggregate planning context, and explicit constraints only.

## Runtime deterministic tools

- FastAPI / Pydantic
- python-pptx
- LibreOffice Impress (headless rendering)
- PyMuPDF
- pytest

## Development AI tools

OpenAI Codex was used as a development-time assistant for implementation support, test review, release engineering, and documentation. It is separate from the runtime Gemini planner. Do not imply that a development assistant generated or verified runtime evidence that was produced by deterministic code.
