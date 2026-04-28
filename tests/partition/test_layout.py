"""Tests for DualBootLayout validators."""

from __future__ import annotations

import pytest

from sysinstall.partition.layout import (
    DualBootLayout,
    LayoutTooLargeError,
    LayoutValidationError,
)

_500GB = 500 * 1024 * 1024 * 1024


class TestWindowsSizeValidation:
    def test_minimum_accepted(self) -> None:
        layout = DualBootLayout(windows_size_gb=30, swap_size_gb=0)
        assert layout.windows_size_gb == 30

    def test_below_minimum_raises(self) -> None:
        with pytest.raises(LayoutValidationError, match="windows_size_gb=29"):
            DualBootLayout(windows_size_gb=29, swap_size_gb=0)

    def test_zero_raises(self) -> None:
        with pytest.raises(LayoutValidationError):
            DualBootLayout(windows_size_gb=0, swap_size_gb=0)

    def test_large_accepted(self) -> None:
        layout = DualBootLayout(windows_size_gb=400, swap_size_gb=0, disk_size_bytes=_500GB)
        assert layout.windows_size_gb == 400


class TestSwapSizeValidation:
    def test_zero_accepted(self) -> None:
        layout = DualBootLayout(windows_size_gb=50, swap_size_gb=0)
        assert layout.swap_size_gb == 0

    def test_max_accepted(self) -> None:
        layout = DualBootLayout(windows_size_gb=50, swap_size_gb=32)
        assert layout.swap_size_gb == 32

    def test_above_max_raises(self) -> None:
        with pytest.raises(LayoutValidationError, match="swap_size_gb=33"):
            DualBootLayout(windows_size_gb=50, swap_size_gb=33)

    def test_negative_raises(self) -> None:
        with pytest.raises(LayoutValidationError):
            DualBootLayout(windows_size_gb=50, swap_size_gb=-1)


class TestDiskSizeValidation:
    def test_fits_disk(self) -> None:
        # 100GB windows + 4GB swap + overhead fits on 500GB disk
        layout = DualBootLayout(
            windows_size_gb=100,
            swap_size_gb=4,
            disk_size_bytes=_500GB,
        )
        assert layout.total_required_mb < 500 * 1024

    def test_too_large_raises(self) -> None:
        small_disk = 50 * 1024 * 1024 * 1024  # 50 GB
        with pytest.raises(LayoutTooLargeError):
            DualBootLayout(
                windows_size_gb=100,
                swap_size_gb=4,
                disk_size_bytes=small_disk,
            )

    def test_zero_disk_size_skips_check(self) -> None:
        # disk_size_bytes=0 means "skip disk-size validation"
        layout = DualBootLayout(windows_size_gb=9999, swap_size_gb=0, disk_size_bytes=0)
        assert layout.windows_size_gb == 9999


class TestTotalRequiredMb:
    def test_calculation(self) -> None:
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=4)
        # overhead(512+16) + win(100*1024) + swap(4*1024) + 1 = 106993
        expected = 512 + 16 + 100 * 1024 + 4 * 1024 + 1
        assert layout.total_required_mb == expected

    def test_no_swap(self) -> None:
        layout = DualBootLayout(windows_size_gb=100, swap_size_gb=0)
        expected = 512 + 16 + 100 * 1024 + 0 + 1
        assert layout.total_required_mb == expected
