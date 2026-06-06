"""Checksum utilities for dataset output files.

Generates SHA-256 checksums for dataset files to verify integrity.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_hex(path: Path) -> str:
    """Compute SHA-256 hex digest of a file.

    Args:
        path: Path to the file.

    Returns:
        SHA-256 hex digest string.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_checksums(dist_dir: Path, files: list[str]) -> dict[str, str]:
    """Compute SHA-256 checksums for the given files.

    Args:
        dist_dir: Path to the dist/ directory.
        files: List of relative file paths within dist_dir.

    Returns:
        Dict mapping relative file path to SHA-256 hex digest.
    """
    checksums: dict[str, str] = {}
    for file_name in files:
        file_path = dist_dir / file_name
        if file_path.is_file():
            checksums[file_name] = sha256_hex(file_path)
    return checksums
