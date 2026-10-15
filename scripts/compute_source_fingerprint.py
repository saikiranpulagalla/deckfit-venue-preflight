"""Compute source fingerprint for the exact export being deployed."""
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from app.security.build_identity import source_fingerprint
print(source_fingerprint(root))
