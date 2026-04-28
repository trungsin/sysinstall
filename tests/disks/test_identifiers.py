"""Unit tests for stable disk ID derivation — pure function, no I/O."""

from __future__ import annotations

import pytest

from sysinstall.disks.identifiers import _short_hash, make_stable_id


class TestShortHash:
    def test_returns_16_hex_chars(self) -> None:
        result = _short_hash("hello")
        assert len(result) == 16
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self) -> None:
        assert _short_hash("test") == _short_hash("test")

    def test_different_inputs_different_output(self) -> None:
        assert _short_hash("abc") != _short_hash("def")


class TestMakeStableId:
    # --- With serial ---

    def test_with_serial_uses_bus_prefix(self) -> None:
        id_ = make_stable_id("nvme", "SN123", "Model X", 500_000_000_000)
        assert id_.startswith("nvme:")

    def test_with_serial_no_unstable_prefix(self) -> None:
        id_ = make_stable_id("sata", "SN999", "Model Y", 1_000_000_000)
        assert "unstable" not in id_

    def test_with_serial_deterministic(self) -> None:
        a = make_stable_id("usb", "USB-SN", "Kingston", 32_000_000_000)
        b = make_stable_id("usb", "USB-SN", "Kingston", 32_000_000_000)
        assert a == b

    def test_different_serials_different_ids(self) -> None:
        a = make_stable_id("sata", "SN-AAA", "Seagate", 1_000_000_000_000)
        b = make_stable_id("sata", "SN-BBB", "Seagate", 1_000_000_000_000)
        assert a != b

    def test_different_bus_different_ids(self) -> None:
        a = make_stable_id("usb", "SAME-SN", "Model", 1_000_000)
        b = make_stable_id("sata", "SAME-SN", "Model", 1_000_000)
        assert a != b

    def test_serial_whitespace_stripped(self) -> None:
        a = make_stable_id("nvme", "  SN123  ", "Model", 500_000_000_000)
        b = make_stable_id("nvme", "SN123", "Model", 500_000_000_000)
        assert a == b

    # --- Without serial (fallback) ---

    def test_none_serial_uses_unstable_prefix(self) -> None:
        id_ = make_stable_id("sata", None, "WD Blue", 1_000_000_000_000)
        assert id_.startswith("unstable:")

    def test_empty_serial_uses_unstable_prefix(self) -> None:
        id_ = make_stable_id("sata", "", "WD Blue", 1_000_000_000_000)
        assert id_.startswith("unstable:")

    def test_whitespace_serial_uses_unstable_prefix(self) -> None:
        id_ = make_stable_id("sata", "   ", "WD Blue", 1_000_000_000_000)
        assert id_.startswith("unstable:")

    def test_unstable_deterministic_same_order(self) -> None:
        a = make_stable_id("unknown", None, "Generic", 250_000_000_000, order=0)
        b = make_stable_id("unknown", None, "Generic", 250_000_000_000, order=0)
        assert a == b

    def test_unstable_different_order_different_id(self) -> None:
        """order is the only differentiator when model+size are identical."""
        a = make_stable_id("unknown", None, "Generic", 250_000_000_000, order=0)
        b = make_stable_id("unknown", None, "Generic", 250_000_000_000, order=1)
        assert a != b

    def test_unstable_different_size_different_id(self) -> None:
        a = make_stable_id("sata", None, "WD", 500_000_000_000, order=0)
        b = make_stable_id("sata", None, "WD", 1_000_000_000_000, order=0)
        assert a != b

    def test_unstable_different_model_different_id(self) -> None:
        a = make_stable_id("sata", None, "WD Blue", 500_000_000_000, order=0)
        b = make_stable_id("sata", None, "Seagate", 500_000_000_000, order=0)
        assert a != b

    # --- Format validation ---

    def test_id_contains_only_safe_chars(self) -> None:
        import re
        for serial, model in [("SN1", "Model A"), (None, "Model B")]:
            id_ = make_stable_id("nvme", serial, model, 1_000_000_000)
            assert re.match(r"^[a-zA-Z0-9:.\-]+$", id_), f"Unsafe chars in ID: {id_!r}"

    @pytest.mark.parametrize("bus", ["usb", "sata", "nvme", "scsi", "unknown"])
    def test_all_bus_types_produce_valid_id(self, bus: str) -> None:
        id_ = make_stable_id(bus, "SN-TEST", "Model", 1_000_000_000)
        assert id_.startswith(f"{bus}:")
