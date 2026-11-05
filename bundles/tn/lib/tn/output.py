"""Output rules (spec §2.4, §5.6): results on stdout, everything else on stderr."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path, PurePath
from typing import Any, Callable, Iterable

from . import clock, term
from .options import state

_COLORS = {"red": "31", "green": "32", "yellow": "33", "blue": "34", "dim": "2", "bold": "1"}


def paint(text: str, color: str, stream: str = "stdout") -> str:
    """``text`` in ``color`` when that stream may be coloured (§2.4), else unchanged."""
    if not term.use_color(stream, state.options):
        return text
    return "\033[%sm%s\033[0m" % (_COLORS.get(color, "0"), text)


def _json_default(o: Any) -> Any:
    if isinstance(o, PurePath):
        return str(o)
    if dataclasses.is_dataclass(o) and not isinstance(o, type):
        return dataclasses.asdict(o)
    if isinstance(o, (set, frozenset, tuple)):
        return list(o)
    to_json = getattr(o, "to_json", None)
    if callable(to_json):
        return to_json()
    raise TypeError("not JSON serialisable: %r" % (o,))


def dumps(obj: Any, *, indent: int | None = 2) -> str:
    """JSON the way tn prints it: Paths as native strings, dataclasses as objects."""
    return json.dumps(obj, indent=indent, default=_json_default, ensure_ascii=False)


def home_short(path: str | os.PathLike | None) -> str:
    """``/Users/me/myprojects/x`` -> ``~/myprojects/x`` (text output only)."""
    if path is None:
        return "-"
    p = str(path)
    home = str(Path.home())
    if p == home:
        return "~"
    if home and p.startswith(home.rstrip(os.sep) + os.sep):
        return "~" + os.sep + p[len(home.rstrip(os.sep)) + 1:]
    return p


def fmt_value(v: Any) -> str:
    """The default text form of a value: ``-`` for None/empty, yes/no, comma lists."""
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (list, tuple)):
        return ",".join(fmt_value(x) for x in v) if v else "-"
    if isinstance(v, dict):
        return dumps(v, indent=None)
    s = str(v)
    return s if s != "" else "-"


def table(rows: list[list[str]], header: list[str] | None = None) -> str:
    """Left-aligned columns separated by two spaces; no trailing blanks."""
    allrows = ([header] if header else []) + rows
    if not allrows:
        return ""
    n = max(len(r) for r in allrows)
    widths = [max((len(r[i]) if i < len(r) else 0) for r in allrows) for i in range(n)]
    lines = []
    for r in allrows:
        cells = [(r[i] if i < len(r) else "") for i in range(n)]
        line = "  ".join(c.ljust(widths[i]) if i < n - 1 else c for i, c in enumerate(cells))
        lines.append(line.rstrip())
    return "\n".join(lines)


class _Out:
    """``tn.out``: the only way plugins should print."""

    # -- stderr ---------------------------------------------------------------------------
    def _err(self, text: str) -> None:
        sys.stderr.write(text + "\n")
        sys.stderr.flush()

    def info(self, msg: str) -> None:
        """Progress on stderr; hidden by -q."""
        if not state.options.quiet:
            self._err(msg)

    def warn(self, msg: str) -> None:
        """``warning: ...`` on stderr; hidden by -q."""
        if not state.options.quiet:
            self._err(paint("warning:", "yellow", "stderr") + " " + msg)

    def hint(self, msg: str) -> None:
        """``  hint: ...`` on stderr; hidden by -q."""
        if not state.options.quiet:
            self._err("  hint: " + msg)

    def debug(self, msg: str) -> None:
        """stderr, only with -v."""
        if state.options.verbose >= 1:
            self._err(paint(msg, "dim", "stderr"))

    def would(self, action: str) -> None:
        """A dry-run line: ``would: <action>`` on stderr (never hidden: it is the result)."""
        self._err("would: " + action)

    def error(self, msg: str) -> None:
        """An error line on stderr, never hidden (use exceptions for command failures)."""
        self._err(msg)

    # -- stdout ---------------------------------------------------------------------------
    def line(self, text: Any = "") -> None:
        """One result line on stdout."""
        sys.stdout.write("%s\n" % (text,))
        sys.stdout.flush()

    def json(self, obj: Any) -> None:
        """``obj`` as indented JSON on stdout."""
        self.line(dumps(obj))

    def records(self, rows: list[dict], columns: Iterable[tuple], *, empty: str) -> None:
        """How ``ls`` prints: a table, or the rows as a JSON array; ``empty`` on stderr."""
        rows = list(rows)
        if state.options.json:
            self.json(rows)
            return
        if not rows:
            if not state.options.quiet:
                self._err(empty)
            return
        cols = [tuple(c) for c in columns]
        header = [c[1] for c in cols]
        body = []
        for r in rows:
            cells = []
            for c in cols:
                fmt: Callable[[Any], str] = c[2] if len(c) > 2 and c[2] else fmt_value
                v = r.get(c[0])
                cells.append(fmt_value(v) if v is None else str(fmt(v)))
            body.append(cells)
        self.line(table(body, header))

    def record(self, obj: dict, fields: Iterable[tuple]) -> None:
        """How ``show`` prints: ``Label: value`` lines, or the object as JSON."""
        if state.options.json:
            self.json(obj)
            return
        fields = [tuple(f) for f in fields]
        width = max((len(f[1]) for f in fields), default=0) + 1
        for f in fields:
            fmt = f[2] if len(f) > 2 and f[2] else fmt_value
            v = obj.get(f[0])
            self.line(("%s:" % f[1]).ljust(width) + " " + (fmt_value(v) if v is None else str(fmt(v))))

    def result(self, obj: Any, text: Callable[[Any], Any] | str | None = None) -> None:
        """How actions print: --json dumps ``obj`` (a dict gets ``"dry_run": true`` under
        --dry-run); otherwise ``text(obj)`` (or ``text``) is printed, if given."""
        if state.options.json:
            if state.options.dry_run and isinstance(obj, dict) and "dry_run" not in obj:
                obj = dict(obj, dry_run=True)
            self.json(obj)
            return
        if text is None:
            return
        value = text(obj) if callable(text) else text
        if value is None:
            return
        if isinstance(value, (list, tuple)):
            for v in value:
                self.line(v)
        else:
            self.line(value)


out = _Out()


def age_text(started: float | None) -> str:
    """``3h`` for an epoch time, via tn.clock."""
    return clock.fmt_age(clock.age_seconds(started))
