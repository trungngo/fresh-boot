"""Time, in one place, so tests can freeze it (``TnTestCase.freeze_time``).

Every age and expiry computation must go through :func:`now`.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

_frozen: float | None = None


def now() -> float:
    """Seconds since the epoch (frozen in tests)."""
    return _frozen if _frozen is not None else time.time()


def iso(ts: float | None) -> str | None:
    """ISO 8601 UTC with ``Z`` (``2026-09-30T08:15:00Z``), or None."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str | None) -> float | None:
    """The inverse of :func:`iso` (also accepts offsets); None for None or garbage."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def age_seconds(ts: float | None) -> int | None:
    """Whole seconds since ``ts`` (never negative), or None."""
    if ts is None:
        return None
    return max(0, int(now() - ts))


def fmt_age(seconds: float | None) -> str:
    """``45s``, ``12m``, ``3h``, ``2d``: the largest whole unit; ``-`` for None."""
    if seconds is None:
        return "-"
    s = max(0, int(seconds))
    if s < 60:
        return "%ds" % s
    if s < 3600:
        return "%dm" % (s // 60)
    if s < 86400:
        return "%dh" % (s // 3600)
    return "%dd" % (s // 86400)


def fmt_duration(seconds: float | None) -> str:
    """``1h12m``, ``45s``, ``2d3h``: two units at most; ``-`` for None."""
    if seconds is None:
        return "-"
    s = max(0, int(seconds))
    parts = []
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if s >= size or (unit == "s" and not parts):
            parts.append("%d%s" % (s // size, unit))
            s %= size
        if len(parts) == 2:
            break
    return "".join(parts)
