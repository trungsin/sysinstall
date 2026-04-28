"""Tests for iso.checksum.sha256_stream."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from sysinstall.iso.checksum import sha256_stream


class TestSha256Stream:
    def test_known_vector_hello(self, tmp_path: Path) -> None:
        """sha256(b'hello') must match the known digest."""
        f = tmp_path / "hello.bin"
        f.write_bytes(b"hello")
        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_stream(f) == expected

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_stream(f) == expected

    def test_multi_chunk(self, tmp_path: Path) -> None:
        """File larger than one chunk is hashed correctly."""
        data = b"x" * (6 * 1024 * 1024)  # 6 MiB — two 4 MiB chunks
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        # Use a small chunk size to force multiple iterations.
        assert sha256_stream(f, chunk=4 * 1024 * 1024) == expected

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        """Progress callback must be invoked at least once per chunk."""
        data = b"a" * (3 * 1024 * 1024)  # 3 MiB
        f = tmp_path / "data.bin"
        f.write_bytes(data)

        calls: list[tuple[int, int]] = []
        sha256_stream(f, chunk=1 * 1024 * 1024, on_progress=lambda d, t: calls.append((d, t)))

        assert len(calls) == 3  # one call per 1 MiB chunk
        # Final call must report full file size.
        assert calls[-1][0] == len(data)
        assert calls[-1][1] == len(data)

    def test_progress_total_always_full_size(self, tmp_path: Path) -> None:
        """Total reported to progress must always equal file size."""
        data = b"b" * (2 * 1024 * 1024 + 7)
        f = tmp_path / "odd.bin"
        f.write_bytes(data)

        totals: list[int] = []
        sha256_stream(f, chunk=1 * 1024 * 1024, on_progress=lambda d, t: totals.append(t))

        assert all(t == len(data) for t in totals)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sha256_stream(tmp_path / "nonexistent.iso")
