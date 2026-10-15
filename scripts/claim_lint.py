from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    ROOT / "README.md",
    ROOT / "frontend/static/index.html",
    ROOT / "docs/DEMO_SCRIPT.md",
    ROOT / "docs/FORGEHACKS_JUDGING_MAP.md",
    ROOT / "docs/FORGEHACKS_SPEC.md",
    ROOT / "docs/SUBMISSION_CHECKLIST.md",
]

BANNED_PATTERNS = {
    "stale_wcc_branding": re.compile(r"WCC Launchpad|Track 01 Agentic", re.I),
    "avixa_certification_claim": re.compile(r"\b(?:is|are|becomes?|makes?)\s+AVIXA[- ]certified\b", re.I),
    "wcag_compliance_claim": re.compile(r"\b(?:is|are|becomes?|makes?)\s+WCAG[- ]compliant\b", re.I),
    "universal_readability_claim": re.compile(
        r"\b(?:guarantees?|ensures?|proves?)\s+(?:that\s+)?(?:every|all)\s+(?:viewer|person|audience member).{0,40}\bread",
        re.I | re.S,
    ),
    "unqualified_readability_verification": re.compile(
        r"\b(?:verifies?|verified|guarantees?|ensures?)\s+(?:that\s+)?(?:the\s+)?(?:deck|presentation|slides?).{0,40}\breadable\b",
        re.I | re.S,
    ),
}

errors: list[str] = []
for path in FILES:
    if not path.exists():
        errors.append(f"missing:{path.relative_to(ROOT)}")
        continue
    text = path.read_text(encoding="utf-8")
    for label, pattern in BANNED_PATTERNS.items():
        if pattern.search(text):
            errors.append(f"{label}:{path.relative_to(ROOT)}")

required_frontend = [
    "DeckFit AI · Presentation preflight",
    "VERIFIED means only",
    "Titles never auto-mutate",
    "Color contrast",
]
frontend = (ROOT / "frontend/static/index.html").read_text(encoding="utf-8")
for phrase in required_frontend:
    if phrase not in frontend:
        errors.append(f"missing_frontend_claim_guard:{phrase}")

if errors:
    print("CLAIM LINT FAIL")
    for e in errors:
        print("-", e)
    raise SystemExit(1)
print("CLAIM LINT PASS")
