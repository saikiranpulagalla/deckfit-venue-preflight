"""Source-bound release fingerprint independent of operator-provided release label.

This is a reproducible checksum of deployed source, not a signed attestation of
Railway's container or an assertion that an untrusted server cannot lie.
"""
from __future__ import annotations

from pathlib import Path
import hashlib


def source_fingerprint(root: Path) -> str:
    files = sorted(p for p in (root / 'backend/app').rglob('*.py') if p.is_file())
    files.extend(root / name for name in ('frontend/static/index.html', 'Dockerfile', 'railway.json',
                                          'reference/PUBLIC_BDM_REFERENCE_V1.json'))
    digest = hashlib.sha256()
    for file in sorted(files):
        rel = file.relative_to(root).as_posix().encode('utf-8')
        data = file.read_bytes()
        digest.update(len(rel).to_bytes(4, 'big'))
        digest.update(rel)
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()
