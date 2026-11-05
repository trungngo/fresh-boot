"""Terminal checks, in one place, so tests can pretend to be on a TTY (``tn(..., tty=True)``)."""

from __future__ import annotations

import os
import sys

# Set by tn.testing: {"stdin": bool, "stdout": bool, "stderr": bool}.
_override: dict | None = None


def is_tty(stream: str = "stdin") -> bool:
    """Whether ``stream`` ("stdin", "stdout" or "stderr") is a terminal."""
    if _override is not None:
        return bool(_override.get(stream, False))
    f = getattr(sys, stream, None)
    try:
        return bool(f is not None and f.isatty())
    except (ValueError, OSError):
        return False


def color_allowed(no_color_flag: bool = False) -> bool:
    """Colour is off with --no-color, a non-empty NO_COLOR, or TERM=dumb (spec §2.4)."""
    if no_color_flag or os.environ.get("NO_COLOR"):
        return False
    return os.environ.get("TERM") != "dumb"


def use_color(stream: str, options) -> bool:
    """Colour on ``stream``: allowed by the options and the stream is a TTY; never in JSON."""
    if options is None or not options.color or options.json:
        return False
    return is_tty(stream)
