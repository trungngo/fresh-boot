"""Just enough TOML writing for tn: a serialiser for ``config show`` / ``config get``, value
parsing for ``config set``, and the line-level key edit of ``config set`` (spec §6.5).

The standard library reads TOML (``tomllib``) but cannot write it; nothing here tries to be a
general TOML writer.
"""

from __future__ import annotations

import json
import re
import tomllib
from datetime import date, datetime, time
from typing import Any

BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def key_text(k: str) -> str:
    return k if BARE_KEY.match(k) else json.dumps(k, ensure_ascii=False)


def value_text(v: Any) -> str:
    """One TOML value (inline form for tables)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(value_text(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join("%s = %s" % (key_text(k), value_text(x)) for k, x in v.items()) + "}"
    if v is None:
        raise ValueError("TOML has no null")
    return json.dumps(str(v), ensure_ascii=False)


def dumps(data: dict, _prefix: tuple = ()) -> str:
    """A dict as TOML: scalars first, then one ``[table]`` per nested dict."""
    lines: list[str] = []
    tables = []
    for k, v in data.items():
        if isinstance(v, dict):
            tables.append((k, v))
        elif v is not None:
            lines.append("%s = %s" % (key_text(k), value_text(v)))
    for k, v in tables:
        name = _prefix + (k,)
        scalars = any(not isinstance(x, dict) for x in v.values()) or not v
        body = dumps(v, name)
        if scalars:
            if lines:
                lines.append("")
            lines.append("[%s]" % ".".join(key_text(p) for p in name))
        if body:
            if not scalars and lines:
                lines.append("")
            lines.append(body)
    return "\n".join(lines)


def parse_value(text: str) -> Any:
    """``config set`` values are TOML: ``3000``, ``true``, ``["a", "b"]``; a bare word is a string."""
    try:
        return tomllib.loads("v = " + text)["v"]
    except tomllib.TOMLDecodeError:
        return text


def split_key(dotted: str) -> list[str]:
    parts = dotted.split(".")
    if not dotted or any(not BARE_KEY.match(p) for p in parts):
        raise ValueError("invalid key %r (dotted bare keys: letters, digits, _ and -)" % dotted)
    return parts


_HEADER = re.compile(r"^\s*\[\[?\s*([^\]]*?)\s*\]\]?\s*(#.*)?$")


def _norm_table(name: str) -> str:
    return ".".join(p.strip().strip('"').strip("'") for p in name.split("."))


def set_key(text: str, dotted: str, value: Any) -> str:
    """``text`` with ``dotted`` set to ``value`` by editing one line (spec §6.5).

    The ``key = ...`` line inside the right ``[table]`` is replaced; without one, the key is
    appended at the end of that table, and the ``[table]`` header is added at the end of the
    file when missing. Everything else is kept as it is.
    """
    parts = split_key(dotted)
    table, key = ".".join(parts[:-1]), parts[-1]
    new_line = "%s = %s" % (key_text(key), value_text(value))
    lines = text.splitlines()
    key_re = re.compile(r"^(\s*)(%s|\"%s\"|'%s')\s*=" % ((re.escape(key),) * 3))

    current = ""
    start = 0 if table == "" else None      # first line of the table's body
    end = None                              # index of the next header after it
    for i, line in enumerate(lines):
        m = _HEADER.match(line)
        if m and not line.lstrip().startswith("#"):
            if start is not None and end is None and current == table:
                end = i
            current = _norm_table(m.group(1))
            if current == table and start is None:
                start = i + 1
            continue
        if current == table and start is not None and end is None:
            km = key_re.match(line)
            if km:
                lines[i] = km.group(1) + new_line
                return "\n".join(lines) + "\n"
    if start is None:
        body = "\n".join(lines).rstrip("\n")
        sep = "\n\n" if body else ""
        return body + sep + "[%s]\n%s\n" % (table, new_line)
    if end is None:
        end = len(lines)
    ins = end
    while ins > start and lines[ins - 1].strip() == "":
        ins -= 1
    lines.insert(ins, new_line)
    return "\n".join(lines) + "\n"
