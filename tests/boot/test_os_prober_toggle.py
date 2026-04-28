"""Tests for enable_os_prober text transform (pure function).

Three cases:
  1. Line present set to true  -> flipped to false
  2. Line missing              -> appended
  3. Line commented out        -> uncommented and set to false
"""

from __future__ import annotations

from pathlib import Path

from sysinstall.boot.grub import toggle_os_prober_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_existing_true_flipped_to_false() -> None:
    content = (FIXTURES / "grub-default-with-os-prober.txt").read_text()
    result = toggle_os_prober_text(content)
    assert "GRUB_DISABLE_OS_PROBER=false" in result
    assert "GRUB_DISABLE_OS_PROBER=true" not in result


def test_missing_line_appended() -> None:
    content = (FIXTURES / "grub-default-no-os-prober.txt").read_text()
    assert "GRUB_DISABLE_OS_PROBER" not in content
    result = toggle_os_prober_text(content)
    assert "GRUB_DISABLE_OS_PROBER=false" in result


def test_commented_line_uncommented() -> None:
    content = "GRUB_DEFAULT=0\n#GRUB_DISABLE_OS_PROBER=true\n"
    result = toggle_os_prober_text(content)
    assert "GRUB_DISABLE_OS_PROBER=false" in result
    assert "#GRUB_DISABLE_OS_PROBER" not in result


def test_already_false_remains_false() -> None:
    content = "GRUB_DEFAULT=0\nGRUB_DISABLE_OS_PROBER=false\n"
    result = toggle_os_prober_text(content)
    assert result.count("GRUB_DISABLE_OS_PROBER=false") == 1


def test_commented_with_spaces() -> None:
    content = "GRUB_DEFAULT=0\n# GRUB_DISABLE_OS_PROBER=true\n"
    result = toggle_os_prober_text(content)
    assert "GRUB_DISABLE_OS_PROBER=false" in result


def test_idempotent_on_already_correct() -> None:
    content = "GRUB_DEFAULT=0\nGRUB_DISABLE_OS_PROBER=false\n"
    result1 = toggle_os_prober_text(content)
    result2 = toggle_os_prober_text(result1)
    assert result1 == result2
