# ForgeHacks Devpost Submission Template

Use the measured technical evidence below. Add only the real public video URL before submitting.

## Title

DeckFit AI

## Track

AI + Creativity

## Short description

DeckFit AI explores responsive presentation design for physical spaces. It combines an existing PPTX with venue geometry, deterministically identifies supported room-dependent visual-demand failures, asks a bounded AI planner to choose among already-safe simulated repairs, requires human approval, modifies a copy, and reopens the saved artifact before reporting the result. The deployed application retains the historical internal Venue Agent name.

## Problem

Presentation tools understand slides; room/AV guidance understands physical viewing conditions. Presenters experience both at the same time. A deck that looks fine on a laptop may demand more from someone sitting much farther from a projected image.

## What it does

1. Upload a PPTX or use the project-owned demo.
2. Enter active displayed-image height and farthest-viewer distance.
3. DeckFit AI analyzes supported structural BODY text against the selected public reference profile.
4. The server generates and simulates bounded `SCALE_TEXT` repair candidates.
5. Gemini may select only from those legal candidate IDs using privacy-safe structural/hierarchy metadata.
6. A human reviews and approves the exact plan.
7. DeckFit AI mutates a copy, reopens it, renders it, and independently rechecks the result.

## Why the AI is not a wrapper

AI does not decide geometry, invent PowerPoint commands, mutate titles, or certify success. Its job is the creative preference problem: choose among non-dominated, pre-simulated safe alternatives. Deterministic policy constrains the choice; the user approves it; fresh artifact verification decides the terminal state.

## Measured evidence

- validated runtime release ID: `r8.1-ab6a6752be613137`
- collected tests: `186`; non-resource passes: `150`
- unsafe false `VERIFIED` observed in the implemented adversarial corpus: `0`
- strict public full judge path: `PASS`
- public Gemini planner runs / deterministic fallbacks: `5 / 0`
- observed public judge-path latency: `11,751.4 ms`
- server-verified output SHA-256 = downloaded output SHA-256: `PASS`

## Limitations

DeckFit AI intentionally supports only a narrow automatic mutation envelope. It does not claim universal human readability, WCAG/accessibility certification, AVIXA certification, or pixel-identical Microsoft PowerPoint rendering. Unsupported/unknown coverage remains explicit and cannot be promoted to whole-deck `VERIFIED`.

## Links

- Demo: https://venue-agent-production.up.railway.app/
- GitHub: https://github.com/saikiranpulagalla/deckfit-ai
- Video: _add the real public or unlisted 2–4 minute video URL before submitting_
