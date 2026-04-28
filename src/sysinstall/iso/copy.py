"""Atomic streaming copy with single-pass SHA-256.

Writes to a .part sibling, computes sha256 in-flight, then renames on
success.  On any exception the .part file is deleted — no partial files
are left behind.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

_CHUNK = 4 * 1024 * 1024  # 4 MiB


def stream_copy(
    src: Path,
    dst: Path,
    *,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, str]:
    """Copy *src* to *dst* atomically, computing sha256 in a single pass.

    The copy is written to ``dst.name + ".part"`` first; on success the
    file is fsync'd and renamed to *dst*.  Any exception deletes the
    partial file so callers can trust dst either exists intact or not at all.

    Args:
        src: Source file path.
        dst: Destination file path (must not already exist as a partial).
        on_progress: Optional callback invoked after each chunk with
            ``(bytes_done, bytes_total)``.

    Returns:
        ``(bytes_copied, sha256_hex)`` — the sha256 is computed over the
        source bytes during the copy; no second read of dst is needed.

    Raises:
        FileNotFoundError: *src* does not exist.
        OSError: read/write failure.
    """
    part = dst.with_suffix(dst.suffix + ".part")
    total = src.stat().st_size
    digest = hashlib.sha256()
    copied = 0

    try:
        with src.open("rb") as src_fh, part.open("wb") as dst_fh:
            while True:
                block = src_fh.read(_CHUNK)
                if not block:
                    break
                dst_fh.write(block)
                digest.update(block)
                copied += len(block)
                if on_progress is not None:
                    on_progress(copied, total)
            # Flush OS buffers then sync to persistent storage.
            dst_fh.flush()
            os.fsync(dst_fh.fileno())

        part.rename(dst)
        log.debug("Copied %d bytes from %s to %s", copied, src, dst)
    except Exception:
        # Best-effort cleanup — don't mask the original exception.
        try:
            if part.exists():
                part.unlink()
                log.debug("Deleted partial file %s", part)
        except OSError as cleanup_err:
            log.warning("Failed to delete partial file %s: %s", part, cleanup_err)
        raise

    return copied, digest.hexdigest()
