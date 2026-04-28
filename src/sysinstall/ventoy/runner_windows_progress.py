"""Pure file-poll progress parser for Ventoy2Disk.exe on Windows.

No subprocess, no threading — takes two reader callables (for cli_percent.txt
and cli_done.txt) and a sleep callable. This makes the poller fully
unit-testable without real files or real time.

Poller contract:
  - Poll cli_percent.txt every 250ms for progress updates.
  - Poll cli_done.txt to detect completion.
  - cli_done.txt contains "0" (success) or "1" (failure).
  - Stop when cli_done.txt appears OR timeout exceeded.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

# How often to poll (seconds). Tests can override via the sleep callable.
_POLL_INTERVAL = 0.25
_TIMEOUT_SECONDS = 600.0


def poll_progress(
    read_percent: Callable[[], str | None],
    read_done: Callable[[], str | None],
    *,
    on_progress: Callable[[int], None] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    poll_interval: float = _POLL_INTERVAL,
    timeout: float = _TIMEOUT_SECONDS,
) -> int:
    """Poll Ventoy Windows progress files until done or timeout.

    Args:
        read_percent: Returns content of cli_percent.txt, or None if absent.
        read_done: Returns content of cli_done.txt, or None if absent.
        on_progress: Called with int 0-100 on each percent change.
        sleep_fn: Replaces time.sleep (injectable for tests).
        poll_interval: Seconds between polls (default 0.25).
        timeout: Maximum seconds to poll before giving up.

    Returns:
        0 on success, 1 on Ventoy-reported failure, 2 on timeout.
    """
    import time as _time

    _sleep = sleep_fn if sleep_fn is not None else _time.sleep
    elapsed = 0.0
    last_pct: int | None = None

    while elapsed < timeout:
        # Check completion first.
        done_content = read_done()
        if done_content is not None:
            result = done_content.strip()
            log.debug("cli_done.txt content: %r", result)
            return 0 if result == "0" else 1

        # Update progress.
        pct_content = read_percent()
        if pct_content is not None:
            try:
                pct = int(pct_content.strip())
                pct = min(max(pct, 0), 100)
                if pct != last_pct:
                    last_pct = pct
                    log.debug("Ventoy progress: %d%%", pct)
                    if on_progress is not None:
                        on_progress(pct)
            except ValueError:
                log.warning("Unexpected cli_percent.txt content: %r", pct_content)

        _sleep(poll_interval)
        elapsed += poll_interval

    log.error("Ventoy Windows install timed out after %.0fs", timeout)
    return 2
