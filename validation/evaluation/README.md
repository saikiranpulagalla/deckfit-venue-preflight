# ForgeHacks evaluation evidence

Venue Agent does not collapse evaluation into one accuracy number.

- **Safety:** zero-tolerance authorization/verification invariants.
- **Utility:** supported workflows must actually complete; always returning `REVIEW_REQUIRED` is not success.
- **Model validity:** reference-bound structural claims remain narrow and estimated near-threshold cases fail to review.
- **AI boundary:** Gemini may select legal candidate IDs and explain the trade-off, but deterministic code owns geometry, mutation authority and final verification.

`planner_study_cases.json` contains synthetic metadata only. It is intentionally content-free so live study runs do not send user slide text or images to Gemini.

`scripts/planner_study.py` compares deterministic and optional live-Gemini choices. Its output is **characterization evidence only** until blinded human ratings are collected with `planner_ratings_template.json`. Do not claim the model is superior to the deterministic baseline merely because it returns valid JSON or a different plan.

`scripts/evaluation_scoreboard.py --include-resource` runs mapped evidence nodes in isolated subprocesses and emits a machine-readable scoreboard.
