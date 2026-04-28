"""SHA-256 streaming checksum helper.

Streams in chunks to avoid loading large ISOs into memory.
Progress callback receives (bytes_done, bytes_total).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path


def sha256_stream(
    path: Path,
    chunk: int = 4 * 1024 * 1024,
    on_progress: Callable[[int, int], None] | None = None,
) -> str:
    """Compute SHA-256 of *path* by streaming in *chunk*-byte blocks.

    Args:
        path: File to hash.
        chunk: Read chunk size in bytes (default 4 MiB).
        on_progress: Optional callback invoked after each chunk with
            ``(bytes_done, bytes_total)``.

    Returns:
        Lowercase hex digest string.

    Raises:
        FileNotFoundError: *path* does not exist.
        OSError: file cannot be opened/read.
    """
    total = path.stat().st_size
    digest = hashlib.sha256()
    done = 0

    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
            done += len(block)
            if on_progress is not None:
                on_progress(done, total)

    return digest.hexdigest()
