# DeckFit AI — ForgeHacks 2026 Judging Map

DeckFit AI is the public ForgeHacks identity; Venue Agent remains the historical internal engineering name.

This file maps implemented evidence to the official five judging criteria. It is intentionally evidence-first; do not replace missing measurements with marketing claims.

## 1. Real-World Impact & Relevance

Problem: presentation authors typically design at laptop distance, while audiences experience a physically bounded display from real viewing distances.

Evidence to show:
- project-owned before/venue/after demo;
- 5–10 genuine presenter/student/faculty conversations if available;
- named limitations showing the project does not overclaim individual readability.

Track fit: DeckFit AI introduces physical venue context into the creation/repair of presentation media.

## 2. Technical Implementation & AI Use

Evidence:
- deterministic PPTX + rendered-PDF analysis;
- versioned public reference profile;
- server-generated bounded repair candidates;
- candidate and combined-plan simulation;
- bounded Gemini proposal schema (`candidate IDs + rationale` only);
- server-side canonicalization of model output;
- exact-plan approval hash;
- copy-only mutation;
- fresh saved-output verification;
- deterministic fallback, timeout, and circuit breaker.

The AI is not used to calculate geometry or certify results.

## 3. Innovation & Creativity

Defensible differentiation, without claiming “first”:

**existing editable deck + physical viewing geometry + bounded AI repair choice + exact approval + saved-artifact verification**.

Positioning: “responsive design for physical spaces,” implemented conservatively for supported structural text.

## 4. Execution & Completeness

Evidence:
- no-login one-click demo;
- public deployment;
- explicit failure/review states;
- source immutability;
- capability-protected sessions;
- bounded renderer/runtime resources;
- automated deterministic/security/resource tests;
- release ID tying deployment to source/evidence.

## 5. Presentation & Communication

Judge should understand within 30 seconds:

1. the room changes the viewing demand;
2. deterministic code measures supported facts;
3. AI selects among bounded safe alternatives;
4. the user approves;
5. the saved artifact, not the model, determines success.

Recommended close: **“The planner recommends. The verifier decides.”**
