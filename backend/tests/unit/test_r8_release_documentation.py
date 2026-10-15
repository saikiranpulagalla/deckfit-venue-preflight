from pathlib import Path


def test_readme_points_to_current_r8_evidence_not_historical_generic_status():
    root = Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text(encoding="utf-8")
    current = root / "validation" / "R8_RELEASE_STATUS.md"
    assert "validation/R8_RELEASE_STATUS.md" in readme
    assert current.exists()
    text = current.read_text(encoding="utf-8")
    assert "exported R8 source snapshot" in text
    assert "183 tests collected" in text
    assert "These are not a full-suite result" in text
