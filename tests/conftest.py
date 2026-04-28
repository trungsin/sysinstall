"""Pytest configuration and shared fixtures for deterministic testing."""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

# ============================================================================
# Note: Global subprocess guard intentionally disabled
# Tests must opt-in to mocking via the mock_subprocess fixture.
# A session-scoped monkeypatch is not available in standard pytest.
# ============================================================================


# ============================================================================
# Time.sleep mock — safety countdown should not block tests
# ============================================================================

@pytest.fixture(autouse=True)
def _mock_sleep(monkeypatch: Any) -> None:
    """Mock time.sleep to instant (0s) so countdown safety tests run fast."""
    monkeypatch.setattr(time, "sleep", lambda s: None)


# ============================================================================
# mock_subprocess fixture — replaces subprocess.run with recording mock
# ============================================================================

@pytest.fixture
def mock_subprocess(monkeypatch: Any) -> Any:
    """
    Mock subprocess.run to record calls and return fixture-based stdout.

    Usage:
        def test_foo(mock_subprocess):
            # subprocess.run is now mocked
            result = my_function_that_calls_subprocess()
            # Verify call was recorded
            assert len(mock_subprocess.calls) == 1
            assert "expected-arg" in mock_subprocess.calls[0]["cmd"]

    Returns:
        SimpleNamespace with:
            - .calls: list of recorded calls, each {cmd, args, kwargs}
            - .set_return(cmd_pattern, returncode, stdout, stderr):
              Configure return value for cmd matching pattern
    """
    calls: list[dict[str, Any]] = []
    returns: dict[tuple[str, ...], dict[str, Any]] = {}

    def fake_run(
        cmd: list[str] | str,
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        # Normalize cmd to tuple of strings for matching
        if isinstance(cmd, str):
            cmd_tuple = (cmd,)
        else:
            cmd_tuple = tuple(cmd)

        calls.append({"cmd": cmd_tuple, "args": args, "kwargs": kwargs})

        # Find matching return config, or default to success
        matched_return = None
        for pattern, ret_config in returns.items():
            if all(p in cmd_tuple for p in pattern):
                matched_return = ret_config
                break

        if matched_return:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=matched_return.get("returncode", 0),
                stdout=matched_return.get("stdout", ""),
                stderr=matched_return.get("stderr", ""),
            )

        # Default: success with empty stdout
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    def set_return(
        cmd_pattern: tuple[str, ...] | list[str],
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """Configure return value for a cmd pattern (all elements must match)."""
        pattern = tuple(cmd_pattern) if isinstance(cmd_pattern, list) else cmd_pattern
        returns[pattern] = {"returncode": returncode, "stdout": stdout, "stderr": stderr}

    monkeypatch.setattr(subprocess, "run", fake_run)

    return SimpleNamespace(calls=calls, set_return=set_return)


# ============================================================================
# host_skip fixture — skip test by platform
# ============================================================================

def host_skip(
    reason: str | None = None,
    darwin: bool = False,
    linux: bool = False,
    win32: bool = False,
) -> pytest.MarkDecorator:
    """
    Mark a test to skip on certain platforms.

    Usage:
        @host_skip(darwin=True)  # Skip on macOS
        def test_foo(): ...

        @host_skip(linux=True, reason="feature not on Linux yet")
        def test_bar(): ...
    """
    should_skip = False
    skip_reason = reason or "Platform not supported for this test"

    if sys.platform == "darwin" and darwin or sys.platform == "linux" and linux or sys.platform == "win32" and win32:
        should_skip = True

    return pytest.mark.skipif(should_skip, reason=skip_reason)


# ============================================================================
# Platform detection helpers
# ============================================================================

@pytest.fixture
def on_darwin() -> bool:
    """Return True if running on macOS."""
    return sys.platform == "darwin"


@pytest.fixture
def on_linux() -> bool:
    """Return True if running on Linux."""
    return sys.platform == "linux"


@pytest.fixture
def on_win32() -> bool:
    """Return True if running on Windows."""
    return sys.platform == "win32"


# ============================================================================
# Fixture: load_fixture_file
# ============================================================================

@pytest.fixture
def load_fixture_file() -> Callable[[str], str]:
    """
    Load a fixture file by relative path from tests/fixtures/.

    Usage:
        def test_foo(load_fixture_file):
            plist_data = load_fixture_file("disks/diskutil-macos-internal-ssd.plist")
            disk = parse_plist(plist_data)
    """
    fixtures_dir = Path(__file__).parent / "fixtures"

    def _load(relative_path: str) -> str:
        file_path = fixtures_dir / relative_path
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture not found: {file_path}")
        return file_path.read_text()

    return _load


# ============================================================================
# Fixture: load_fixture_bytes
# ============================================================================

@pytest.fixture
def load_fixture_bytes() -> Callable[[str], bytes]:
    """
    Load a fixture file as bytes by relative path from tests/fixtures/.

    Usage:
        def test_foo(load_fixture_bytes):
            plist_bytes = load_fixture_bytes("disks/diskutil-macos-internal-ssd.plist")
    """
    fixtures_dir = Path(__file__).parent / "fixtures"

    def _load(relative_path: str) -> bytes:
        file_path = fixtures_dir / relative_path
        if not file_path.exists():
            raise FileNotFoundError(f"Fixture not found: {file_path}")
        return file_path.read_bytes()

    return _load


# ============================================================================
# Shared pytest.ini config applied here
# ============================================================================

def pytest_configure(config: Any) -> None:
    """Configure pytest markers and defaults."""
    # Register custom markers
    config.addinivalue_line(
        "markers",
        "smoke: VM smoke test (not run by default, use -m smoke to run)",
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration test requiring real host state (runs on CI)",
    )
    config.addinivalue_line(
        "markers",
        "slow: Slow test (consider with -m slow or skip with -m 'not slow')",
    )
