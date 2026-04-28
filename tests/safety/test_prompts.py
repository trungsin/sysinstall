"""Tests for safety prompts: banner output, countdown timing, rate-limit cache."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, call, patch

import pytest
import typer

from sysinstall.disks.base import Disk
from sysinstall.safety.prompts import (
    _RATE_LIMIT_SECONDS,
    _is_rate_limited,
    _record_prompt,
    _run_countdown,
    clear_rate_limit_cache,
    confirm_with_banner,
    show_destructive_banner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_disk() -> Disk:
    return Disk(
        id="usb:TestModel:SN123",
        path="/dev/sdb",
        size_bytes=16 * 1024**3,
        model="TestModel",
        serial="SN123",
        bus="usb",
        is_removable=True,
        is_system=False,
        partitions=(),
    )


# ---------------------------------------------------------------------------
# Rate-limit cache
# ---------------------------------------------------------------------------


class TestRateLimitCache:
    def setup_method(self) -> None:
        clear_rate_limit_cache()

    def test_not_rate_limited_initially(self) -> None:
        assert not _is_rate_limited("disk:1", "op_a")

    def test_rate_limited_after_record(self) -> None:
        _record_prompt("disk:1", "op_a")
        assert _is_rate_limited("disk:1", "op_a")

    def test_different_ops_not_shared(self) -> None:
        _record_prompt("disk:1", "op_a")
        assert not _is_rate_limited("disk:1", "op_b")

    def test_different_disks_not_shared(self) -> None:
        _record_prompt("disk:1", "op_a")
        assert not _is_rate_limited("disk:2", "op_a")

    def test_rate_limit_expires_after_window(self) -> None:
        _record_prompt("disk:1", "op_a")
        # Simulate time passing beyond the limit window by backdating cache entry.
        from sysinstall.safety import prompts as prompts_mod
        prompts_mod._rate_limit_cache[("disk:1", "op_a")] = (
            time.monotonic() - _RATE_LIMIT_SECONDS - 1
        )
        assert not _is_rate_limited("disk:1", "op_a")

    def test_clear_resets_all_entries(self) -> None:
        _record_prompt("disk:1", "op_a")
        _record_prompt("disk:2", "op_b")
        clear_rate_limit_cache()
        assert not _is_rate_limited("disk:1", "op_a")
        assert not _is_rate_limited("disk:2", "op_b")

    def test_second_confirm_within_window_auto_passes(self) -> None:
        """Two confirm_with_banner calls within 60 s for same (disk, op) -> second skips prompt."""
        disk = _make_disk()
        with (
            patch("sysinstall.safety.prompts._run_countdown"),
            patch("sysinstall.safety.prompts._console"),
        ):
            # First call — records timestamp
            confirm_with_banner(disk, "op_a", confirmed=True, no_banner=True)
            # Second call within 60 s — should auto-pass without prompting
            prompt_mock = MagicMock()
            with patch("typer.prompt", prompt_mock):
                confirm_with_banner(disk, "op_a", confirmed=False, no_banner=True)
            prompt_mock.assert_not_called()

    def test_second_confirm_outside_window_prompts_again(self) -> None:
        """Two calls outside 60 s -> second call shows prompt."""
        disk = _make_disk()
        clear_rate_limit_cache()
        with (
            patch("sysinstall.safety.prompts._run_countdown"),
            patch("sysinstall.safety.prompts._console"),
        ):
            confirm_with_banner(disk, "op_b", confirmed=True, no_banner=True)
            # Backdate cache entry to expire the window.
            from sysinstall.safety import prompts as prompts_mod
            prompts_mod._rate_limit_cache[(disk.id, "op_b")] = (
                time.monotonic() - _RATE_LIMIT_SECONDS - 1
            )
            with patch("typer.prompt", return_value="yes"):
                confirm_with_banner(disk, "op_b", confirmed=False, no_banner=True)


# ---------------------------------------------------------------------------
# Countdown
# ---------------------------------------------------------------------------


class TestCountdown:
    def test_sleep_called_once_per_second(self) -> None:
        """Mock time.sleep and assert called 5 times with 1s each."""
        with (
            patch("sysinstall.safety.prompts.time") as mock_time,
            patch("rich.progress.Progress.__enter__", return_value=MagicMock()),
            patch("rich.progress.Progress.__exit__", return_value=False),
        ):
            mock_time.sleep = MagicMock()
            mock_time.monotonic = time.monotonic  # keep monotonic real
            _run_countdown(seconds=5)
        assert mock_time.sleep.call_count == 5
        mock_time.sleep.assert_has_calls([call(1)] * 5)

    def test_countdown_skipped_with_no_banner(self) -> None:
        """show_destructive_banner with no_banner=True must not call _run_countdown."""
        disk = _make_disk()
        with patch("sysinstall.safety.prompts._run_countdown") as mock_cd:
            show_destructive_banner(disk, "test op", no_banner=True)
        mock_cd.assert_not_called()

    def test_countdown_runs_without_no_banner(self) -> None:
        disk = _make_disk()
        with (
            patch("sysinstall.safety.prompts._run_countdown") as mock_cd,
            patch("sysinstall.safety.prompts._console"),
        ):
            show_destructive_banner(disk, "test op", no_banner=False)
        mock_cd.assert_called_once()


# ---------------------------------------------------------------------------
# Banner content
# ---------------------------------------------------------------------------


class TestBannerContent:
    def test_banner_contains_disk_info(self) -> None:
        """Banner panel renderable must contain disk path, model, and serial."""
        disk = _make_disk()
        rendered_text: list[str] = []

        class FakeConsole:
            def print(self, *args: object, **kwargs: object) -> None:
                # Rich Panel objects store content in .renderable attribute.
                # Fall back to str() for plain strings.
                for arg in args:
                    from rich.panel import Panel
                    if isinstance(arg, Panel):
                        rendered_text.append(str(arg.renderable))
                    else:
                        rendered_text.append(str(arg))

        with (
            patch("sysinstall.safety.prompts._console", FakeConsole()),
            patch("sysinstall.safety.prompts._run_countdown"),
        ):
            show_destructive_banner(disk, "install Ventoy", no_banner=False)

        combined = " ".join(rendered_text)
        assert disk.path in combined
        assert disk.model in combined
        assert disk.serial in combined

    def test_confirm_flag_skips_interactive_prompt(self) -> None:
        disk = _make_disk()
        clear_rate_limit_cache()
        with (
            patch("sysinstall.safety.prompts._run_countdown"),
            patch("sysinstall.safety.prompts._console"),
            patch("typer.prompt") as mock_prompt,
        ):
            confirm_with_banner(disk, "op_x", confirmed=True, no_banner=True)
        mock_prompt.assert_not_called()

    def test_interactive_no_raises_abort(self) -> None:
        disk = _make_disk()
        clear_rate_limit_cache()
        with (
            patch("sysinstall.safety.prompts._run_countdown"),
            patch("sysinstall.safety.prompts._console"),
            patch("typer.prompt", return_value="no"),pytest.raises(typer.Abort)
        ):
            confirm_with_banner(disk, "op_y", confirmed=False, no_banner=True)
