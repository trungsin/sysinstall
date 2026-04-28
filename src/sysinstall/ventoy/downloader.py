"""Ventoy binary downloader — fetch, cache, and SHA256-verify the upstream archive.

Cache layout: ~/.cache/sysinstall/ventoy/<version>/<filename>
Atomic write: download to .tmp sibling, rename on success.
Retry: 3 attempts with exponential backoff (1s, 2s, 4s).
No third-party deps — stdlib urllib only.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from sysinstall.ventoy.manifest import VENTOY_VERSION, get_artifact

log = logging.getLogger(__name__)

# Seconds between retry attempts (doubles each time).
_RETRY_BASE_DELAY = 1.0
_MAX_RETRIES = 3
# Read chunk size for streaming download + hashing.
_CHUNK_SIZE = 1 << 16  # 64 KiB


def _cache_dir() -> Path:
    """Return the versioned cache directory, creating it if needed."""
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache = base / "sysinstall" / "ventoy" / VENTOY_VERSION
    cache.mkdir(parents=True, exist_ok=True)
    return cache


def _sha256_file(path: Path) -> str:
    """Return lowercase hex SHA256 of a file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_to(url: str, dest: Path) -> None:
    """Download *url* into *dest*, streaming through SHA256 hash.

    Uses an atomic write: data goes to a temp file next to *dest*, then
    renamed. The rename is omitted here — caller does the final rename
    after verifying checksum.
    """
    log.info("Downloading %s -> %s", url, dest)
    req = urllib.request.Request(url, headers={"User-Agent": "sysinstall-downloader/1"})
    with urllib.request.urlopen(req, timeout=30) as resp, dest.open("wb") as fh:  # noqa: S310
        while True:
            chunk = resp.read(_CHUNK_SIZE)
            if not chunk:
                break
            fh.write(chunk)


def fetch_ventoy(platform_key: str) -> Path:
    """Fetch the Ventoy archive for *platform_key*, returning its cached path.

    If already cached with a valid checksum, returns immediately without
    re-downloading.

    Args:
        platform_key: e.g. "linux-x64" or "windows-x64".

    Returns:
        Path to the verified cached archive.

    Raises:
        KeyError: unknown platform key.
        NotImplementedError: SHA256 placeholder not yet pinned.
        RuntimeError: download or verification failed after all retries.
    """
    filename, expected_sha, url = get_artifact(platform_key)
    cache = _cache_dir()
    dest = cache / filename

    # Fast path — already cached and checksum matches.
    if dest.exists():
        actual = _sha256_file(dest)
        if actual == expected_sha:
            log.debug("Cache hit: %s (sha256 ok)", dest)
            return dest
        log.warning("Cache file %s has wrong sha256 (%s); re-downloading.", dest, actual)
        dest.unlink()

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        tmp_path: Path | None = None
        try:
            # Write to a temp file in the same directory for atomic rename.
            fd, tmp_str = tempfile.mkstemp(dir=cache, prefix=filename + ".tmp")
            os.close(fd)
            tmp_path = Path(tmp_str)

            _download_to(url, tmp_path)

            actual_sha = _sha256_file(tmp_path)
            if actual_sha != expected_sha:
                raise RuntimeError(
                    f"SHA256 mismatch for {filename}: "
                    f"expected {expected_sha}, got {actual_sha}. "
                    "Aborting — do not use this file."
                )

            # Atomic rename: either the file is complete+verified or absent.
            tmp_path.rename(dest)
            tmp_path = None  # rename succeeded; don't delete in finally.
            log.info("Downloaded and verified %s", dest)
            return dest

        except RuntimeError:
            # SHA mismatch is a hard error — no point retrying.
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            log.warning("Download attempt %d/%d failed: %s", attempt, _MAX_RETRIES, exc)
            if attempt < _MAX_RETRIES:
                delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                log.debug("Retrying in %.1fs…", delay)
                time.sleep(delay)
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    raise RuntimeError(
        f"Failed to download {url} after {_MAX_RETRIES} attempts. "
        f"Last error: {last_error}"
    )
