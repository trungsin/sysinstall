"""Tests for the Linux Ventoy stdout progress parser (pure function)."""

from __future__ import annotations

from pathlib import Path

from sysinstall.ventoy.runner_linux_progress import parse_progress

FIXTURES = Path(__file__).parent / "fixtures"


def _lines(filename: str):
    return iter((FIXTURES / filename).read_text().splitlines())


class TestParseProgress:
    def test_extracts_percentages_from_fixture(self):
        received: list[int] = []
        result = parse_progress(_lines("ventoy-linux-stdout.txt"), on_progress=received.append)
        assert result == [10, 50, 75, 100]
        assert received == [10, 50, 75, 100]

    def test_callback_fires_for_each_pct(self):
        lines = iter(["10%", "20%", "100%"])
        fired: list[int] = []
        parse_progress(lines, on_progress=fired.append)
        assert fired == [10, 20, 100]

    def test_no_callback_returns_list(self):
        lines = iter(["50%"])
        result = parse_progress(lines, on_progress=None)
        assert result == [50]

    def test_empty_input_returns_empty(self):
        result = parse_progress(iter([]))
        assert result == []

    def test_no_pct_in_lines_returns_empty(self):
        result = parse_progress(iter(["Ventoy Install OK.", "Done."]))
        assert result == []

    def test_multiple_pct_on_one_line(self):
        # Edge case: two percentages on same line.
        lines = iter(["Start 10% ... 20%"])
        result = parse_progress(lines)
        assert result == [10, 20]

    def test_clamps_above_100(self):
        lines = iter(["999%"])
        result = parse_progress(lines)
        assert result == [100]

    def test_clamps_below_0(self):
        # Parser only captures \d+, so negative won't match — but 0 is valid.
        lines = iter(["0%"])
        result = parse_progress(lines)
        assert result == [0]

    def test_pct_with_surrounding_text(self):
        lines = iter(["Done: 100%", "Format partition ... 10%"])
        result = parse_progress(lines)
        assert result == [100, 10]
