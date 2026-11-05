"""Pickers, confirmations and questions (spec §2.5)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Any, Callable, Sequence

from . import proc, term
from .errors import Cancelled, UsageError
from .options import state
from .output import out


def can_prompt() -> bool:
    """Only when stdin and stderr are both TTYs and --json is not given."""
    return (not state.options.json) and term.is_tty("stdin") and term.is_tty("stderr")


def _readline(question: str) -> str | None:
    sys.stderr.write(question)
    sys.stderr.flush()
    try:
        line = sys.stdin.readline()
    except (OSError, ValueError):
        return None
    if line == "":
        return None
    return line.rstrip("\r\n")


def _fzf(labels: list[str], prompt: str) -> int | None:
    fzf = proc.which("fzf")
    feed = "".join("%d\t%s\n" % (i, lab.replace("\n", " ")) for i, lab in enumerate(labels))
    try:
        p = subprocess.run([fzf, "--height=40%", "--reverse", "--prompt", prompt + "> ",
                            "--with-nth=2..", "--delimiter=\t"],
                           input=feed, stdout=subprocess.PIPE, text=True, encoding="utf-8")
    except OSError:
        return -1
    if p.returncode != 0:
        return None
    first = (p.stdout or "").split("\t", 1)[0].strip()
    try:
        idx = int(first)
    except ValueError:
        return None
    return idx if 0 <= idx < len(labels) else None


def first_column(text: str) -> str:
    """A label's first column: the text before the first run of two spaces (or a tab).

    ``"claude-acme-shop-00  Acme Shop #U1-00"`` -> ``"claude-acme-shop-00"``. It is what
    ``pick()`` puts in ``choices`` when no ``value`` is given, so a label written as
    ``"<value>  <description>"`` gives back a value the command accepts as its argument."""
    s = str(text).strip()
    cut = len(s)
    for sep in ("  ", "\t"):
        i = s.find(sep)
        if i >= 0:
            cut = min(cut, i)
    return s[:cut].rstrip()


def pick(items: Sequence[Any], *, label: Callable[[Any], str] = str,
         value: Callable[[Any], str] | None = None, prompt: str = "pick",
         what: str = "which one?") -> Any:
    """One of ``items``: the only one without asking, else fzf or a numbered list on a TTY;
    without one, ``UsageError(what, choices=values)`` (exit 2).

    ``label`` is what a person sees (fzf, the numbered list, ``using <label>``). ``value`` is
    what goes in ``choices`` without a TTY: a string the same command accepts back as its
    argument, so a caller such as a Claude skill can choose and call again. It defaults to the
    label's first column (``first_column``)."""
    items = list(items)
    if not items:
        raise UsageError("%s (nothing to choose from)" % what.rstrip("?"))
    labels = [str(label(i)) for i in items]
    if len(items) == 1:
        out.info("using %s" % labels[0])
        return items[0]
    if not can_prompt():
        if value is None:
            values = [first_column(lab) for lab in labels]
        else:
            values = [str(value(i)) for i in items]
        raise UsageError(what, choices=list(dict.fromkeys(values)))
    if os.environ.get("TN_PICKER") != "list" and proc.which("fzf"):
        idx = _fzf(labels, prompt)
        if idx is None:
            raise Cancelled()
        if idx >= 0:
            return items[idx]
    width = len(str(len(labels)))
    for n, lab in enumerate(labels, 1):
        sys.stderr.write("  %s) %s\n" % (str(n).rjust(width + 1), lab))
    for _ in range(3):
        ans = _readline("%s [1-%d, or blank to cancel]: " % (prompt, len(labels)))
        if ans is None or ans.strip() == "":
            raise Cancelled()
        try:
            n = int(ans.strip())
        except ValueError:
            n = 0
        if 1 <= n <= len(labels):
            return items[n - 1]
        sys.stderr.write("  not a number from 1 to %d\n" % len(labels))
    raise Cancelled()


def confirm(question: str, default: bool = False) -> bool:
    """True with --yes; asks on a TTY; otherwise exit 2 ``<question> — pass --yes to confirm``."""
    if state.options.yes:
        return True
    if not can_prompt():
        raise UsageError("%s — pass --yes to confirm" % question)
    ans = _readline("%s [%s] " % (question, "Y/n" if default else "y/N"))
    if ans is None:
        raise Cancelled()
    a = ans.strip().lower()
    if a == "":
        return default
    return a in ("y", "yes")


def ask(question: str, default: str | None = None) -> str:
    """A line of text; the default (pre-filled in brackets) without a TTY or on a blank answer.
    Without a TTY and without a default, exit 2."""
    if not can_prompt():
        if default is None:
            raise UsageError(question)
        return default
    ans = _readline("%s%s: " % (question, " [%s]" % default if default else ""))
    if ans is None:
        raise Cancelled()
    ans = ans.strip()
    if ans:
        return ans
    if default is None:
        raise Cancelled()
    return default
