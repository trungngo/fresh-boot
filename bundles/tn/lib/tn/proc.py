"""Running programs (spec §5.5). Every process tn starts goes through here, so dry-run and the
tests (fake executables, intercepted handoff) work."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn, Sequence

from .errors import Fail, Missing, UsageError
from .options import state
from .output import out

IS_WINDOWS = os.name == "nt"


def _argv(argv: Sequence) -> list[str]:
    if isinstance(argv, (str, bytes)):
        raise TypeError("argv must be a list, not a string (tn never uses a shell)")
    return [os.fspath(a) if isinstance(a, os.PathLike) else str(a) for a in argv]


def _join(argv: list[str]) -> str:
    if IS_WINDOWS:
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


_DEFAULT_PATHEXT = ".COM;.EXE;.BAT;.CMD"


def _search_path(prog: str, path: str, cwd: str, pathext: str) -> str | None:
    """Windows' program search without the current directory.

    ``shutil.which`` on Windows (3.11) looks in the current directory first and applies
    PATHEXT, so a ``git.cmd`` in a cloned repository would run instead of Git for Windows. Here
    only absolute PATH entries are searched, and an entry that is the current directory is
    skipped; ``.`` and relative entries are ignored."""
    exts = [e for e in (x.strip() for x in pathext.split(";")) if e]
    names = [prog] if os.path.splitext(prog)[1].lower() in {e.lower() for e in exts} \
        else [prog + e for e in exts]
    here = os.path.normcase(os.path.abspath(cwd))
    for d in path.split(os.pathsep):
        d = d.strip().strip('"')
        if not d or not os.path.isabs(d):
            continue
        if os.path.normcase(os.path.abspath(d)) == here:
            continue
        for n in names:
            f = os.path.join(d, n)
            if os.path.isfile(f):
                return f
    return None


def which(prog: str, path: str | None = None) -> str | None:
    """The absolute path of ``prog`` on ``path`` (default ``$PATH``), or None. On Windows the
    current directory is never searched (``_search_path``)."""
    if IS_WINDOWS:
        if os.path.dirname(prog):
            return prog if os.path.isfile(prog) else None
        return _search_path(prog, os.environ.get("PATH", "") if path is None else path,
                            os.getcwd(), os.environ.get("PATHEXT") or _DEFAULT_PATHEXT)
    return shutil.which(prog, path=path)


def _resolve(argv: list[str], env: dict | None) -> list[str]:
    """argv[0] through ``which`` (Windows needs it to find ``.cmd`` shims).

    On Windows a program not found on PATH raises ``FileNotFoundError`` instead of being
    passed on bare: CreateProcess would look for it in the current directory."""
    prog = argv[0]
    if os.path.dirname(prog):
        return argv
    path = (env or os.environ).get("PATH")
    found = which(prog, path=path)
    if found:
        return [found] + argv[1:]
    if IS_WINDOWS:
        raise FileNotFoundError(prog)
    return argv


def _no_window() -> int:
    """``CREATE_NO_WINDOW`` on Windows, else 0: a console program started by a process without
    a console (the detached ``tn tunnel --for`` watcher) would otherwise open a visible window."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0


def _has_console() -> bool:
    if not IS_WINDOWS:
        return True
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.GetConsoleWindow())  # type: ignore[attr-defined]
    except (ImportError, AttributeError, OSError):
        return True


def _env(env: dict | None) -> dict | None:
    if env is None:
        return None
    merged = dict(os.environ)
    for k, v in env.items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = str(v)
    return merged


def _describe(argv: list[str], cwd) -> str:
    text = "run " + _join(argv)
    if cwd is not None:
        text += " in " + str(cwd)
    return text


def _echo(argv: list[str], cwd) -> None:
    if state.options.verbose >= 2:
        out.error("+ " + _join(argv) + ("  (in %s)" % cwd if cwd is not None else ""))


def _has_fileno(stream) -> bool:
    try:
        stream.fileno()
        return True
    except (AttributeError, ValueError, OSError):
        return False


