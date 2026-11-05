# tn

`tn` is the one helper command of this repository: a Python core (this bundle) plus **one
plugin per bundle**, copied in by that bundle. The full command specification is
[docs/tn.md](../../docs/tn.md); this README covers the install and the core.

## Installs

| path | what | how |
|---|---|---|
| `~/.local/share/tn/lib/tn/` | the core library, the Python package `tn` | `copy` of `lib/tn` (a directory copy: files deleted here are pruned) |
| `~/.local/bin/tn` | Unix entry point (`#!/usr/bin/env python3`, mode 0755) | `copy` of `bin/tn`, Linux and macOS |
| `~/.local/bin/tn.cmd` | Windows entry point (`py -3 -P -m tn`) | `copy` of `bin/tn.cmd`, Windows |
| `~/.config/zsh/conf.d/tn.zsh` | `eval "$(tn shell init zsh)"`: the `tn` shell function and completion | `link` |
| `$PROFILE` block | the same for PowerShell (`tn.cmd shell init pwsh`) | `block` in `{{ documents }}/PowerShell/Microsoft.PowerShell_profile.ps1` |
| (removed) `~/.scripts`, `~/.config/zsh/conf.d/scripts.zsh` | links left by the deleted `scripts` bundle on upgraded machines | `absent` with `only: link` (Linux, macOS) |

Everything is **copied, never linked** (the zsh snippet excepted), so `tn` keeps working while
this checkout moves or is mid-edit, exactly as on a machine without the checkout. Each bundle
with a plugin copies `bundles/<b>/plugin.py` to `~/.local/share/tn/plugins/<b>.py` (with `-`
turned into `_`), so the commands a machine has match the bundles applied on it; `dot remove
<b>` takes the plugin away again. `bundles/*/tests/` is never copied.

Python: **3.11 or later, standard library only** (`tomllib` is 3.11). `common` provides it on
every OS: Homebrew `python` on macOS (the system `/usr/bin/python3` is 3.9), apt `python3` on
Ubuntu (3.12 on 24.04; 22.04's 3.10 is too old), and the Python install manager (`py`) plus its
default runtime on Windows. `bin/tn` checks the version before importing anything and exits 3
with `run: dot apply common` on an older Python.

## Layout

    bin/tn, bin/tn.cmd      entry points (tiny; the version gate lives here and in __main__.py)
    lib/tn/                 the package (copied as a whole)
      cli.py                global flags, dispatch, help, errors, exit codes
      builtins.py           status, doctor, sessions, plugins, config, shell, --version
      complete.py           `tn __complete` for the shell completers
      loader.py             plugin discovery, the ast index (~/.cache/tn/index.json), clashes
      plugin.py             Plugin, arg, Session: the plugin API
      context.py            Context: where am I (roots, project, workspace, repo, names)
      config.py             config files, forges, people, project tn.toml
      output.py, prompt.py  out.*, pick(), confirm(), ask()
      proc.py, fs.py        run/capture/need/git/spawn_detached/handoff, dry-run file writes
      clock.py, term.py     time and TTY checks (patched by tests)
      tomlw.py              TOML writing for `config set` / `config show`
      testing.py            TnTestCase for core and plugin tests
      lint.py               the repository plugin lint (test/tn-tests.sh)
      plugins/__init__.py   the tn.plugins namespace; its __path__ is set to TN_PLUGIN_PATH
    tests/                  core tests (never copied)
    tn.zsh                  the zsh integration

## Writing a plugin

Read docs/tn.md §5. In short:

```python
"""tn plugin for the foo bundle."""
from tn import Plugin, arg, out, need, run

plugin = Plugin("foo", help="what foo does")        # literal arguments only

@plugin.command(help="list foos")
def ls(ctx, args):
    out.records(rows, [("name", "NAME")], empty="No foos. Make one with: tn foo new")

@plugin.check
def foo_installed(ctx):
    """foo installed"""
    need("foo", fix="dot apply foo")
```

and in `bundles/foo/bundle.yml` (`requires: [common, tn]`):

```yaml
  - label: Copy the tn plugin
    copy:
      ~/.local/share/tn/plugins/foo.py: plugin.py
```

Tests go in `bundles/foo/tests/test_*.py`, using `tn.testing.TnTestCase` (a temp HOME, fake
executables on PATH, `self.tn(...)` in process). Run everything with `test/tn-tests.sh`
(or `test/tn-tests.sh foo`), which also lints every plugin.

## Gotchas

- Globals (`-C -n -y -q -v -h --json --dry-run --yes --quiet --verbose --no-color --help
  --version`) are removed from the command line anywhere before `--`, so a plugin can never
  declare them, and a passthrough command needs `--` to hand such a flag to its tool
  (`tn run staging -- ls -l`).
- `tn` cannot change the calling shell's directory on its own: `ctx.request_cd()` writes the
  path to `$TN_CD_FILE`, which only the shell function from `tn shell init` sets. Without it the
  path is printed with a hint.
- **No bytecode next to the copy.** dot's directory copy takes every file (it ignores
  `.gitignore`), and Python rewrites `.pyc` files whose source got a new mtime, so a
  `__pycache__` under `~/.local/share/tn` would be drift on every run and a leftover after
  `dot remove tn`. So `bin/tn` sets `sys.pycache_prefix` and `bin/tn.cmd` sets
  `PYTHONPYCACHEPREFIX` to `~/.cache/tn/pycache` (unless already set), and the first step of
  this bundle deletes any `lib/tn/**/__pycache__` from the checkout before the copy. The
  prefix applies to every module, so the first run also compiles the stdlib modules tn uses
  into it (a few MB); deleting `~/.cache/tn/pycache` is always safe.
  `test/tn-tests.sh` runs with `PYTHONDONTWRITEBYTECODE=1`, so it leaves none behind.
- `tn.cmd` runs `py -3 -P -m tn`: `-m` would otherwise put the current directory first on
  `sys.path`, and a project with its own `tn.py` or `tn/` would be imported instead of tn.
- The index is cached in `~/.cache/tn/index.json` by path, mtime and size; deleting it is
  always safe.
- Colour follows `NO_COLOR`, `--no-color`, `TERM=dumb` and whether the stream is a TTY; JSON is
  never coloured.
