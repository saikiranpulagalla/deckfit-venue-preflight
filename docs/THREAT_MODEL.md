# Threat Model

## Assets

- immutable uploaded source PPTX;
- exact approved repair plan;
- generated output artifact;
- session capability token;
- integrity of `VERIFIED`.

## Trust boundaries

### Untrusted
- uploaded PPTX bytes and all slide content;
- filenames;
- model output;
- client-supplied candidate IDs/plan hash;
- venue measurements supplied by a user.

### Deterministic authority
- intake limits/package validation;
- renderer/structural analysis;
- reference lookup;
- candidate generation/simulation;
- title/semantic-rewrite prohibitions;
- plan-hash construction;
- mutation execution;
- saved-output verification.

## Critical failure classes

1. **False VERIFIED:** unknown/unsupported content disappears from coverage.
2. **Approval drift:** source/candidate/constraint/simulation changes after approval.
3. **AI authority escape:** model invents mutation parameters, IDs, or success state.
4. **Source mutation:** original uploaded deck changes.
5. **Cross-session access:** public session handle is mistaken for authorization.
6. **Renderer ambiguity:** font substitution, AutoFit, wrapping, overflow, overlap, or missing render evidence.
7. **Scientific claim leakage:** structural reference output is described as a guarantee of human readability/accessibility.
8. **Runtime exhaustion:** unbounded uploads/renders/sessions deny the judge path.

## Fail-closed policy

Uncertainty becomes `REVIEW_REQUIRED`, `NO_FEASIBLE_PLAN`, or request rejection—not `VERIFIED`.

`VERIFIED` is allowed only when the saved artifact reopens and every supported mechanical invariant holds with no detected unknown/outside-reference/unsupported-visible condition.

## Runtime AI privacy boundary

Competition V1 does not send raw uploaded PPTX bytes, slide screenshots, speaker notes, or slide text to Gemini. The planner receives derived candidate/context metadata only. This keeps arbitrary presentation content out of the runtime AI request while retaining a bounded planning role.