def need(prog: str, fix: str) -> str:
    """The absolute path of ``prog``, or ``Missing(f"{prog} is not installed", fix)``."""
    found = which(prog)
    if not found:
        raise Missing("%s is not installed" % prog, fix)
    return found


def run(argv: Sequence, *, cwd=None, env: dict | None = None, input: str | None = None,
        check: bool = True, quiet: bool = False) -> int:
    """Run a command that changes something. Output is inherited (``quiet=True`` sends the
    child's stdout to stderr). Dry-run prints ``would: run ...`` and returns 0."""
    argv = _argv(argv)
    if state.options.dry_run:
        out.would(_describe(argv, cwd))
        return 0
    _echo(argv, cwd)
    full_env = _env(env)
    target_out = sys.stderr if quiet else sys.stdout
    # A real stream (a terminal, a file) is inherited; a StringIO (tests) gets the output copied.
    pipe_out = not _has_fileno(target_out)
    pipe_err = not _has_fileno(sys.stderr)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (ValueError, OSError):
        pass
    extra: dict = {}
    if IS_WINDOWS and not _has_console():
        extra["creationflags"] = _no_window()
    try:
        proc = subprocess.run(
            _resolve(argv, full_env), cwd=None if cwd is None else str(cwd), env=full_env,
            input=input, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE if pipe_out else target_out,
            stderr=subprocess.PIPE if pipe_err else sys.stderr, **extra)
    except FileNotFoundError:
        raise Fail("%s is not installed (or not on PATH)" % argv[0])
    except PermissionError as e:
        raise Fail("cannot run %s: %s" % (argv[0], e))
    if pipe_out and proc.stdout:
        target_out.write(proc.stdout)
    if pipe_err and proc.stderr:
        sys.stderr.write(proc.stderr)
    if check and proc.returncode != 0:
        raise Fail("%s exited %d" % (argv[0], proc.returncode))
    return proc.returncode


def capture(argv: Sequence, *, cwd=None, env: dict | None = None, input: str | None = None,
            timeout: float | None = None, check: bool = False,
            fix: str | None = None) -> subprocess.CompletedProcess:
    """Run a read-only query (also under dry-run): text, UTF-8, stdout and stderr captured.

    A missing program gives ``returncode=127``, or ``Missing`` with ``check=True`` (``fix``
    defaults to ``install <prog>``). A timeout gives ``returncode=124`` (``Fail`` with check).
    ``check=True`` also raises ``Fail`` on a non-zero exit, with the program's stderr as hint.
    """
    argv = _argv(argv)
    _echo(argv, cwd)
    full_env = _env(env)
    try:
        proc = subprocess.run(
            _resolve(argv, full_env), cwd=None if cwd is None else str(cwd), env=full_env,
            input=input, text=True, encoding="utf-8", errors="replace",
            stdin=None if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
            **({"creationflags": _no_window()} if IS_WINDOWS else {}))
    except FileNotFoundError:
        if check:
            raise Missing("%s is not installed" % argv[0], fix or "install %s" % argv[0])
        return subprocess.CompletedProcess(argv, 127, "", "%s: not found\n" % argv[0])
    except PermissionError as e:
        if check:
            raise Fail("cannot run %s: %s" % (argv[0], e))
        return subprocess.CompletedProcess(argv, 126, "", "%s: %s\n" % (argv[0], e))
    except subprocess.TimeoutExpired:
        if check:
            raise Fail("%s timed out after %ss" % (argv[0], timeout))
        return subprocess.CompletedProcess(argv, 124, "", "%s: timed out\n" % argv[0])
    if check and proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        raise Fail("%s exited %d" % (argv[0], proc.returncode), hint=err[-1] if err else None)
    return proc


def git(repo_dir, *args, check: bool = False) -> subprocess.CompletedProcess:
    """``capture(["git", "-C", repo_dir, *args])``; ``Missing`` when git is absent."""
    need("git", "dot apply git")
    return capture(["git", "-C", str(repo_dir), *args], check=check)


