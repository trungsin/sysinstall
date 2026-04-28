"""Tests for iso.copy.stream_copy — atomic copy with sha256."""

from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from sysinstall.iso.copy import stream_copy


def _random_bytes(size: int) -> bytes:
    rng = random.Random(42)
    return bytes(rng.getrandbits(8) for _ in range(size))


class TestStreamCopy:
    def test_copy_produces_identical_file(self, tmp_path: Path) -> None:
        data = _random_bytes(1 * 1024 * 1024)  # 1 MiB
        src = tmp_path / "source.iso"
        dst = tmp_path / "dest.iso"
        src.write_bytes(data)

        bytes_copied, sha = stream_copy(src, dst)

        assert dst.exists()
        assert dst.read_bytes() == data
        assert bytes_copied == len(data)

    def test_returned_sha256_matches(self, tmp_path: Path) -> None:
        data = _random_bytes(1 * 1024 * 1024)
        src = tmp_path / "source.iso"
        dst = tmp_path / "dest.iso"
        src.write_bytes(data)

        _bytes_copied, sha = stream_copy(src, dst)

        expected = hashlib.sha256(data).hexdigest()
        assert sha == expected

    def test_part_file_deleted_on_failure(self, tmp_path: Path) -> None:
        """If an error occurs mid-copy the .part file must be cleaned up."""
        data = _random_bytes(512 * 1024)
        src = tmp_path / "source.iso"
        dst = tmp_path / "dest.iso"
        src.write_bytes(data)

        part = dst.with_suffix(dst.suffix + ".part")

        # Patch os.fsync to raise IOError after write begins.
        with patch("sysinstall.iso.copy.os.fsync", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                stream_copy(src, dst)

        assert not part.exists(), ".part file was not cleaned up after failure"
        assert not dst.exists(), "dst should not exist after failure"

    def test_dst_does_not_exist_before_completion(self, tmp_path: Path) -> None:
        """dst must not appear until the rename succeeds."""
        data = _random_bytes(256 * 1024)
        src = tmp_path / "source.iso"
        dst = tmp_path / "dest.iso"
        src.write_bytes(data)

        seen_dst_during_copy: list[bool] = []

        original_write = os.write  # not used directly; track via progress callback

        def on_progress(done: int, total: int) -> None:
            seen_dst_during_copy.append(dst.exists())

        stream_copy(src, dst, on_progress=on_progress)

        # dst must not have existed during the copy (only the .part should).
        assert not any(seen_dst_during_copy), "dst appeared before rename"
        assert dst.exists()

    def test_progress_callback_invoked(self, tmp_path: Path) -> None:
        data = _random_bytes(1 * 1024 * 1024)
        src = tmp_path / "source.iso"
        dst = tmp_path / "dest.iso"
        src.write_bytes(data)

        calls: list[tuple[int, int]] = []
        stream_copy(src, dst, on_progress=lambda d, t: calls.append((d, t)))

        assert len(calls) >= 1
        assert calls[-1][0] == len(data)

    def test_missing_source_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            stream_copy(tmp_path / "missing.iso", tmp_path / "dst.iso")
