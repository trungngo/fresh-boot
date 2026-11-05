"""File writes that honour --dry-run (spec §5.5). Reads need no wrapper."""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from .options import state
from .output import out


def _dry(action: str) -> bool:
    if state.options.dry_run:
        out.would(action)
        return True
    return False


def mkdir(path, mode: int | None = None) -> bool:
    """Create ``path`` and its parents; True when it did not exist."""
    p = Path(path)
    if p.is_dir():
        return False
    if _dry("mkdir %s" % p):
        return True
    p.mkdir(parents=True, exist_ok=True)
    if mode is not None:
        os.chmod(p, mode)
    return True


def write_text(path, text: str, mode: int | None = None) -> None:
    """Atomic write: a temporary file in the same directory, then ``os.replace``."""
    p = Path(path)
    if _dry("write %s" % p):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="." + p.name + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        elif p.exists():
            try:
                os.chmod(tmp, stat.S_IMODE(p.stat().st_mode))
            except OSError:
                pass
        else:
            um = os.umask(0)
            os.umask(um)
            os.chmod(tmp, 0o666 & ~um)
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_text(path, text: str) -> None:
    p = Path(path)
    if _dry("append to %s" % p):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="") as f:
        f.write(text)


def remove(path) -> bool:
    """Remove a file or link; True when something was removed. A missing path is fine."""
    p = Path(path)
    if not p.exists() and not p.is_symlink():
        return False
    if _dry("remove %s" % p):
        return True
    p.unlink()
    return True


def rmtree(path) -> bool:
    """Remove a directory tree (read-only files included, as git leaves on Windows)."""
    p = Path(path)
    if not p.exists():
        return False
    if _dry("remove %s" % p):
        return True

    def retry(func, name, exc):
        try:
            os.chmod(name, stat.S_IWRITE)
            func(name)
        except OSError:
            raise exc

    if sys.version_info >= (3, 12):
        shutil.rmtree(p, onexc=retry)
    else:  # onerror is deprecated from 3.12 on
        shutil.rmtree(p, onerror=lambda func, name, info: retry(func, name, info[1]))
    return True


def replace_line(path, match_prefix: str, line: str) -> bool:
    """Replace the last line starting with ``match_prefix`` by ``line`` (appending it when
    there is none); True when the file changed."""
    p = Path(path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    lines = text.splitlines()
    idx = None
    for i, cur in enumerate(lines):
        if cur.startswith(match_prefix):
            idx = i
    if idx is not None:
        if lines[idx] == line:
            return False
        lines[idx] = line
    else:
        lines.append(line)
    write_text(p, "\n".join(lines) + "\n")
    return True