def spawn_detached(argv: Sequence, *, cwd=None, log=None, env: dict | None = None) -> int:
    """Start a process that outlives the terminal; returns its pid (0 under dry-run)."""
    argv = _argv(argv)
    if state.options.dry_run:
        out.would(_describe(argv, cwd))
        return 0
    _echo(argv, cwd)
    full_env = _env(env)
    kwargs: dict = {}
    if IS_WINDOWS:
        kwargs["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0x8)
                                   | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
    else:
        kwargs["start_new_session"] = True
    if log is not None:
        Path(log).parent.mkdir(parents=True, exist_ok=True)
        sink = open(log, "ab")
    else:
        sink = open(os.devnull, "wb")
    try:
        p = subprocess.Popen(_resolve(argv, full_env), cwd=None if cwd is None else str(cwd),
                             env=full_env, stdin=subprocess.DEVNULL, stdout=sink,
                             stderr=subprocess.STDOUT, close_fds=True, **kwargs)
    except FileNotFoundError:
        raise Fail("%s is not installed (or not on PATH)" % argv[0])
    finally:
        sink.close()
    p.returncode = 0  # never waited for: it outlives tn (and silences Popen's ResourceWarning)
    return p.pid


def handoff(argv: Sequence, *, cwd=None, env: dict | None = None) -> NoReturn:
    """Give the terminal to another program and exit with its status (never returns).

    Rejects --json (exit 2). Dry-run prints ``would: run ...`` and exits 0.
    """
    argv = _argv(argv)
    if state.options.json:
        raise UsageError("--json is not supported here: this command hands the terminal to %s"
                         % os.path.basename(argv[0]))
    if state.options.dry_run:
        out.would(_describe(argv, cwd))
        raise SystemExit(0)
    _echo(argv, cwd)
    if state.handoff_hook is not None:
        raise SystemExit(state.handoff_hook(argv, cwd, env))
    full_env = _env(env)
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except (ValueError, OSError):
        pass
    if IS_WINDOWS:
        try:
            rc = subprocess.run(_resolve(argv, full_env), cwd=None if cwd is None else str(cwd),
                                env=full_env).returncode
        except FileNotFoundError:
            raise Fail("%s is not installed (or not on PATH)" % argv[0])
        except KeyboardInterrupt:
            rc = 130
        raise SystemExit(rc)
    resolved = _resolve(argv, full_env)
    if cwd is not None:
        os.chdir(str(cwd))
    try:
        os.execvpe(resolved[0], resolved, full_env if full_env is not None else dict(os.environ))
    except FileNotFoundError:
        raise Fail("%s is not installed (or not on PATH)" % argv[0])
    raise SystemExit(1)  # not reached


def pid_alive(pid: int | None) -> bool:
    """Whether ``pid`` names a live process (``PermissionError`` counts as alive)."""
    if not pid or pid <= 0:
        return False
    if IS_WINDOWS:
        return _win_pid_alive(pid, _Kernel32())
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False
    return True


# -- Windows liveness without a child process (a tasklist per check would flash a console
#    window from the detached watcher, and cost a process start every 0.2 s while stopping) ----

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


class _Kernel32:
    """The three kernel32 calls ``pid_alive`` needs (a seam: tests pass a fake)."""

    def __init__(self) -> None:
        import ctypes
        self._ct = ctypes
        self._k = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]

    def open(self, pid: int) -> tuple[int, int]:
        """(handle, 0), or (0, the Win32 error)."""
        h = self._k.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return (h, 0) if h else (0, self._ct.get_last_error())

    def exit_code(self, handle: int) -> int | None:
        from ctypes import wintypes
        code = wintypes.DWORD()
        if not self._k.GetExitCodeProcess(handle, self._ct.byref(code)):
            return None
        return code.value

    def close(self, handle: int) -> None:
        self._k.CloseHandle(handle)


def _win_pid_alive(pid: int, k) -> bool:
    handle, err = k.open(pid)
    if not handle:
        return err == _ERROR_ACCESS_DENIED   # it exists, we may not look at it
    try:
        code = k.exit_code(handle)
        return code is None or code == _STILL_ACTIVE
    finally:
        k.close(handle)
