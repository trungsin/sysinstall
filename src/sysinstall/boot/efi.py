"""EFI boot entry management via efibootmgr.

parse_efibootmgr is a pure function — tested with fixture text, no subprocess.
list_entries and set_boot_order call subprocess (Linux only).
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import TYPE_CHECKING

from sysinstall.boot.types import EfiEntry
from sysinstall.safety.audit import append_audit

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_EFIBOOTMGR_TIMEOUT = 30

# Matches: Boot0001* ubuntu   HD(...)...
# Group 1: 4-digit hex num
# Group 2: active flag (* or space)
# Group 3: label
# Group 4: path (optional, rest of line)
_BOOT_ENTRY_RE = re.compile(
    r"^Boot([0-9A-Fa-f]{4})([* ])\s+(\S[^\t]*)(?:\t(.*))?$",
    re.MULTILINE,
)

# Matches: BootOrder: 0001,0002,...
_BOOT_ORDER_RE = re.compile(r"^BootOrder:\s*([0-9A-Fa-f,]+)$", re.MULTILINE)


def parse_efibootmgr(text: str) -> list[EfiEntry]:
    """Parse efibootmgr -v output into a list of EfiEntry objects.

    This is a pure function — takes raw text, returns structured data.
    Boot order positions are assigned from the BootOrder line if present.

    Args:
        text: Raw stdout from ``efibootmgr -v``.

    Returns:
        List of EfiEntry objects. Entries not in BootOrder have
        boot_order_position = -1.
    """
    # Parse BootOrder line first to assign positions.
    order_map: dict[str, int] = {}
    order_match = _BOOT_ORDER_RE.search(text)
    if order_match:
        for pos, num in enumerate(order_match.group(1).upper().split(",")):
            order_map[num.strip()] = pos

    entries: list[EfiEntry] = []
    for m in _BOOT_ENTRY_RE.finditer(text):
        num = m.group(1).upper()
        active = m.group(2) == "*"
        label = m.group(3).strip()
        path = (m.group(4) or "").strip()
        position = order_map.get(num, -1)
        entries.append(EfiEntry(
            num=num,
            label=label,
            path=path,
            active=active,
            boot_order_position=position,
        ))

    return entries


def list_entries() -> list[EfiEntry]:
    """Run efibootmgr -v and return parsed EFI entries.

    Returns:
        List of EfiEntry objects.

    Raises:
        RuntimeError: if efibootmgr fails or is not available.
    """
    result = subprocess.run(
        ["efibootmgr", "-v"],
        capture_output=True,
        timeout=_EFIBOOTMGR_TIMEOUT,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"efibootmgr -v failed: {stderr}")

    text = result.stdout.decode(errors="replace")
    return parse_efibootmgr(text)


def set_boot_order(entries: list[EfiEntry], *, dry_run: bool = False) -> None:
    """Set EFI boot order using efibootmgr -o.

    Entries are written in the order they appear in the list.

    Args:
        entries: Ordered list of EfiEntry. The boot order will be set
                 to match this ordering.
        dry_run: Log intent but do not execute.

    Raises:
        RuntimeError: if efibootmgr fails.
    """
    if not entries:
        log.warning("set_boot_order called with empty entries list — skipping")
        return

    order_str = ",".join(e.num for e in entries)
    args = ["efibootmgr", "-o", order_str]

    append_audit(
        "boot.repair.command",
        target="efi",
        outcome="dry_run" if dry_run else "started",
        args={"cmd": " ".join(args)},
    )

    if dry_run:
        log.info("[dry-run] would run: %s", " ".join(args))
        return

    result = subprocess.run(args, capture_output=True, timeout=_EFIBOOTMGR_TIMEOUT)
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"efibootmgr -o failed: {stderr}")

    append_audit("boot.repair.command", target="efi", outcome="success")
    log.info("EFI boot order set to: %s", order_str)


def find_ubuntu_first_order(entries: list[EfiEntry]) -> list[EfiEntry]:
    """Return entries reordered with Ubuntu entry first.

    Finds the first entry whose label contains 'ubuntu' (case-insensitive).
    All other entries follow in their original relative order.

    Args:
        entries: Current EFI entries.

    Returns:
        Reordered list with Ubuntu entry first, or original order if
        no Ubuntu entry is found.
    """
    ubuntu = [e for e in entries if "ubuntu" in e.label.lower()]
    others = [e for e in entries if "ubuntu" not in e.label.lower()]
    if not ubuntu:
        log.warning("No Ubuntu EFI entry found — boot order unchanged")
        return list(entries)
    return ubuntu + others
