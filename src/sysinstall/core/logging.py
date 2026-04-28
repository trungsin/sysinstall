"""Rich-based logger that respects --verbose / --quiet global options."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

# Module-level console instances; quiet mode writes to stderr only for errors.
_console = Console(stderr=False)
_err_console = Console(stderr=True)

_LOG_FORMAT = "%(message)s"
_DATE_FORMAT = "[%X]"


def get_logger(name: str = "sysinstall") -> logging.Logger:
    """Return a named logger. Call configure_logging() first to set level."""
    return logging.getLogger(name)


def configure_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """
    Set up Rich logging handler for the sysinstall root logger.

    Levels:
      verbose=True  -> DEBUG
      quiet=True    -> ERROR  (suppresses info/warning)
      default       -> INFO
    """
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        level = logging.INFO

    handler = RichHandler(
        console=_err_console,
        show_time=verbose,
        show_path=verbose,
        markup=True,
        rich_tracebacks=True,
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger("sysinstall")
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    root.propagate = False
