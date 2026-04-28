"""Tests for the Ventoy downloader — atomic write, SHA256 verify, retry.

Uses a local http.server fixture instead of hitting GitHub.
"""

from __future__ import annotations

import hashlib
import http.server
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from sysinstall.ventoy.downloader import _sha256_file, fetch_ventoy

# ---------------------------------------------------------------------------
# Local HTTP server fixture
# ---------------------------------------------------------------------------

class _ThreadedHTTPServer(http.server.HTTPServer):
    """HTTPServer that handles requests in a daemon thread."""


def _make_handler(content: bytes):
    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass  # suppress test output

    return _Handler


@pytest.fixture()
def local_http_server(tmp_path):
    """Yield (url_base, content, sha256) for a simple file served locally."""
    content = b"fake ventoy archive content for testing"
    sha256 = hashlib.sha256(content).hexdigest()
    handler = _make_handler(content)
    server = _ThreadedHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", content, sha256
    server.shutdown()


# ---------------------------------------------------------------------------
# SHA256 helper tests
# ---------------------------------------------------------------------------

class TestSha256File:
    def test_correct_hash(self, tmp_path: Path):
        data = b"hello world"
        f = tmp_path / "test.bin"
        f.write_bytes(data)
        assert _sha256_file(f) == hashlib.sha256(data).hexdigest()

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        assert _sha256_file(f) == hashlib.sha256(b"").hexdigest()


# ---------------------------------------------------------------------------
# Atomic write + SHA verify tests
# ---------------------------------------------------------------------------

class TestFetchVentoy:
    def test_atomic_write_and_verify(self, tmp_path: Path, local_http_server):
        url_base, content, sha256 = local_http_server
        filename = "ventoy-test-linux.tar.gz"
        url = f"{url_base}/{filename}"

        # Patch manifest to point at local server with correct SHA.
        with (
            patch("sysinstall.ventoy.downloader._cache_dir", return_value=tmp_path),
            patch(
                "sysinstall.ventoy.downloader.get_artifact",
                return_value=(filename, sha256, url),
            ),
        ):
            result = fetch_ventoy("linux-x64")

        assert result == tmp_path / filename
        assert result.exists()
        assert _sha256_file(result) == sha256

    def test_sha_mismatch_raises(self, tmp_path: Path, local_http_server):
        url_base, content, _ = local_http_server
        filename = "ventoy-test.tar.gz"
        url = f"{url_base}/{filename}"
        wrong_sha = "a" * 64  # wrong checksum

        with (
            patch("sysinstall.ventoy.downloader._cache_dir", return_value=tmp_path),
            patch(
                "sysinstall.ventoy.downloader.get_artifact",
                return_value=(filename, wrong_sha, url),
            ),pytest.raises(RuntimeError, match="SHA256 mismatch")
        ):
            fetch_ventoy("linux-x64")

        # Temp file must be cleaned up after mismatch.
        tmp_files = list(tmp_path.glob("*.tmp*"))
        assert tmp_files == [], f"Temp files not cleaned up: {tmp_files}"

    def test_cache_hit_skips_download(self, tmp_path: Path):
        content = b"cached content"
        sha256 = hashlib.sha256(content).hexdigest()
        filename = "ventoy-cached.tar.gz"
        cached = tmp_path / filename
        cached.write_bytes(content)

        download_called = []

        def _fake_download(url, dest):
            download_called.append(url)

        with (
            patch("sysinstall.ventoy.downloader._cache_dir", return_value=tmp_path),
            patch(
                "sysinstall.ventoy.downloader.get_artifact",
                return_value=(filename, sha256, "http://unused/"),
            ),
            patch("sysinstall.ventoy.downloader._download_to", side_effect=_fake_download),
        ):
            result = fetch_ventoy("linux-x64")

        assert result == cached
        assert download_called == [], "Download was called despite cache hit"

    def test_stale_cache_redownloads(self, tmp_path: Path, local_http_server):
        url_base, content, sha256 = local_http_server
        filename = "ventoy-stale.tar.gz"
        url = f"{url_base}/{filename}"

        # Write a stale file with wrong content.
        stale = tmp_path / filename
        stale.write_bytes(b"wrong content")

        with (
            patch("sysinstall.ventoy.downloader._cache_dir", return_value=tmp_path),
            patch(
                "sysinstall.ventoy.downloader.get_artifact",
                return_value=(filename, sha256, url),
            ),
        ):
            result = fetch_ventoy("linux-x64")

        assert _sha256_file(result) == sha256

    def test_retry_on_network_failure(self, tmp_path: Path, local_http_server):
        url_base, content, sha256 = local_http_server
        filename = "ventoy-retry.tar.gz"
        url = f"{url_base}/{filename}"

        call_count = [0]
        original_download = __import__(
            "sysinstall.ventoy.downloader", fromlist=["_download_to"]
        )._download_to

        def _flaky_download(u, dest):
            call_count[0] += 1
            if call_count[0] < 2:
                raise OSError("Simulated network failure")
            # Write real content on second attempt.
            dest.write_bytes(content)

        with (
            patch("sysinstall.ventoy.downloader._cache_dir", return_value=tmp_path),
            patch(
                "sysinstall.ventoy.downloader.get_artifact",
                return_value=(filename, sha256, url),
            ),
            patch("sysinstall.ventoy.downloader._download_to", side_effect=_flaky_download),
            patch("sysinstall.ventoy.downloader.time.sleep"),  # no real sleep
        ):
            result = fetch_ventoy("linux-x64")

        assert call_count[0] == 2
        assert result.exists()
