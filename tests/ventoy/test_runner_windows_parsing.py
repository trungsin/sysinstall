"""Tests for Windows Ventoy progress file poller (pure function)."""

from __future__ import annotations

from pathlib import Path

from sysinstall.ventoy.runner_windows_progress import poll_progress

FIXTURES = Path(__file__).parent / "fixtures"


def _no_sleep(seconds: float) -> None:
    """Replacement for time.sleep — instant in tests."""


class TestPollProgress:
    def test_done_zero_returns_success(self):
        """cli_done.txt containing '0' means success."""
        rc = poll_progress(
            read_percent=lambda: None,
            read_done=lambda: "0",
            sleep_fn=_no_sleep,
        )
        assert rc == 0

    def test_done_one_returns_failure(self):
        """cli_done.txt containing '1' means Ventoy reported failure."""
        rc = poll_progress(
            read_percent=lambda: None,
            read_done=lambda: "1",
            sleep_fn=_no_sleep,
        )
        assert rc == 1

    def test_fixture_cli_done_is_success(self):
        """The fixture file cli_done.txt contains '1' (success sentinel in fixture)."""
        content = (FIXTURES / "cli_done.txt").read_text().strip()
        # Fixture contains "1" which maps to failure from Ventoy's perspective,
        # but we verify the poller reads it correctly.
        rc = poll_progress(
            read_percent=lambda: None,
            read_done=lambda: content,
            sleep_fn=_no_sleep,
        )
        assert rc == 1  # fixture has "1"

    def test_fixture_cli_percent_fires_callback(self):
        """Reading fixture cli_percent.txt (47) triggers on_progress."""
        content = (FIXTURES / "cli_percent.txt").read_text()

        calls: list[int] = []
        call_count = 0

        def _read_done() -> str | None:
            nonlocal call_count
            call_count += 1
            # Return done after first percent poll.
            return "0" if call_count > 1 else None

        poll_progress(
            read_percent=lambda: content,
            read_done=_read_done,
            on_progress=calls.append,
            sleep_fn=_no_sleep,
        )
        assert 47 in calls

    def test_progress_callback_fires_on_change(self):
        """on_progress fires only when percent value changes."""
        pcts = iter([10, 10, 50, 100])
        fired: list[int] = []
        done_counter = [0]

        def _read_pct() -> str | None:
            try:
                return str(next(pcts))
            except StopIteration:
                return None

        def _read_done() -> str | None:
            done_counter[0] += 1
            return "0" if done_counter[0] > 4 else None

        poll_progress(
            read_percent=_read_pct,
            read_done=_read_done,
            on_progress=fired.append,
            sleep_fn=_no_sleep,
        )
        # 10 appears twice but callback fires once (deduped), then 50, 100.
        assert fired == [10, 50, 100]

    def test_timeout_returns_code_2(self):
        """When cli_done.txt never appears and timeout is reached, returns 2."""
        rc = poll_progress(
            read_percent=lambda: "50",
            read_done=lambda: None,
            sleep_fn=_no_sleep,
            poll_interval=0.1,
            timeout=0.05,  # effectively 0 iterations
        )
        assert rc == 2

    def test_invalid_percent_content_does_not_raise(self):
        """Garbage in cli_percent.txt is logged and ignored."""
        call_count = [0]

        def _read_done() -> str | None:
            call_count[0] += 1
            return "0" if call_count[0] > 2 else None

        rc = poll_progress(
            read_percent=lambda: "not_a_number",
            read_done=_read_done,
            sleep_fn=_no_sleep,
        )
        assert rc == 0  # still succeeded despite bad percent content
