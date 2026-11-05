"""tn plugin for the python bundle: one doctor check, uv installed (docs/tn.md §7.7).

No commands: the old ``tn dj`` (Django manage.py) and ``tn py serve`` groups were removed as
outdated. A Plugin always owns at least one group, so this one keeps the default (its own name,
``python``), which only labels the doctor row.
"""

from __future__ import annotations

from tn import Context, Plugin, Problem, capture

plugin = Plugin("python", help="Python checks (uv)")


@plugin.check
def uv_installed(ctx: Context):
    """uv installed"""
    r = capture(["uv", "--version"], timeout=10)
    if r.returncode == 127:
        raise Problem("uv is not installed", fix="dot apply python", level="warn")
    return (r.stdout or "").strip() or None
