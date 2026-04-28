"""Sanitiser for fixture data — normalise serials, MACs, machine IDs."""

from __future__ import annotations

import re
from typing import Any


def sanitise_serial(serial: str) -> str:
    """Replace any alphanumeric serial with TESTSERIAL000."""
    if serial and len(serial) > 3:
        return "TESTSERIAL000"
    return serial


def sanitise_mac(mac: str) -> str:
    """Replace any MAC address with 00:11:22:33:44:55."""
    if re.match(r"^([0-9A-Fa-f]{2}:){5}([0-9A-Fa-f]{2})$", mac):
        return "00:11:22:33:44:55"
    return mac


def sanitise_machine_id(uuid: str) -> str:
    """Replace any UUID with 00000000-0000-0000-0000-000000000000."""
    if re.match(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        uuid,
        re.IGNORECASE,
    ):
        return "00000000-0000-0000-0000-000000000000"
    return uuid


def sanitise_json_fixture(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively sanitise JSON fixture data."""
    result = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = sanitise_json_fixture(value)
        elif isinstance(value, list):
            result[key] = [
                sanitise_json_fixture(item) if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str):
            # Try to sanitise by key name heuristics
            if "serial" in key.lower():
                result[key] = sanitise_serial(value)
            elif "mac" in key.lower() or key.lower() == "hwaddr":
                result[key] = sanitise_mac(value)
            elif "uuid" in key.lower() or "machine" in key.lower():
                result[key] = sanitise_machine_id(value)
            else:
                result[key] = value
        else:
            result[key] = value
    return result
