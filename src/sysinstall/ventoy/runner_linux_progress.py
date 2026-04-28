"""Pure progress parser for Ventoy2Disk.sh stdout lines.

No subprocess, no I/O — takes an iterator of text lines and calls
on_progress(pct: int) for each percentage found. This makes the parser
fully unit-testable without spawning processes.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator

# Matches "10%", "  50 %", "Done: 100%" etc.
_PCT_RE = re.compile(r"(\d{1,3})\s*%")


def parse_progress(
    lines: Iterator[str],
    on_progress: Callable[[int], None] | None = None,
) -> list[int]:
    """Consume *lines*, fire *on_progress* for every percentage found.

    Args:
        lines: Iterator of stdout lines from Ventoy2Disk.sh.
        on_progress: Optional callback receiving an int 0-100.

    Returns:
        List of all percentage values found, in order (useful for tests).
    """
    found: list[int] = []
    for line in lines:
        for match in _PCT_RE.finditer(line):
            pct = int(match.group(1))
            pct = min(max(pct, 0), 100)  # clamp to valid range
            found.append(pct)
            if on_progress is not None:
                on_progress(pct)
    return found
