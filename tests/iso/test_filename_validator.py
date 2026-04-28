"""Tests for iso.catalog.validate_filename — allowlist and rejection cases."""

from __future__ import annotations

import pytest

from sysinstall.iso.catalog import validate_filename


class TestValidFilenames:
    @pytest.mark.parametrize("name", [
        "ubuntu-24.04.iso",
        "WIN_11_22H2.ISO",
        "arch-linux-2026.01.01-x86_64.iso",
        "debian 12.5.0 amd64.iso",
        "a.iso",
        "UPPERCASE.ISO",
        "mixed-Case_123.iso",
        "file.with.dots.iso",
    ])
    def test_valid(self, name: str) -> None:
        validate_filename(name)  # must not raise


class TestRejectedFilenames:
    @pytest.mark.parametrize("name,reason", [
        ("../etc/passwd.iso", "dotdot traversal"),
        ("/abs.iso", "absolute path via slash"),
        ("name/slash.iso", "embedded forward slash"),
        ("name\\back.iso", "embedded backslash"),
        ("..\\windows\\system32.iso", "dotdot with backslash"),
        ("./relative.iso", "dotdot not present but slash is"),
        ("no-extension", "missing .iso extension"),
        ("file.img", "wrong extension"),
        ("", "empty string"),
    ])
    def test_rejected(self, name: str, reason: str) -> None:
        with pytest.raises(ValueError, match=r""):
            validate_filename(name)
