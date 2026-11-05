# tn: command specification

`tn` is the single helper command of this dotfiles repository. It replaces the 163 scripts that
plus one **plugin per bundle**. dot copies a plugin in when its bundle is applied and deletes it on
`dot remove`, so the commands a machine has always match the bundles installed on it.

This document is the canonical spec. Core and each plugin are meant to be built independently
against it, so it says exactly what every command takes, prints and returns. If code and this
document disagree, fix one of them in the same change. Background and rationale are in the
blueprint (the "dotfiles-next Blueprint" page); this document wins wherever the two differ.

Terms. **Must**, **must not** and **may** are normative. "Exit 2" means the process exit status.
`~` is the user's home directory (`Path.home()`: `$HOME` on Unix, `%USERPROFILE%` on Windows).

Contents

1. [Install layout](#1-install-layout)
2. [Command language](#2-command-language)
3. [Context: where am I](#3-context-where-am-i)
4. [Configuration](#4-configuration)
5. [Plugin API](#5-plugin-api)
6. [Built-in commands](#6-built-in-commands)
7. [Plugins](#7-plugins): projects, claude, codex, vscode, git, tmux, python
8. [Old scripts to new commands, and what is dropped](#8-old-scripts-to-new-commands)
9. [Testing](#9-testing)
10. [Implementation notes and open points](#10-implementation-notes-and-open-points)

---

## 1. Install layout

### 1.1 Files on the machine

| path | what | written by |
|---|---|---|
| `~/.local/bin/tn` | Unix entry point, mode `0755`, first line `#!/usr/bin/env python3` | `tn` bundle, `copy` (`when: { os: [linux, macos] }`) |
| `~/.local/bin/tn.cmd` | Windows entry point, runs `py -3` | `tn` bundle, `copy` (`when: { os: windows }`) |
| `~/.local/share/tn/lib/tn/` | the core library, the Python package `tn` | `tn` bundle, `copy` of `bundles/tn/lib/tn` |
| `~/.local/share/tn/plugins/<bundle>.py` | one plugin per installed bundle | each bundle, `copy` of `bundles/<bundle>/plugin.py` |
| `~/.local/share/tn/plugins/<bundle>/` | a plugin that has outgrown one file: a package with `__init__.py` | each bundle, `copy` of `bundles/<bundle>/plugin/` |
| `~/.config/tn/config.toml` | the user's own config (§4). Never written by dot. | the user, `tn config set`, `tn config edit` |
| `~/.config/tn/conf.d/*.toml` | config fragments shipped by bundles (§4) | bundles, `copy` or `template` |
| `~/.config/tn/secrets/` | reserved for secret files a plugin reads (mode 0700; files 0600); none at present | bundles, `secret_file` |
| `~/.local/state/tn/` | runtime state (tunnels, index cache). `$XDG_STATE_HOME/tn` when that is set. | tn |
| `~/.cache/tn/` | disposable caches (the plugin index, §5.8). `$XDG_CACHE_HOME/tn` when set. | tn |

Windows uses the same paths under the user profile (`%USERPROFILE%\.local\share\tn\lib\tn`,
`%USERPROFILE%\.config\tn\config.toml`). It does not use `%APPDATA%`, so one layout serves every OS.

The plugin file is named after the bundle, with `-` replaced by `_` (a module name must be an
identifier). A bundle ships at most one plugin. `bundles/<b>/tests/` is never copied (§9).

### 1.2 Entry points

`bin/tn` (Unix) must stay tiny and must not import anything version-specific before the version
gate:

```python
#!/usr/bin/env python3
import os, sys
from pathlib import Path
if sys.version_info < (3, 11):
    sys.stderr.write("tn: needs Python 3.11 or later (this is %d.%d)\n  run: dot apply common\n"
                     % sys.version_info[:2])
    sys.exit(3)
home = Path(os.environ.get("TN_HOME") or Path.home() / ".local/share/tn")
# Bytecode goes to the cache, never next to the copied sources: dot owns ~/.local/share/tn, and
# a __pycache__ there would be drift it copies over and a leftover `dot remove` cannot see.
if sys.pycache_prefix is None:
    cache = os.environ.get("XDG_CACHE_HOME")
    sys.pycache_prefix = str((Path(cache) if cache else Path.home() / ".cache") / "tn" / "pycache")
sys.path.insert(0, str(home / "lib"))
from tn.cli import main
sys.exit(main())
```

`bin/tn.cmd` (Windows):

```bat
@echo off
setlocal
if not defined TN_HOME set "TN_HOME=%USERPROFILE%\.local\share\tn"
set "PYTHONPATH=%TN_HOME%\lib;%PYTHONPATH%"
rem Bytecode goes to the cache, never into %TN_HOME% (dot owns it), as bin/tn does.
if not defined PYTHONPYCACHEPREFIX (
  if defined XDG_CACHE_HOME (
    set "PYTHONPYCACHEPREFIX=%XDG_CACHE_HOME%\tn\pycache"
  ) else (
    set "PYTHONPYCACHEPREFIX=%USERPROFILE%\.cache\tn\pycache"
  )
)
rem -P: no current directory on sys.path, so a tn.py or tn\ where the user stands is not imported.
py -3 -P -m tn %*
exit /b %ERRORLEVEL%
```

Neither entry point writes bytecode under `~/.local/share/tn`: dot's directory copy of `lib/tn`
takes every file, and a `.pyc` Python rewrites there is drift on every `dot status` and a
leftover after `dot remove tn`. For the same reason the tn bundle deletes `lib/tn/**/__pycache__`
from the checkout before copying, and `test/tn-tests.sh` runs with `PYTHONDONTWRITEBYTECODE=1`.
`-P` (3.11+) matters because `-m` otherwise puts the current directory first on `sys.path`.

`lib/tn/__main__.py` repeats the version gate and calls `tn.cli.main()`, so `py -3 -m tn` and
`python3 -m tn` (with `PYTHONPATH` set) behave exactly like `bin/tn`.

### 1.3 Environment variables tn reads

| variable | default | meaning |
|---|---|---|
| `TN_HOME` | `~/.local/share/tn` | where `lib/` and `plugins/` are |
| `TN_PLUGIN_PATH` | `$TN_HOME/plugins` | plugin directories, `os.pathsep`-separated, searched in order. Replaces the default when set (tests use it). |
| `TN_CONFIG_DIR` | `~/.config/tn` | where `config.toml`, `conf.d/` and `secrets/` are |
| `TN_STATE_DIR` | `$XDG_STATE_HOME/tn` or `~/.local/state/tn` | runtime state |
| `TN_CD_FILE` | unset | set by the `tn` shell function (§6.7); a command that wants the shell to change directory writes the target path there |
| `TN_PICKER` | unset | `list` forces the numbered-list picker even when `fzf` is on PATH |
| `TN_DEBUG` | unset | `1` prints Python tracebacks for internal errors (same as `-vv`) |
| `NO_COLOR` | unset | any non-empty value turns colour off (<https://no-color.org>) |
| `MYPROJECTS_DIR` | `~/myprojects` | default for the projects root when `[roots]` does not set it (§4) |
| `MY_MACHINE` | from `~/.config/dot/local.env` | this machine's short name (§3.4) |
| `MY_NAME`, `MY_EMAIL` | unset | the `me` identity (§4.3): dot prompts, kept in `~/.config/dot/local.env`, exported by `dot env` |
| `DOT_REPO` | from `~/.config/dot/local.env`, else `~/.dot` | the dotfiles checkout, used only to name the bundle behind a missing group (§5.9) |

### 1.4 Python

Python 3.11 or later, **standard library only**. No venv, no pip, no third-party import, and
nothing that exists only in 3.12 or later. That rules out PEP 695 `type` statements and generics,
f-strings that reuse the enclosing quote character, `itertools.batched`, `Path.walk`,
`typing.override`, and `datetime` APIs added in 3.12. 3.11 is the floor because `tomllib`
arrived in 3.11. All paths go through `pathlib`. Subprocesses take argument lists, never
`shell=True`. Plugins must run on Windows unless a command says it is Unix-only; a Unix-only command
exits 3 on Windows with a fix line (§2.6).

The `common` bundle is responsible for a Python 3.11+ being on PATH as `python3` (Unix) and for
`py` (Windows). `tn doctor` reports the version it is running under.

---

## 2. Command language

### 2.1 Grammar

```
tn [global flags] <group> <verb> [target] [flags] [-- passthrough...]
tn [global flags] <built-in> ...
```

* **group**: a noun, provided by a plugin (`claude`, `repo`, `tunnel`) or by core (`status`,
  `doctor`, `sessions`, `plugins`, `config`, `shell`).
* **verb**: one word from the vocabulary in §2.2.
* **target**: optional, and always the first positional argument. When it is left out, it is taken
  from the Context (§3). When it is still missing, the picker rules apply (§2.5).
* **flags**: long options in kebab-case. A short form is allowed only where this spec gives one.
* A group may have a **default command** that runs when the next word is not one of its verbs:
  `tn cd shop`. Only the groups listed in §7 with a default command have one.
* `--` ends option parsing. Everything after it goes to the underlying tool untouched, where a
  command says it passes arguments through.

### 2.2 Verbs

Every plugin uses these verbs with these meanings. `tn <anything> ls` always lists.

| verb | means |
|---|---|
| `new` | create something that does not exist yet |
| `clone` | bring an existing remote thing here |
| `ls` | list; `--json` prints a JSON array |
| `show` | details of one item; `--json` prints a JSON object |
| `open` | open in a browser or editor; for tunnels, open a forward |
| `close` | end what `open` started (tunnels) |
| `start`, `stop` | long-running processes (agent sessions, daemons) |
| `attach` | join a running session in this terminal |
| `sync` | bring local and remote in line |
| `rm` | delete; asks for confirmation unless `--yes` |
| `login` | authenticate the underlying tool |

Some groups need a verb the table does not have. Only the verbs below are allowed, and a new one
must be added here first:

| group | extra verbs |
|---|---|
| `git` | `pull`, `remote add`, `remote ls`, `as`, `whoami`, `init`, `ignore`, `log`, `changed`, `authors`, `export`, `feature new`, `feature ls` |
| `claude` | `restart` (`stop` then `start --resume`), `resume` (wake the sessions that died) |
| `tmux` | `kill` (as the blueprint names it; it means `stop` for a plain tmux session) |
| `config` | `get`, `set`, `edit` |
| `shell` | `init` |

### 2.3 Global flags

Global flags may appear before the group, or anywhere before `--`. Core removes them before the
command's own parser runs, so no plugin may define `-C`, `-n`, `-y`, `-q`, `-v` or `-h`, or the
long forms below.

| flag | effect |
|---|---|
| `-C <dir>` | run as if started in `<dir>`, like `git -C`. Relative paths are resolved against the real cwd. A missing directory exits 2. Repeatable: each one is resolved against the previous. |
| `--json` | machine output: `ls` prints a JSON array, `show` an object, and actions print the object their spec gives. It implies no prompts (§2.5). Commands that hand the terminal to another program (`attach`, `tn tmux new`) reject it with exit 2. |
| `-n`, `--dry-run` | on every command that changes something: print each action as `would: <action>` on stderr, run read-only queries normally, change nothing, exit 0. With `--json` the action's object is printed with `"dry_run": true`. Read-only commands ignore it. |
| `-y`, `--yes` | answer yes to every confirmation. |
| `-q`, `--quiet` | suppress progress and hints on stderr. Errors are still printed. |
| `-v`, `--verbose` | more progress; `-vv` also echoes every subprocess argv and prints tracebacks. |
| `--no-color` | same as `NO_COLOR=1` |
| `-h`, `--help` | help for whatever precedes it (§6.8) |
| `--version` | `tn --version` only (§6.8) |

### 2.4 Output rules

* **stdout carries results only**: tables, JSON, a URL, a path. Something piping `tn` must get
  exactly the result.
* **stderr carries everything else**: progress, `would:` lines, warnings, hints and errors.
* Text tables have an UPPERCASE header row. Columns are separated by two spaces and left-aligned.
  Absent values print as `-`. Times print as an age (`45s`, `12m`, `3h`, `2d`: the largest whole
  unit). An empty list prints one line on **stderr** (`No tunnels. Open one with: tn tunnel open
  <port>`), and stdout stays empty.
* Colour is used only when that stream is a TTY, `NO_COLOR` is unset, `--no-color` is not given and
  `TERM` is not `dumb`. It is never used in JSON.
* JSON follows these conventions:
  * keys are `snake_case`;
  * paths are absolute strings in native form;
  * times are ISO 8601 UTC with `Z` (`"2026-09-30T08:15:00Z"`), and each is paired with an
    integer `age_seconds` where this spec shows one;
  * absent values are `null`, never missing keys;
  * booleans are real booleans.

  A JSON shape given in this spec is a contract. Fields may be added. Renaming or removing one is
  a breaking change, and the Claude skills must be updated in the same change.
* Errors print as `tn: <message>` on stderr, followed by indented lines where they apply:
  `  run: <command>` for a fix, `  hint: <text>` for advice, `  choices: a, b, c`. With `--json`,
  stderr instead gets one JSON line, and stdout stays empty:

  ```json
  {"error": {"code": 2, "message": "which repo?", "fix": null, "hint": null, "choices": ["acme/shop-app", "acme/shop-all"]}}
  ```

  `choices` is what a picker would have offered, so a caller such as a Claude skill can choose and
  call again. Each choice is a **value the same command accepts back as its argument** (a tmux
  name, a port, a `project/repo`), never the descriptive label a person sees in the picker.

### 2.5 Prompts and pickers

A command that needs a value the user did not give may ask for it. It may ask **only when stdin
and stderr are both TTYs and `--json` is not given**. Otherwise it must not prompt: it exits 2 with
the message and the `choices`.

The picker is `tn.pick()`:

1. if `fzf` is on PATH and `TN_PICKER` is not `list`, run
   `fzf --height=40% --reverse --prompt "<prompt>> " --with-nth=2.. --delimiter='\t'`, feeding it
   `<index>\t<label>` lines on stdin. The chosen index comes back on fzf's stdout.
2. otherwise print a numbered list on stderr (`   1) label`) and read one line from stdin:
   `[1-N, or blank to cancel]`.
3. an empty answer, Esc in fzf (exit 130) or Ctrl-C means cancel: `tn: cancelled` and exit 1.
4. with exactly one candidate, `pick()` returns it without asking, and prints `using <label>` on
   stderr.
5. without a TTY, `pick()` exits 2 with `choices` set to each item's `value`: `value=` when given,
   else the label's first column (`tn.prompt.first_column`: the text before the first two spaces
   or tab). Labels are written `"<value>  <description>"`; a label whose first column is not an
   argument the command accepts (`"shop (projects)  ~/..."`) must pass `value=`.

Confirmations use `tn.confirm(question, default=False)`. `--yes` returns true without asking.
Without a TTY or with `--json`, and without `--yes`, it exits 2 with
`tn: <question> — pass --yes to confirm`. Destructive commands (`rm`, `stop --all`, `kill --all`,
`tn codex stop`, `tn ws rm`) confirm.

### 2.6 Exit codes

| code | meaning |
|---|---|
| 0 | done; also a dry run, and "already in that state" (a second `tn tunnel open 3000`) |
| 1 | failed: the command ran and something went wrong, or was cancelled at a prompt |
| 2 | usage: bad arguments, an unknown verb, a missing target that could not be asked for, a command that needs a Context run outside one, `--json` on a terminal-taking command |
| 3 | missing prerequisite: a tool not installed, not logged in, a plugin or bundle not applied, `MY_MACHINE` unset. **Always** printed with a fix: `  run: dot apply tmux`, `  run: tn claude login`, `  run: devtunnel user login -g` |
| other | a command that hands the terminal to a child (`attach`) exits with the child's status |

Ctrl-C at any point exits 130 without a traceback.

---

## 3. Context: where am I

Core works out the Context once, from the cwd after `-C`, before any command runs. It hands the
Context to the command and to every hook. Plugins must not parse `$PWD` themselves.

### 3.1 Roots and layout

Roots come from `[roots]` in the config (§4). Every key names a **projects root**. The default is:

```toml
[roots]
projects = "$MYPROJECTS_DIR, else ~/myprojects"
```

Paths are expanded (`~` and `$VAR`) and normalised, and symlinks are **not** resolved: a root
reached through a link still matches. If the cwd lies under several roots, the **longest** matching
root wins. A tree has this shape:

```
<root>/<project>/<ws>/<repo>/<anything...>
         |         |     |      '- ignored (a subdirectory inside the repo)
         |         |     '- repo: a directory directly inside the workspace
         |         '- workspace: "src", or "src-<suffix>" (src-01, src-02, src-review)
         '- project
```

* The projects tree is `$MYPROJECTS_DIR/<project>/src/<repo>`. A project directory holds `src bin
  rel key tmp` (§7.1) and may hold `tn.toml`.
* A third path component that is not `src` or `src-*` is still recorded as the workspace. This
  keeps the old resolvers' behaviour: they took `parts[2]` whatever it was. In that case `ws_id` is
  the literal directory name.

### 3.2 The Context object

`tn.Context` is a frozen dataclass. Every field below is filled before the command runs, except the
lazy properties.

| field | type | example (`~/myprojects/acme/src-02/shop-app/app/models`) |
|---|---|---|
| `cwd` | `Path` | `/Users/me/myprojects/acme/src-02/shop-app/app/models` |
| `kind` | `"projects"` \| `None` | `"projects"` |
| `root_key` | `str \| None` (the `[roots]` key) | `"projects"` |
| `root` | `Path \| None` | `/Users/me/myprojects` |
| `project` | `str \| None` | `"acme"` |
| `ws` | `str \| None` (the directory name) | `"src-02"` |
| `ws_id` | `str \| None`: `"00"` for `src`, the suffix after `src-` for the others, else the literal name | `"02"` |
| `repo` | `str \| None` | `"shop-app"` |
| `project_dir`, `ws_dir`, `repo_dir` | `Path \| None` | `.../acme`, `.../acme/src-02`, `.../acme/src-02/shop-app` |
| `path` | `Path`: the deepest of `repo_dir`, `ws_dir`, `project_dir`, else `cwd` | `.../acme/src-02/shop-app` |
| `options` | `Options(json, dry_run, yes, quiet, verbose, color)` | |
| `config` | `tn.Config`: merged global config plus this project's `tn.toml` (§4) | |
| `git_root` | lazy `Path \| None`: the nearest ancestor of `cwd` containing `.git` (a directory or a file), found without a subprocess | `.../shop-app` |
| `machine` | lazy `str \| None`: `MY_MACHINE` (§3.4) | `"U1"` |

`ctx.in_project` is true when `project` is set. `ctx.require(level)`, with level `"project"`,
`"ws"` or `"repo"`, returns the Context or raises the usage error from §3.5.

`ctx.for_path(path)` builds the Context for another directory with the same options and config
sources. `projects.resolve` uses it (§7.1.4).

`ctx.to_json()` returns
`{"kind", "root", "project", "ws", "ws_id", "repo", "path", "name", "slug", "git_root", "machine"}`.

### 3.3 Names derived from the Context

Every name below is derived by core, so every plugin labels things the same way. `short_repo` is
`repo` with a leading `<project>-` removed; it is empty when `repo == project`. The old
`_session_name.py` did the same, so `hooli/src/hooli-even` gives `even`.

| name | method | format | example |
|---|---|---|---|
| display name | `ctx.name` | `<project>[/<repo>][@<ws_id>]`; `@<ws_id>` only when `ws != "src"`; `None` outside roots | `acme/shop-app@02`, `acme/shop-app`, `acme@02`, `acme` |
| slug | `ctx.slug` | `slugify(project, short_repo, ws_id)`, with `ws_id` present whenever `ws` is (so `src` gives `00`); at a project root `slugify(project)`; outside roots `slugify(basename(cwd))` | `acme-shop-app-02`, `acme-shop-app-00`, `acme` |
| session name | `ctx.session(kind)` | `<kind>-<slug>` | `claude-acme-shop-app-02` |
| tunnel label | `ctx.tunnel_label(port)` | `slugify(project, short_repo, ws_id unless ws == "src", port)`; outside roots `slugify(basename, port)` | `acme-shop-app-3000`, `acme-shop-app-02-3000` |
| human label | `ctx.label()` | `<Project> <Repo> #<machine>-<ws_id>`; at a project or bare workspace `<Project> #<machine>`; outside roots `<Basename> #<machine>`. Words are split on `-`, `_` and space, and the first letter of each is capitalised. Needs `machine` (§3.4). | `Acme Shop App #U1-02`, `Demo Web Demo #U1-00` |
| forge spec | `config.forge_spec(url)` | `<forge key>:<path>` for a remote URL on a known forge | `work:acme/shop-app` |

`slugify(*parts)` lowercases, joins non-empty parts with `-`, turns every run of characters outside
`[a-z0-9]` into one `-`, and strips leading and trailing `-`. The result is safe as a tmux session
name: tmux rejects `.` and `:`, and treats `#` as format syntax.

### 3.4 The machine name

`machine` comes from `$MY_MACHINE`. If that is unset, it is the last `MY_MACHINE=` line in
`~/.config/dot/local.env` (dotenv syntax, optional `export `, quotes and whitespace stripped).
Otherwise it is `None`. tn never invents one. A command that needs it raises exit 3:

```
tn: MY_MACHINE is not set (it names this machine in session names, e.g. U1)
  run: tn config set machine <name>
```

### 3.5 Outside the roots

Outside every root, `kind`, `project`, `ws` and `repo` are `None`, and `path` is the cwd.

* A command that needs a project, workspace or repo, with no target given, exits 2:
  `tn: not inside a project (expected ~/myprojects/<project>/...); pass a target`.
* Commands that do not need one work anywhere. `tn claude start` in `/tmp/x` names its session
  `claude-x`, because a session outside the convention is legal.
* At a project root, `repo` is `None`. A repo-level command there picks among the project's repos
  (§2.5), and only when a picker is allowed.

---

## 4. Configuration

### 4.1 Files and merge order

Each file is read with `tomllib`, and later files override earlier ones. Tables merge key by key,
recursively. Scalars and arrays are replaced whole.

1. built-in defaults (the values shown in §4.2)
2. `~/.config/tn/conf.d/*.toml`, in lexical filename order. These are written by bundles: the
   git bundle copies the public `git-forges.toml` (`[forges.*]` for github.com, gitlab.com,
   bitbucket). Personal values (people, own namespaces, a self-hosted forge) are never in the
   repository: keep them in your own `git-private.toml` (shape in the git bundle's
   `private.toml.example`; docs/private-overlay.md). `git-private.toml` sorts after
   `git-forges.toml`, so it extends the public forges key by key.
3. `~/.config/tn/config.toml`, the user's own file. It wins over any bundle.
4. the project file `<root>/<project>/tn.toml`, when the Context has a project. Only the project
   keys in §4.4 are read from it. Any other key there is a warning in `tn doctor`, not an error.

An unreadable or invalid file exits 1, and the message names the file and the line tomllib
reports. The exception is `tn doctor`, which reports the problem and carries on.

**No secret goes in any of these files.** Tokens, passwords and keys belong in a tool's own store
(or a file you write yourself under `~/.config/tn/secrets/`), never in tn's config. `tn doctor` warns about any key named `*token*`,
`*password*`, `*secret*` or `*_key` in a config file.

### 4.2 Global schema

```toml
[roots]                         # key -> directory, every key a projects root
projects = "~/myprojects"       # default: $MYPROJECTS_DIR, else ~/myprojects

[proj]
dirs = ["src", "bin", "rel", "key", "tmp"]     # what `tn proj new` creates

[forges.gh]
host  = "github.com"
cli   = "gh"                    # "gh" | "glab" | "none"
kind  = "github"                # "github" | "gitlab" | "bitbucket"; default from cli, else from host
owner = "alex"              # default namespace when a project sets no group
remote = "github"               # remote name `tn git remote add gh` uses; default: the forge key
path  = "{group}/{repo}"        # path template; {group} defaults to the project's group, else owner, else project
ssh_url   = "git@{host}:{path}.git"         # default
https_url = "https://{host}/{path}.git"     # default
clone = "cli"                   # "cli" (gh/glab repo clone) | "ssh" | "https"; default "cli" when cli != "none", else "ssh"
web   = "https://{host}"        # web base; default https://{host}

[forges.work]                   # private (git-private.toml): a self-hosted GitLab
host = "gitlab.example.com"     # your self-hosted GitLab
cli  = "glab"
remote = "gitlab"

[forges.bitbucket]
host = "bitbucket.org"
cli  = "none"
path = "alex/{project}-{repo}"          # the old git-remote-bitbucket.sh shape

[people.alex-work]
name  = "Alex Doe"
email = "alex@example.com"
aliases = ["alex"]             # optional extra words `tn git as` matches

[claude]
trust = true                    # `tn claude start` trusts the directory unless --no-trust
```

Template placeholders are `{host}`, `{path}`, `{project}`, `{repo}`, `{group}` and `{owner}`. An
unknown placeholder is a config error.

### 4.3 People and `me`

`[people.<key>]` needs `name` and `email`; `aliases` is optional. The reserved key **`me`** is
built from `MY_NAME` and `MY_EMAIL` (dot prompts for them once and keeps them in
`~/.config/dot/local.env`; `dot env` exports them) unless a `[people.me]` table overrides it.
Each variable not in the environment is read from that `local.env` (as `MY_MACHINE` is, §3.4):
Windows shells and non-zsh contexts never load `dot env`. When neither is set, `me` does not
exist. The old per-person scripts' identities are in the
private `conf.d/git-private.toml` (from the `tn_git_private` secret), never in the repository:
names and e-mail addresses are not secrets, but they are personal.

### 4.4 Project schema: `<root>/<project>/tn.toml`

```toml
forge    = "work"          # forge key: repo new/clone, git remote add, git open
group    = "acme/web"    # namespace on that forge; default: the project name
identity = "alex-work"    # people key set on every repo tn creates or clones here; doctor flags mismatches

[tunnel]
ports = [3000, 8080]        # `tn tunnel open` with no port
```

`config.project` gives these values (with defaults filled in), or `None` outside a project.

### 4.5 Access from code

```python
cfg = ctx.config
cfg.get("forges.gh.host")            # dotted lookup in the merged config; None when absent
cfg.roots                            # dict[str, Path], expanded
cfg.forge("work") -> Forge          # dataclass: key, host, cli, kind, owner, remote, path, ssh_url, https_url, clone, web
cfg.forges() -> list[Forge]
cfg.forge_for_url(url) -> Forge | None           # by host; accepts scp-style and URL forms
cfg.forge_spec(url) -> str | None                # "work:acme/shop-app"
cfg.person(key) -> Person | None                 # dataclass: key, name, email, aliases
cfg.people() -> list[Person]                     # includes "me" when it exists
cfg.project -> ProjectConfig | None              # forge, group, identity, tunnel_ports: list[int]
cfg.sources -> list[Path]                        # files that were read, in merge order
```

---

## 5. Plugin API

### 5.1 A plugin file

```python
"""tn plugin for the claude bundle."""
from tn import Plugin, Context, arg, run, capture, need, out, pick, confirm, UsageError
from tn.plugins import projects          # allowed: the claude bundle requires projects

plugin = Plugin("claude", help="Claude Code sessions in tmux", requires=["projects"])

@plugin.command(help="start a session here or in a target")
@arg("target", nargs="?", complete="target", help="project, project/repo, repo or a path")
@arg("--resume", nargs="?", const="latest", metavar="ID")
@arg("--ws", metavar="NN|new", help="run in a workspace")
def start(ctx: Context, args) -> int:
    ...

@plugin.check
def tmux_present(ctx: Context):
    """tmux installed"""            # the docstring's first line is the check's label
    need("tmux", fix="dot apply tmux")

@plugin.status
def sessions_here(ctx: Context):
    return f"{len(list_sessions())} sessions"
```

Rules:

* The module must bind exactly one `Plugin` at module level, to the name `plugin`. Every argument
  of that `Plugin(...)` call must be a **literal** (str, list of str), because the index reads it
  without importing the module (§5.8).
* `Plugin(name, *, help, requires=(), groups=())`:
  * `name` is the bundle name with `-` replaced by `_`, and equals the file (or package) name.
  * `requires` names other plugins this one imports. It must be a subset of the bundle's
    `requires` in `bundle.yml`, so that the import is always present on the machine. The lint in §9
    checks this.
  * `groups` lists every command group the plugin provides. The default is `[name]`. When it is
    given, it replaces the default: `vscode` has `groups=["tunnel"]`; `projects` has
    `groups=["proj", "repo", "ws", "cd"]`. A plugin always
    has a group: one with only hooks (`python`) keeps the default, which has no commands.
* Module import must be cheap and free of side effects: no subprocess, no file writes, no network.
  The status, doctor and sessions commands import every plugin.
* Anything a plugin needs from the machine goes through the core helpers (`run`, `capture`, `fs`),
  so that `--dry-run` and the tests work.

### 5.2 Commands and arguments

```python
@plugin.command(name=None, *, group=None, help, passthrough=False)
@arg(*names_or_flags, complete=None, **argparse_kwargs)
def fn(ctx: Context, args: argparse.Namespace) -> int | None
```

* `name` defaults to the function name with `_` replaced by `-`. A trailing underscore is dropped:
  `ls_` becomes `ls`. `name=""` makes the **default command** of the group (§2.1).
* A name with a space defines a two-word verb: `remote add`, `feature new`.
* `group` defaults to the plugin's first group, and must be one of the plugin's `groups`.
* `@arg` takes argparse's `add_argument` arguments unchanged. Decorators apply bottom-up; core
  reverses them, so arguments are declared in reading order.
* `complete=` sets tab completion (§5.7): a completer name (`"project"`, `"repo"`, `"target"`,
  `"ws"`, `"session"`, `"tunnel"`, `"forge"`, `"person"`,
  `"file"`, `"dir"`), or a callable `(ctx, prefix) -> list[str]`.
* `passthrough=True` stops argparse after the declared arguments. Every remaining token, `--`
  included and then removed, lands in `args.rest: list[str]`. A plugin that hands its tail to another program uses it.
* Return value: `None` or `0` means success. Any other int is the exit status. Failures are raised
  (§5.4), not printed.

### 5.3 Hooks

| decorator | signature | used by | contract |
|---|---|---|---|
| `@plugin.status` | `(ctx) -> str \| list[str] \| None` | `tn status` | one short line (or a few) about this plugin's state here and now; `None` means nothing to say. Must not use the network. Should finish within about 300 ms. |
| `@plugin.check` | `(ctx) -> None \| str` | `tn doctor` | label = first docstring line. Returns `None` or a detail string when OK. Raises `Missing` (a prerequisite, with fix) or `Problem(message, fix=None, level="fail" \| "warn")`. May run subprocesses (`capture(..., timeout=10)`). |
| `@plugin.sessions` | `(ctx) -> list[Session]` | `tn sessions` | every agent-like session this plugin runs on the machine, wherever the cwd is |
| `@plugin.completer(name)` | `(ctx, prefix) -> list[str \| tuple[str, str]]` | shell completion | registers a named completer; a tuple is (value, description) |

A plugin may have several hooks of each kind. Core calls every hook inside its own exception
boundary. An exception is reported as `<plugin>: error: <message>` and never stops the other hooks.

```python
@dataclass
class Session:
    kind: str                 # "claude" | "codex"
    id: str                   # stable, unique within kind: the tmux session name, or "daemon"
    name: str                 # human name ("Acme Shop App #U1-02")
    context: str | None       # display name ("acme/shop-app@02")
    dir: str | None
    started: float | None     # epoch seconds
    attached: bool | None
    status: str | None        # "idle" | "busy" | "running" | None
    attach: list[str] | None  # argv that attaches this terminal to it
    extra: dict               # plugin-specific fields, e.g. {"uuid": ...}; emitted as-is in JSON
```

### 5.4 Errors

| exception | exit | printed |
|---|---|---|
| `tn.Fail(message, hint=None)` | 1 | `tn: message` (+ hint) |
| `tn.UsageError(message, choices=None, hint=None)` | 2 | `tn: message` (+ choices, hint) |
| `tn.Missing(what, fix)` | 3 | `tn: what` + `  run: fix`. `fix` is required. |
| `tn.Problem(message, fix=None, level="fail")` | only in checks | a doctor row |

Any other exception is an internal error. It prints `tn: internal error in <plugin>: <exc>
(TN_DEBUG=1 for the traceback)` and exits 1.

### 5.5 Process and file helpers

```python
need(prog, fix) -> str
```
Returns the absolute path from `tn.proc.which`. When `prog` is missing, raises
`Missing(f"{prog} is not installed", fix)`. `which` is `shutil.which` on Unix; on Windows it
searches only absolute `PATH` entries with `PATHEXT`, never the current directory (Python's
Windows `which` looks there first, so a `git.cmd` in a cloned repository would run). Every
helper below resolves `argv[0]` the same way; on Windows a name not found on PATH is "not
installed" rather than passed to CreateProcess (which would also search the current directory).
`capture()` starts its child with `CREATE_NO_WINDOW`, and `run()` does too when tn has no console
(the detached `tn tunnel --for` watcher); `pid_alive()` asks kernel32 (`OpenProcess` +
`GetExitCodeProcess`) instead of starting `tasklist`. On Windows `tn.cli.main` also sets stdout
and stderr to UTF-8 (`errors="replace"`): a piped stream would otherwise use the ANSI code page.

```python
run(argv, *, cwd=None, env=None, input=None, check=True, quiet=False) -> int
```
Runs a command that **changes** something. Output is inherited (it goes to the terminal; commands
that must keep stdout clean pass `quiet=True`, which sends the child's stdout to stderr). Under
`--dry-run` it prints `would: run <shlex-joined argv> [in <cwd>]` and returns 0. With `check=True`,
a non-zero status raises `Fail(f"{argv[0]} exited {code}")`. With `-vv`, the argv is echoed first.
`env` is merged over `os.environ`.

```python
capture(argv, *, cwd=None, env=None, input=None, timeout=None, check=False) -> subprocess.CompletedProcess[str]
```
Runs a **read-only** query, always, dry run included. Text mode, UTF-8, stdout and stderr captured.
A missing executable raises `Missing` only when `check=True`; otherwise it returns a
`CompletedProcess` with `returncode=127`.

```python
spawn_detached(argv, *, cwd=None, log=None) -> int
```
Starts a background process that outlives the terminal and returns its pid. On Unix it uses
`start_new_session=True` (the old `setsid`). On Windows it uses
`DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`. stdout and stderr go to `log`, or to `os.devnull`.
It honours dry-run.

```python
handoff(argv, *, cwd=None, env=None) -> NoReturn
```
Gives the terminal to another program. On Unix, `os.execvpe` after flushing. On Windows,
`subprocess.run` followed by `sys.exit(returncode)`. `--json` is rejected before it is reached.
Dry-run prints `would: run ...` and exits 0.

```python
fs.mkdir(path, mode=None)
fs.write_text(path, text, mode=None)
fs.append_text(path, text)
fs.remove(path)
fs.rmtree(path)
fs.replace_line(path, match_prefix, line)
```
File writes that honour dry-run. `write_text` is atomic: a temporary file in the same directory,
then `os.replace`.

`git(repo_dir, *args, check=False)` is `capture(["git", "-C", repo_dir, *args])`. It raises
`Missing("git is not installed", "dot apply git")` when git is absent.

### 5.6 Output, prompts, cd

```python
out.info(msg)                 # stderr progress; hidden by -q
out.warn(msg)                 # stderr "warning: ..."; hidden by -q
out.hint(msg)                 # stderr "  hint: ..."; hidden by -q
out.debug(msg)                # stderr, only with -v
out.line(text)                # stdout result line
out.records(rows, columns, *, empty)
```
`out.records` is how `ls` prints. `rows` is a list of dicts, each holding the full JSON shape.
`columns` is a list of `(key, HEADER)` or `(key, HEADER, formatter)`. In text mode it prints the
table. With `--json` it prints `json.dumps(rows, indent=2)`. For an empty list it prints `empty`
on stderr, or `[]` with `--json`.

```python
out.record(obj, fields)       # how `show` prints: "Key: value" lines, or the object as JSON
out.result(obj, text=None)    # how actions print: --json dumps obj; otherwise text(obj) is printed, if given
pick(items, *, label=str, value=None, prompt, what)   # §2.5; `what` names the thing in the no-TTY error ("which repo?"); `value` is what `choices` holds
confirm(question) -> bool                  # §2.5
ctx.request_cd(path)          # §6.7
```

### 5.7 Completion

`tn shell init` installs completion that calls the hidden command
`tn __complete <cword> -- <word0> <word1> ...`. That command prints one candidate per line, as
`value` or `value\tdescription`. Groups and verbs come from the index (§5.8), plus an import of the
plugin that owns the group. Argument values come from the argument's `complete=` completer.
`__complete` never prompts, never fails loudly, and prints nothing on any error.

Built-in completers, provided by projects (`project`, `repo`, `target`, `ws`) and core:

* `session`: the ids from every sessions hook;
* `tunnel`: the ports that are open now;
* `forge`: the forge keys;
* `person`: the people keys, and `me`;
* `file`, `dir`: left to the shell.

When the plugin that provides a completer is absent, the completer returns nothing.

### 5.8 Discovery, lazy loading, clashes

Discovery happens on every call. Nothing is registered in advance.

1. **List** every `*.py` file and every package directory (one with `__init__.py`) in each
   directory of `TN_PLUGIN_PATH`. Names starting with `_` or `.` are ignored. The first directory
   that has a name wins, and a later duplicate is ignored with a `-v` note. A file and a package
   with the same name in one directory is an error for that plugin.
2. **Index** each one without importing it. Parse the source with `ast`, find the module-level
   `plugin = Plugin(...)` call, and read `name`, `help`, `requires` and `groups` from its literal
   arguments. The result is cached in `~/.cache/tn/index.json`, keyed by path, mtime and size. A
   file whose call is not all literals is indexed as broken.
3. **Map** each group to its plugin. If two plugins claim the same group, that group is
   **refused**. Running any command in it exits 1:
   `tn: group "tunnel" is claimed by both vscode.py and other.py; remove one (dot remove <bundle>)`.
   Other groups keep working, and `tn plugins` and `tn doctor` report the clash.
4. **Import** only the plugin that owns the requested group, via
   `importlib.import_module(f"tn.plugins.{name}")`. `tn.plugins` is a package whose `__path__` is
   set at start-up to the `TN_PLUGIN_PATH` directories, so `from tn.plugins import projects` inside
   a plugin works the same way. The plugin's `requires` are imported first. A required plugin that
   is not installed exits 3:
   `tn: the claude plugin needs the projects plugin` / `  run: dot apply projects`. If a plugin
   fails to import (syntax error, bad literal), its groups exit 1 with the error, and other groups
   are unaffected.
5. **Hooks.** `tn status`, `tn doctor`, `tn sessions` and `tn plugins` import every plugin and run
   its hooks. A plugin that fails to import becomes one error row.

Importing a plugin only registers it. Commands are attached to the `Plugin` object by the
decorators, and core builds the argparse tree from it.

### 5.9 A group that is not installed

When `<group>` belongs to no installed plugin:

1. Look for the dotfiles checkout at `$DOT_REPO`, else the `DOT_REPO=` line of
   `~/.config/dot/local.env`, else `~/.dot` (never `~/.dotfiles`, the old dotbot checkout).
2. If it exists, index (§5.8 step 2) every `bundles/*/plugin.py`, and `bundles/*/plugin/__init__.py`
   for package plugins. If one of them provides the group, exit 3:
   ```
   tn: "tunnel" comes from the vscode bundle, which is not applied on this machine
     run: dot apply vscode
   ```
3. Otherwise exit 2:
   `tn: unknown command "tunel"` / `  hint: did you mean "tunnel"? (tn --help lists the groups)`.
   Suggestions use `difflib.get_close_matches` over the installed groups and the repo's groups.

A verb that the plugin does not have is a plain usage error (exit 2) with the plugin's verb list.

---

## 6. Built-in commands

### 6.1 `tn status`

One screen that shows where you are.

```
$ tn status
context   acme/shop-app@02           ~/myprojects/acme/src-02/shop-app
machine   U1
claude    2 sessions (1 attached); here: claude-acme-shop-app-02 busy
git       main, 3 changed, ahead 1
tunnel    1 open: 3000 https://k7m2xq04-3000.asse.devtunnels.ms (private, 12m)
```

The first lines come from core. The rest come from each plugin's status hooks, in plugin-name
order, each line prefixed by the plugin's first group. Outside every root, `context` shows `-` and
the cwd.

`--json`:

```json
{"context": {"kind": "projects", "root": "...", "project": "acme", "ws": "src-02", "ws_id": "02", "repo": "shop-app", "path": "...", "name": "acme/shop-app@02", "slug": "acme-shop-app-02", "git_root": "...", "machine": "U1"},
 "plugins": {"claude": ["2 sessions (1 attached); ..."], "git": ["main, 3 changed, ahead 1"]},
 "errors": {"git": "..."}}
```

It always exits 0, unless the config cannot be read (exit 1).

### 6.2 `tn doctor`

Runs the core checks, then every plugin check, and prints one row per check.

```
ok    core     Python 3.12.4 (3.11+ needed)
ok    core     ~/.local/bin on PATH
FAIL  claude   logged in                     run: tn claude login
warn  git      identity of acme/src/shop-all is alex@example.org, tn.toml says alex@example.com
                                             run: tn -C ~/myprojects/acme/src/shop-all git as alex-work
ok    tunnel   devtunnel installed
```

The core checks are:

* the Python version;
* `TN_HOME/lib` present;
* the plugin directories readable;
* every plugin indexes and imports;
* no group clashes;
* the config files parse, with no unknown project keys and no secret-looking keys;
* `~/.local/bin` is on PATH, and `tn` resolves to it;
* `MY_MACHINE` is set (warn; fix `tn config set machine <name>`);
* the shell integration is loaded. This is `warn` when `TN_CD_FILE` support is absent, detected by
  the shell function exporting `TN_SHELL=1`. The fix is `eval "$(tn shell init zsh)"`, which the
  tn bundle's `tn.zsh` does.

It exits 0 when nothing failed (warnings allowed), and 1 when any check failed. It never exits 3:
the fixes are in the rows. `--json` prints an array of
`{"plugin", "check", "status": "ok"|"warn"|"fail"|"error", "detail", "fix"}`.

### 6.3 `tn sessions` and `tn sessions attach [name]`

`tn sessions` lists every row from every sessions hook, with Claude and Codex side by side:

```
KIND    ID                          NAME                     CONTEXT              STATUS  AGE  ATTACHED
claude  claude-acme-shop-app-02   Acme Shop App #U1-02   acme/shop-app@02   busy    3h   yes
codex   daemon                      codex daemon             -                    running 2d   -
```

`--json` prints an array of the `Session` fields plus `age_seconds`.

`tn sessions attach [name]` matches `name` against `id`, `name`, `context` and the `uuid` prefix in
`extra` (case-insensitive, exact before prefix before substring). With several matches, or no name,
it picks (§2.5). It then hands off to the session's `attach` argv. Inside tmux, the claude plugin's
argv is already `tmux switch-client`.

### 6.4 `tn plugins`

```
PLUGIN    GROUPS                  REQUIRES   FILE                                   STATE
claude    claude                  projects   ~/.local/share/tn/plugins/claude.py    ok
projects  proj repo ws cd         -          ~/.local/share/tn/plugins/projects.py  ok
```

STATE is `ok`, `broken: <reason>`, `clash: <group> also in <other>`, or
`missing requires: <name>`. `--json` prints an array of
`{"name", "groups", "requires", "file", "state", "help"}`. With `--repo`, it also lists the plugins
in `$DOT_REPO/bundles/*` and whether each is installed.

### 6.5 `tn config get|set|edit`

* `tn config get <key> [--project]` prints the value from the merged config: a dotted key, or
  `machine`. A table prints as TOML (or a JSON object with `--json`). A missing key exits 1.
  `--project` reads the project's `tn.toml` alone and needs a project Context.
* `tn config set <key> <value> [--project]` edits one key.
  * The value is read as TOML: `3000`, `true`, `["a", "b"]`, and a bare word is a string.
  * The write is a **line-level edit** of `config.toml` (or the project `tn.toml` with
    `--project`). It replaces the `key = ...` line inside the right `[table]`. If there is none, it
    appends the key at the end of that table, adding the `[table]` header at the end of the file
    when missing. Comments and order elsewhere are kept.
  * The file is created when missing.
  * The result must re-parse, or the edit is rolled back and it exits 1.
  * The merged config (every `conf.d` file plus the edited `config.toml`; the project keys with
    `--project`) must also still validate: a problem the edit would add exits 1 with
    `nothing was written` and `run: tn config edit`. Problems already there do not block it, so a
    broken key can be fixed with `set`. A config that fails validation at load names the fix
    (`tn config edit`) and the files it was merged from.
  * The special key **`machine`** writes `MY_MACHINE=<value>` into `~/.config/dot/local.env`,
    replacing the existing line or appending one. It does not write to `config.toml`: dot's
    `local.env` stays the single source, which `dot env` and `dot apply` also read. It prints
    `hint: open a new shell (or re-source dot env) for MY_MACHINE to reach this one`. This replaces
    `_machine.sh`.
* `tn config edit [--project]` opens the file in `$VISUAL`, else `$EDITOR`, else `vi` (Unix) or
  `notepad` (Windows). A missing file is first created from a commented template of §4.2 (or §4.4).
  After the editor exits, the file is parsed, and any error is printed with the file and line
  (exit 1; the edit is kept).
* `tn config show [--json]` prints the effective merged config and, as comments, the source files
  in merge order.

### 6.6 JSON for skills

Skills never parse text. Every command a skill runs is either an action with a documented `--json`
object or an `ls`/`show` command. §7 lists the JSON of each.

### 6.7 `tn shell init zsh|bash|pwsh`

Prints shell code on stdout. The tn bundle links a `tn.zsh` into `~/.config/zsh/conf.d/` containing
`command -v tn >/dev/null && eval "$(tn shell init zsh)"`. On Windows, the pwsh profile gets the
equivalent. The code defines two things.

**1. A `tn` shell function** that lets tn change the caller's directory. zsh and bash:

```sh
tn() {
  local __tn_f __tn_rc
  __tn_f="$(mktemp "${TMPDIR:-/tmp}/tn-cd.XXXXXX")" || { command tn "$@"; return; }
  TN_CD_FILE="$__tn_f" TN_SHELL=1 command tn "$@"; __tn_rc=$?
  if [ -s "$__tn_f" ]; then builtin cd -- "$(cat -- "$__tn_f")" || __tn_rc=1; fi
  rm -f -- "$__tn_f"
  return $__tn_rc
}
```

pwsh: the same `tn` function (`tn shell init pwsh` prints it in full), with two additions.

* PowerShell's binder drops a bare `--` given to a function, so `tn run prod -- tail -n 50`
  would reach tn as `ssh prod tail -n 50` (and `-n` would be `--dry-run`). A helper,
  `__tn_args`, re-parses `$MyInvocation.Line`; when the call has exactly one element more than
  `$args` and that element is `--`, it puts `--` back in place. What it cannot line up
  (splatting) is passed on unchanged; quoting `'--'` always works.
* tn prints UTF-8 (§5.5), so the function sets `[Console]::OutputEncoding` to UTF-8 while tn
  runs and restores it after; the completer does the same around `tn.cmd __complete`.

`ctx.request_cd(path)`:

* when `TN_CD_FILE` names a writable file, write the absolute path (UTF-8, no newline) and nothing
  else;
* otherwise print the path on **stdout** and
  `hint: tn cannot change your shell's directory without its shell function; add eval "$(tn shell init zsh)"`
  on stderr (on Windows: `add tn shell init pwsh | Out-String | Invoke-Expression to $PROFILE`,
  the same line `tn doctor` gives).

A dry run writes nothing. `reload` (`exec $SHELL -l`) stays a plain zsh function in the zsh bundle.
A child process cannot replace its parent shell.

**2. Completion** through `tn __complete` (§5.7):

* zsh: `compdef _tn tn`, with `_tn` calling `tn __complete $((CURRENT-1)) -- ${words[@]}` and
  feeding `_describe`;
* bash: `complete -o default -F _tn tn`;
* pwsh: `Register-ArgumentCompleter -Native -CommandName tn,tn.cmd`.

An unknown shell exits 2.

### 6.8 `tn --help`, `tn <group> --help`, `tn --version`

* `tn --help` (and a bare `tn`) prints usage, the global flags, the built-ins and every installed
  group with its plugin's `help`, read from the index without importing plugins. It ends with
  `tn <group> --help for its commands`.
* `tn <group> --help` imports that plugin and lists its verbs with their `help`.
* `tn <group> <verb> --help` is argparse's help for the command.
* Help always exits 0 and goes to stdout.
* `tn --version` prints `tn <version> (python <x.y.z>, <lib path>)`. With `--json` it prints
  `{"tn": "...", "python": "...", "lib": "...", "plugins": {"claude": "<file>", ...}}`. The version
  is `tn.__version__` in `lib/tn/__init__.py`. It is tn's own version, not a pinned tool version.

---

## 7. Plugins

Each subsection gives the bundle, its `Plugin(...)` declaration, and every command:

* **Synopsis**: the command line.
* **Behaviour**: numbered steps in order.
* **JSON**: the `--json` shape.
* **Exits**: the codes beyond the common rules.

"Needs repo" means the command requires a repo Context or a target (§3.5).

### 7.1 projects

```python
plugin = Plugin("projects", help="projects, repos, workspaces, and cd",
                groups=["proj", "repo", "ws", "cd"])
```

Bundle `projects`: `requires: [common, tn]`. It has no packages, only the plugin copy.

#### 7.1.1 `proj`

**`tn proj new <name> [--root KEY] [--forge F] [--group G] [--identity P] [--cd]`**

1. Validate the name against `^[a-z0-9][a-z0-9._-]*$`, else exit 2.
2. The directory is `<roots[KEY or "projects"]>/<name>`. If the directory exists, exit 1:
   `tn: ~/myprojects/<name> already exists`.
3. Create `[proj].dirs` (default `src bin rel key tmp`).
4. If `--forge`, `--group` or `--identity` is given, write `tn.toml` with those keys. Unknown forge
   or person keys exit 2 with the choices.
5. Hint: `add a repo: tn repo new <name> -p <project>   or clone one: tn repo clone gh:owner/repo -p <project>`.
6. `--cd`: `request_cd(project_dir)`.

JSON: `{"project": "<name>", "root": "projects", "path": "...", "dirs": [...], "config": {"forge": null, "group": null, "identity": null}}`.

**`tn proj ls [--root KEY] [--all]`**

Lists the projects under the projects roots. `--root` limits the
listing to one root. A project is any directory directly under a root that is not hidden.

| column | key | meaning |
|---|---|---|
| PROJECT | `name` | directory name |
| ROOT | `root` | root key |
| REPOS | `repos` | names of git repos in `src/` (text: the count) |
| WS | `workspaces` | ws_ids other than `00` (text: comma list) |
| FORGE | `forge` | from tn.toml, or null |
| IDENTITY | `identity` | from tn.toml, or null |
| — | `path` | absolute path (JSON only) |

**`tn proj show [project]`**

`project` defaults to the Context. The JSON is the `ls` row plus `"repos"` as the full
`tn repo ls` rows for `src/`, plus `"config"` (the project's tn.toml as a table).

#### 7.1.2 `repo`

**`tn repo new <name> [-p PROJECT] [--forge [F]] [--cd]`**. Needs a project, from `-p` or the
Context.

1. The target is `<project>/src/<name>` (in the **`src`** workspace, even when run from `src-NN`,
   because new repos belong to the original). If it exists, exit 1.
2. `git init` in the new directory.
3. Set the identity (§7.1.4).
4. Write `.gitattributes` as in `tn git init` (§7.5).
5. `--forge [F]` (`nargs="?"`; with no value, the project's `forge`) adds the remote as
   `tn git remote add` does. No remote is added by default.
6. Hint: `add a remote: tn git remote add <forge>`.

JSON: `{"project", "repo", "path", "identity": {"key", "name", "email"} | null, "remote": {"name", "url"} | null}`.

**`tn repo clone <source> [name] [-p PROJECT] [--cd]`**. Needs a project.

`source` forms:

* `<forge>:<path>`, for example `gh:alex/demo-app` or `work:acme/web/shop-all`: the
  forge from config;
* a URL (`https://…`, `ssh://…`, `git@host:path`): `git clone` as given;
* a bare `owner/repo`: the project's `forge`. With no project forge, exit 2
  `say which forge: tn repo clone gh:owner/repo (forges: gh, work, ...)`.

Steps:

1. `name` defaults to the last path segment without `.git`. GitLab paths are nested groups, so this
   is the last segment only. The name is a real choice: remote and local names often differ, as in
   `alex/demo-app` cloned to `demo/src/app`. So on a TTY with no `name` given, tn
   asks with the default pre-filled. Without a TTY it uses the default.
2. The target is `<project>/src/<name>`. If it exists, exit 1.
3. Clone according to the forge's `clone`:
   * `cli` with `gh`: `gh repo clone <path> <target>` (gh supplies the stored credentials);
   * `cli` with `glab`: `glab repo clone <path> <target>`;
   * `ssh` / `https`: `git clone <url> <target>`.

   The remote stays `origin`.
4. Set the identity (§7.1.4), then print `committer here: Name <email>`.

JSON: `{"project", "repo", "path", "source", "url", "forge": "<key>" | null, "identity": {...} | null}`.

Exits: 3 when the forge's cli is required and missing (`dot apply gh` or `dot apply glab`). A
failed clone exits 1 with git's own stderr passed through.

**`tn repo ls [project] [--ws ID | --all-ws] [--all] [--fetch]`**. Without a project and without
`--all`, exit 2. With `--all`, it covers every repo of every project in every root.

Covers the repos in the Context's workspace (default `src`), `--ws ID`, or every workspace. It reads
each repo's state with git subprocesses: `git status --porcelain=v2 --branch`. There is no network
unless `--fetch`, which runs `git fetch --quiet --prune` on each remote first.

| column | key | meaning |
|---|---|---|
| REPO | `repo` | |
| WS | `ws_id` | |
| BRANCH | `branch` | null when detached (text: `(detached <short>)`) |
| DIRTY | `dirty` | number of changed and untracked entries |
| AHEAD / BEHIND | `ahead`, `behind` | against the upstream; null without one |
| REMOTE | `remote` | forge spec of the upstream (or first) remote, else its URL, else null |
| — | `path`, `project`, `upstream`, `remotes` (list of `{name, url, forge}`), `identity` (`{name, email}` local or null), `identity_ok` (bool or null when the project sets none) | JSON only |

**`tn repo show [repo]`**. Needs a repo. It shows the `ls` row plus the following; this replaces
`repo-stats.sh`:

* `last_commit`: `{hash, date, age_seconds, author, subject}` (`date` in UTC with `Z`, §2.4);
* `authors`: the top 10 from `git shortlog -sne HEAD`, as `{name, email, commits}`;
* `files`: a count by extension of `git ls-files`, top 15, as `{ext, count}`;
* `markers`: which of `manage.py`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`,
  `Dockerfile` and `nginx*` exist, with repo-relative directories.

#### 7.1.3 `ws`: parallel workspaces

**`tn ws new [ID] [--cd]`**. Needs a project. A port of `src-new.sh`, behaviour for behaviour:

1. `ID` of `01` or `src-01` gives `src-01`. Anything else is literal (`review` gives `src-review`).
   With no ID, it takes the lowest unused `src-NN`, starting at 01. If the directory exists, exit 1.
   If `src/` does not exist, exit 1 (`nothing to copy`).
2. For each entry of `src/`, in name order:
   * not a git repo: skip, with `reason: "not a git repository"`;
   * no default branch: skip, with `reason: "no branch to check out"`.

   The default branch is, in order: `refs/remotes/origin/HEAD` minus `origin/`; `main` or `master`
   if a local branch exists; the current `HEAD` branch.
3. `git clone --quiet <src/repo> <dest>`. This is a local clone: it hardlinks objects and writes
   nothing to the source. **Never** `git worktree`, because it writes into the source's `.git`.
4. Copy the source's remotes:
   * If it has any, remove `origin` from the clone, add every source remote with the same name and
     URL, and pick a primary (`origin` if present, else the first). Then
     `git fetch --quiet --prune <primary>`.
   * With no remotes: check the branch out from the local clone's `origin/<branch>`, then
     **remove `origin`**, so nothing points at the original directory.
5. `git checkout -B <branch> <primary>/<branch>` and set the upstream. If the primary lacks the
   branch, check out the local one.
6. Delete every other local branch, so exactly one exists.
7. Unpushed count: `git -C <src/repo> rev-list --count <dest HEAD>..refs/heads/<branch>`. When it
   is positive, print `note: src/<repo> is N unpushed commit(s) ahead - not copied`.
8. When `.gitmodules` exists: `note: has submodules - run 'git submodule update --init' in it`.
9. End with `Created <path> - C copied, S skipped, F failed`, then this hint: gitignored files
   (`.env`, `node_modules`, `.claude/settings.local.json`) do not come along; the workspace is a
   new, untrusted path for Claude, and `tn claude start` trusts it.
10. Exit 1 if any repo failed. The workspace is kept.

stdout: the workspace path (unless `--json`).

JSON: `{"project", "workspace": "src-01", "ws_id": "01", "path", "repos": [{"repo", "state": "copied"|"skipped"|"failed", "branch", "primary_remote", "unpushed": 0, "submodules": false, "reason": null}]}`.

The same logic is the Python API `projects.ws_new(ctx, id=None) -> WsResult`, which
`tn claude start --ws new` uses.

**`tn ws ls [project]`**

| column | key |
|---|---|
| WS | `ws_id` (`00` for `src`) |
| DIR | `ws` |
| REPOS | `repos` (names; text: count) |
| DIRTY | `dirty_repos` (count of repos with changes) |
| UNPUSHED | `unpushed_repos` (count of repos failing the §7.1.3 `rm` safety test) |
| SESSIONS | `sessions` (ids of sessions from every sessions hook whose `dir` is inside it) |
| AGE | `age_seconds` (directory mtime) |
| — | `path` |

**`tn ws rm <ID>`**. Needs a project.

1. `ID` normalises as in `new` and must be a single name (letters, digits, `.`, `_`, `-`; no
   path separators). `src` and `00` are refused (exit 2), and so is anything that is not a
   `src-*` directory directly inside the project once symlinks are resolved.
2. Safety test. Every repo in the workspace must have all of the following, otherwise it exits 1
   and lists what blocks it:
   * no uncommitted or untracked changes: `git status --porcelain` is empty;
   * no stash: `git stash list` is empty;
   * no git operation in progress: no `rebase-merge`, `rebase-apply`, `MERGE_HEAD`,
     `CHERRY_PICK_HEAD` or `REVERT_HEAD` in the git directory;
   * no local commit that is safe nowhere else: `git rev-list HEAD --branches --tags --not
     --remotes` (HEAD left out on an unborn branch; a detached HEAD and local tags count), minus
     every commit the original `src/<repo>` reaches (`git -C src/<repo> rev-list --all`), is
     empty. The original is kept, so what it holds is not lost;
   * a repo with commits must have at least one remote, unless its original `src/<repo>` exists
     (a copy of a `tn repo new` repo has no remote and is compared with its original instead).

   Every other entry of the workspace, hidden ones included, blocks it too: a hidden git repo is
   tested like any other, and any other file or directory is reported as `not a git repository
   (would be deleted)`. Only `.DS_Store`, `Thumbs.db` and `desktop.ini` are ignored.

   There is no `--force`. Uncommitted work is never deleted by tn.
3. If any session has its `dir` inside the workspace, exit 1:
   `stop it first: tn claude stop <id>`.
4. Confirm `delete ~/…/src-02 (3 repos)?` (§2.5), then remove the directory tree.
5. If the cwd was inside it, `request_cd(project_dir)`.

JSON: `{"project", "workspace", "path", "removed": true, "repos": [...]}`. With a refusal and
`--json`, the error includes `"hint"` with the blocking items.

#### 7.1.4 Identity (shared rule)

`projects.identity_for(ctx) -> Person | None` returns the project's `identity`
person, else `me`, else `None`. `projects.set_identity(repo_dir, person)` runs
`git config user.name` and `git config user.email`, local to the repo. `repo new`, `repo clone` and `git init` call both. With `None`, the global identity stays and a hint
says so.

#### 7.1.5 `cd`

**`tn cd [query...] [--print]`** is the default command of group `cd`.

1. Candidates are, in every root: each project; each workspace dir other than `src`
   (`acme@02`); each repo in each workspace (`acme/shop-app`, `acme/shop-app@02`). Each
   candidate has its display name, its path, and for repos the remote paths as secondary keys.
2. Score each candidate against the query words, joined with `/`, case-insensitively:

   | match | score |
   |---|---|
   | exact display name or exact last component | 100 |
   | prefix of a component | 80 |
   | substring | 60 |
   | subsequence of the display name | 40 |
   | secondary key (remote) | half of the above |

   Ties go to the `src` workspace over `src-NN`, then the shorter path.
3. When one candidate has the highest score, `request_cd(path)`. With several at the highest score,
   or no query at all, pick (§2.5). Without a TTY, exit 2 with the choices.
4. `--print`, or `--json` (`{"name", "path", "kind": "project"|"ws"|"repo"}`), prints instead of
   changing directory.
5. No match: exit 1 `no project, workspace or repo matches "<query>"`.

#### 7.1.6 Python API for other plugins

```python
projects.resolve(ctx, target: str | None, *, ws: str | None = None,
                 prefer_repo: bool = False, what: str = "target") -> Where
```

It resolves in this order:

1. `None` gives the Context.
2. A value containing a path separator, or starting with `.` or `~`, is a directory. It must exist
   (exit 2).
3. `project/repo[@ws]`.
4. `project[@ws]`.
5. A bare word, searched across all roots in this order: a project; a repo; a remote path.

Several matches pick (§2.5) or exit 2 with the choices. Each choice is a target resolve
accepts back as given (`project/repo[@ws]`, or the absolute path when that name matches more than
one). `prefer_repo=True` turns a project holding
exactly one repo into that repo.

`ws="NN"` or `ws="name"` gives the same relative position in that workspace, which must exist, else
exit 2 `no workspace src-NN in <project>: tn ws new NN`. `ws="new"` runs `ws_new` first. `ws` with
no project in the target or Context exits 2.

`Where` has `path: Path`, `ctx: Context` (from `ctx.for_path`), `name`, `session(kind)`, `label()`,
and `git_root: Path | None`.

Also exported:

* `iter_projects(cfg, root=None) -> Iterator[ProjectRef]`
* `iter_repos(project_dir, ws=None | "all") -> Iterator[RepoRef]`
* `repo_state(repo_dir, fetch=False) -> RepoState`: the `repo ls` row
* `default_branch(repo_dir) -> str | None`
* `ws_new(ctx, id=None) -> WsResult`
* `identity_for(ctx)`, `set_identity(repo_dir, person)`

Completers: `project`, `repo`, `target`, `ws`.

Status: `projects: <display name>, <n> repos, workspaces 00 01 02`, only inside a project.

Checks: the roots exist (`warn`, with the fix `mkdir -p ~/myprojects`); `git` is installed (fail,
`dot apply git`).

### 7.2 claude

```python
plugin = Plugin("claude", help="Claude Code sessions in tmux, for Remote Control", requires=["projects"])
```

Bundle `claude`: `requires: [common, tn, projects]`. Sessions run as an interactive `claude` inside
a detached tmux session, not `--bg`, because `--bg` sessions go offline after a long idle. Windows
has no tmux: `start` opens the session in a new Windows Terminal tab (`wt -w 0 new-tab`; a `cmd /c
start` window without `wt`) and the tab is the session. A registry, `~/.claude/tn-sessions.json`
(name, title, uuid, dir, context, created), lets `ls` list a session whose tab was closed
(`attached` = its claude is alive per `claude agents`), `attach` reopen it with `--resume` (a
session whose tab is still open fails: tn cannot raise a tab), and `stop` `taskkill` the process
tree and drop the entry. With tmux the registry outlives the tmux sessions for `resume`: `start`
records each one (plus `account`, the `claude auth status` e-mail), `stop` sets `stopped`
(epoch seconds) instead of dropping it, and `ls` adopts live tn sessions it lacks
(`account: null`) and drops entries whose directory is gone. None of them write in a dry run.
`login` works everywhere.

**`tn claude start [target] [--ws NN|new] [--resume [ID]] [--name NAME] [--no-trust]`**

1. `need("tmux", fix="dot apply tmux")`. Get `claude`'s absolute path with
   `need("claude", fix="dot apply claude")`. Unless `~/.claude.json` has
   `hasCompletedOnboarding: true` (a missing file counts as not set; unreadable or invalid JSON
   is left to step 7), exit 3 `Claude Code has not been set up on this machine ...` with
   `run: claude`: until then claude opens its first-run screens, which a detached session sits
   on while staying alive.
2. `where = projects.resolve(ctx, target, ws=args.ws, prefer_repo=True)`. The session directory is
   `where.git_root` when the path is inside a git repo, else `where.path`. When they differ, print
   `(git root of <path>)` to stderr.
3. Names:
   * The **title** is `--name`, else `Context(root).label()`, which needs `machine` (exit 3 per
     §3.4 when it is unset).
   * The **tmux name** is `claude-` + `slugify(--name)` when a name is given, else
     `ctx.session("claude")` for the root Context.
   * There is no name prompt. The old one is replaced by `--name`.
4. If a tmux session `=<tmux name>` exists, exit 1: `already running in tmux session <name>`, with
   `run: tn claude attach <name>`.
5. The uuid:
   * `--resume` with no ID means `latest`: the newest `*.jsonl` by mtime in
     `~/.claude/projects/<dir with every character outside [A-Za-z0-9] replaced by '-'>/`. If there
     is none, exit 1 `no conversation to resume in <dir>`.
   * `--resume ID` must be a full uuid. A short id exits 2 with `--resume takes the full uuid (the transcript file name)`.
   * Otherwise `str(uuid.uuid4())`.
6. If any tmux session has `@claude_uuid == uuid`, exit 1 `conversation <uuid> is already running`.
   With `--resume`: if `claude agents --json` lists that `sessionId` with a positive integer `pid`
   that is alive (`os.kill(pid, 0)`; `PermissionError` counts as alive), exit 1
   `conversation <uuid> is running outside tmux (pid N); exit it first`. Two processes on one
   transcript corrupt it.
7. Trust, unless `--no-trust` or `[claude] trust = false`. In `~/.claude.json`, set
   `projects["<abs dir>"].hasTrustDialogAccepted = true`:
   * a missing file starts as `{}`;
   * invalid JSON exits 1 and leaves the file untouched;
   * the write is atomic (temp file + `os.replace`), and skipped when the flag is already true;
   * print `trusted <dir>` when it changed.

   Trust is read at process start, so it must happen before step 8.
8. Build the args: `["--session-id", uuid]`, or `["--resume", uuid]` when resuming, then
   `["--remote-control", title, "-n", title]`. Both names are needed: `--remote-control` names the
   session in the desktop app, and `-n` names it in `claude agents` and `/resume`. Then run:

   ```
   tmux new-session -d -s <tmux> -c <dir> -e PATH=<PATH> [-e MY_MACHINE=<m>] <claude abs path> <args...> \;
        set-option @claude_name <title> \; set-option @claude_dir <dir> \; set-option @claude_uuid <uuid> \;
        set-option @tn_context <display name or ""> \; set-option @tn_kind claude
   ```

   `PATH` and `MY_MACHINE` are passed with `-e`, because a running tmux server gives new sessions
   its own environment. The options are chained into the same tmux call, so they land even if
   Claude dies at once.
9. Wait 2 seconds. If the tmux session is gone, exit 1
   `claude exited straight away; run it by hand to see why:` with `  run: cd <dir> && claude <args>`.
10. Print to stderr `Directory / Name / Tmux / Session` lines and
    `attach: tn claude attach <tmux>`. Print the tmux name on stdout.

JSON: `{"tmux", "name", "uuid", "dir", "context", "resumed": bool, "trusted": bool, "workspace_created": "src-03" | null}`.

**`tn claude ls`** lists the tmux sessions with a non-empty `@claude_name`, joined on the uuid to
`claude agents --json` (`sessionId` gives `status`). No tmux server means an empty list.

| column | key |
|---|---|
| TMUX | `tmux` |
| NAME | `name` |
| CONTEXT | `context` |
| STATUS | `status` (`idle` / `busy` / … or null) |
| AGE | `age_seconds` (from `session_created`) |
| ATTACHED | `attached` (bool) |
| DIRECTORY | `dir` (text: `~`-shortened) |
| — | `uuid`, `started` |

The empty message is `No Claude sessions in tmux. Start one with: tn claude start [target]`.

**`tn claude attach [name]`** matches `name` against `tmux`, `name`, `context` and the `uuid`
prefix; with no name, it picks. Inside tmux (`$TMUX` set), it runs `tmux switch-client -t =<tmux>`;
otherwise it hands off to `tmux attach-session -t =<tmux>`. Detaching (`C-a d`) leaves the session
running. With no sessions: stderr message, exit 1.

**`tn claude stop [name | --all]`** kills the tmux session(s) with `kill-session -t =<tmux>`. The
conversation is kept. With no name it picks; `--all` confirms. For each session it prints
`resume: tn claude start <dir> --resume <uuid>`.

JSON: `[{"tmux", "name", "uuid", "dir", "resume": "tn claude start <dir> --resume <uuid>"}]`.

**`tn claude restart [name]`** is `stop` then `start --resume` for one session: it matches `name`
as `attach` does (no name picks; exit 2 with `choices` off a TTY), kills the tmux session, waits up
to 5 seconds for its claude to exit (two processes on one transcript corrupt it), then starts the
same conversation (`--resume <uuid>`) in the same directory under the **same tmux name and
title**, so a custom `--name` survives. It is not the way to move a session between machines or
to start one that is not running (`tn claude start --resume` does that). If the start fails, the
session stays stopped and the `resume:` line is printed. A session with no recorded uuid or
directory exits 1. `--dry-run` changes nothing. JSON: the `start` result.

**`tn claude resume [name | --all]`** brings back sessions that died, under their old tmux name
and title (`start --resume <uuid>`; a live one on the previous account goes through `restart`).
Unix only: on Windows exit 1 with `run: tn claude attach <name>`. Each registry entry gets a
state, checked in this order:

1. `running`: a tmux session of that name has its uuid; `account` instead when the entry's
   account and the current login are both known and differ.
2. `missing`: the directory or the transcript `<uuid>.jsonl` is gone.
3. `outside`: `claude agents --json` shows the uuid with a live pid.
4. `stopped`: the entry has `stopped`.
5. `account`: as in 1, with no tmux session.
6. `rebooted`: the boot time (`/proc/stat` `btime`, else `sysctl -n kern.boottime`) is after
   `created`, and the transcript either ends abruptly or was last written no more than 600
   seconds before the boot (a claude may exit cleanly on the shutdown's SIGTERM).
7. `exited` when a `cost-state` row follows the last `user`/`assistant` row (Claude writes it
   as it exits: `/exit`, an archive in the app, `tn claude stop`'s SIGHUP), else `crashed`.

`--all` wakes every `crashed`, `rebooted` and `account` entry and prints `left alone: <n>
sessions stopped or exited on purpose ...` when there are any; with nothing to wake it prints
`No Claude session to resume.` and `[]`. No name and no `--all` picks among those (exit 2 with
`choices` off a TTY). A name matches as `attach` does, over the registry, and may resume a
`stopped` or `exited` entry too; `running` exits 1 with `run: tn claude attach <tmux>`,
`outside` and `missing` exit 1. Before starting anything, a known logged-out status exits 3 with
`run: tn claude login`. With `--all` one failure does not stop the rest; the exit is 1 if any
failed. `--dry-run` changes nothing.

JSON: `[{"tmux", "name", "uuid", "dir", "context", "state", "resumed": bool, "error": str | null}]`.

**`tn claude login [--console] [--sso] [--email ADDR]`**

1. `need("claude", ...)`.
2. Read `claude auth status --json`. Use the `loggedIn` field, never the exit code (it is 0 either
   way). Print `currently: <email> via <authMethod> (<subscriptionType>)` or `not signed in`.
3. When signed in, confirm `sign in again, replacing this?`. A no keeps the login and exits 0.
4. Hand off to `claude auth login` with the given flags. A `-- <args>` tail is also passed.
5. After it returns, print `now: ...`.

`--json` gives the status only, without logging in:
`{"logged_in": bool, "email", "auth_method", "subscription"}`.

**Hooks**

* sessions: one `Session(kind="claude", id=<tmux>, name, context, dir, started, attached, status,
  attach=["tmux", "attach-session"|"switch-client", "-t", "=<tmux>"], extra={"uuid"})` per row of
  `ls`.
* status: `<n> sessions (<a> attached)` and, when one runs for the Context's path,
  `; here: <tmux> <status>`.
* checks:
  * `claude installed` (fix `dot apply claude`);
  * `tmux installed` (fix `dot apply tmux`, Unix only);
  * `logged in` (fix `tn claude login`);
  * `MY_MACHINE set` (fix `tn config set machine <name>`).

### 7.3 codex

```python
plugin = Plugin("codex", help="the shared Codex daemon and its sessions", requires=["projects"])
```

Bundle `codex`: `requires: [common, tn, projects]`. The verbs match claude, but their meaning
follows how Codex works. Codex runs **one shared app-server daemon** that hosts every session.
Remote Control belongs to the daemon, and Codex has no machine-readable session list. So there is
no per-directory session to name.

**`tn codex start [target] [--ws NN|new]`**

1. `need("codex", fix="dot apply codex")`.
2. `codex login status`. Match the text: when the output contains `ot logged in`, exit 3 with
   `run: tn codex login`. The exit code is 0 either way. Capture the output; never pipe it into
   `grep -q`.
3. Resolve the target as claude does, including the git root.
4. `codex remote-control start`. Starting a running daemon is a no-op.
5. `codex remote-control pair`, printing its pairing code under
   `pairing code (only needed to link a new device):`.
6. Hint: `open a session there: codex -C <dir>`.

JSON: `{"dir", "context", "daemon": "running", "pairing": "<text printed by pair>"}`.

**`tn codex ls`** reports the daemon, and never opens Codex's full-screen browser:

* `codex app-server daemon version`. A failure means `running: false`.
* Otherwise parse its JSON (`status`, `cliVersion`, `appServerVersion`).

JSON (an array, so `ls` stays an array):
`[{"id": "daemon", "running": bool, "status", "cli_version", "app_server_version", "logged_in": bool}]`.
Text: one row with DAEMON, STATUS, VERSION and LOGIN, then the hint
`browse sessions: codex agents   resume one: tn codex attach [name]`.

**`tn codex attach [name]`** hands off to `codex resume <name>` (a name or uuid). With no name, it
hands off to `codex resume --all`: Codex's own picker, across every directory. That still counts as
a prompt, so without a TTY it exits 2.

**`tn codex stop`** takes no name, because it is daemon-wide. If the daemon is not running, print
`not running` and exit 0. Otherwise confirm
`this stops the shared daemon, ending remote control for every Codex session on this machine; conversations are kept. Stop it?`,
then run `codex remote-control stop`.

JSON: `{"stopped": bool}`.

**`tn codex login [--device-auth | --with-api-key | --with-access-token]`**

1. Print the current state (the first line of `codex login status`).
2. When signed in, confirm replacing it.
3. With no flag, choose the flow:
   * **Browser flow**: when not over ssh (`SSH_CONNECTION` unset) and either on macOS or Windows,
     or on Linux with `DISPLAY` or `WAYLAND_DISPLAY` set. Also print
     `not at this machine? Ctrl-C and run: tn codex login --device-auth`.
   * **`--device-auth`** otherwise.
4. `--with-api-key` and `--with-access-token` read stdin (`printenv OPENAI_API_KEY | tn codex login --with-api-key`).
5. Hand off to `codex login <flags>`, then print `now: ...`.

JSON: status only, `{"logged_in": bool, "status": "<first line>"}`.

**Hooks**

* sessions: when the daemon runs, one
  `Session(kind="codex", id="daemon", name="codex daemon", context=None, dir=None, started=None,
  attached=None, status=<status>, attach=["codex", "resume", "--all"])`. If Codex ever ships a JSON
  session listing, per-session rows replace this one.
* status: `daemon running` / `daemon stopped`.
* checks: `codex installed` (fix `dot apply codex`); `logged in` (fix `tn codex login`).

### 7.4 vscode (`tunnel`)

```python
plugin = Plugin("vscode", help="port forwards through VS Code dev tunnels", groups=["tunnel"])
```

Bundle `vscode`: `requires: [common, tn]`. It wraps `devtunnel`, the same service as VS Code's
PORTS panel. The `code` CLI cannot forward a port. These are **temporary** tunnels: created by
`devtunnel host`, and deleted when that process ends. So `devtunnel list` shows nothing, and tn's
state files are the truth. The state lives in `$TN_STATE_DIR/tunnels/`:

* `<port>.json`:
  `{"port", "pid", "url", "access": "private"|"public", "started", "expires": null | "<iso>", "label", "context", "dir", "log"}`;
* `<port>.log`: devtunnel's output, kept after close as the record of why a tunnel ended.

A tunnel is **live** when its pid is alive. Stale entries are pruned (json removed, log kept)
whenever state is read.

**`tn tunnel open [port...] [--public] [--for DURATION]`**

1. `need("devtunnel", fix="dot apply vscode")`.
2. Login check: `devtunnel user show` exits 0 either way, so a login is missing when its output
   contains `not logged in` (case-insensitive). Then exit 3 with
   `run: devtunnel user login -g   (add -d on a machine without a browser)`.
3. The ports come from the arguments, else the project's `[tunnel].ports`, else exit 2
   `no port given and no [tunnel] ports in <project>/tn.toml`. Each port must be an integer from
   1 to 65535.
4. For each port:
   * **Already live**: print the recorded URL and exit 0 for that port (`reused: true`). With
     `--for`, set the new `expires` and start a new expiry watcher.
   * Otherwise, if nothing accepts a TCP connection on `127.0.0.1:<port>` (checked with `socket`,
     so it is portable), warn: `nothing is listening on <port> yet - the link will 502 until something starts there`.
     This is a warning, not a failure.
   * Otherwise start `devtunnel host -p <port> [--allow-anonymous]` with `spawn_detached`, logging
     to `<port>.log`, and write the state.
5. Wait up to 45 s. Poll the log once a second for
   `https://[a-z0-9]+-<port>\.[a-z0-9-]+\.devtunnels\.ms`. The anchor is `-<port>.`, which excludes
   the `-<port>-inspect.` URL.
   * If the process exits first, print the log indented on stderr, remove the state, and fail.
   * On timeout: `gave up after 45s; still running: see <log>, or tn tunnel close <port>` (exit 1).
6. Record the URL. Print it on stdout, and the access line on stderr:
   * `private: opening it asks for the account that started it`, or
   * `public: anyone with this link reaches port N on this machine`.

   `--public` is per forward and never remembered. A private link cannot be curl'ed; for API
   clients, use `devtunnel token <id> --scopes connect` with the header
   `X-Tunnel-Authorization: tunnel <token>`.
7. `--for DURATION` accepts `90s`, `30m`, `2h`, `1d`, and combinations like `1h30m`; anything else
   is exit 2. It records `expires` and starts a watcher with `spawn_detached`:
   `<tn> tunnel close <port> --when-expired`. The watcher sleeps until `expires` and then closes the
   tunnel only if the state's pid and expiry are still the ones it was started for. `tn tunnel ls`
   and `tn status` also close any live tunnel past its expiry, in case the watcher died.

Exit: 1 if any port failed; the others still open.

JSON: `[{"port", "url", "access", "pid", "started", "expires", "label", "context", "reused": bool}]`.

**`tn tunnel ls`**

| column | key |
|---|---|
| PORT | `port` |
| ACCESS | `access` |
| AGE | `age_seconds` |
| EXPIRES | `expires` (text: `in 1h12m` or `-`) |
| LABEL | `label` (`ctx.tunnel_label(port)` at open time) |
| CONTEXT | `context` |
| LINK | `url` |
| — | `pid`, `started`, `dir` |

The empty message is `No tunnels. Open one with: tn tunnel open <port>`.

**`tn tunnel close [port... | --all] [--when-expired]`**

* With no port and no `--all`: pick.
* For each tunnel: SIGTERM (Windows: `os.kill` with `SIGTERM`, which terminates). Poll for up to
  10 s, then SIGKILL. Remove the json; keep the log.
* A port that is not open exits 1 `port N is not forwarded`.
* `--all` with nothing open prints `No tunnels to close` and exits 0.
* `--all` does not confirm, because only links are lost. It does print
  `the link is gone for good: a new open gets a new URL`.
* `--when-expired` is internal (step 7 above) and hidden from help.

JSON: `[{"port", "url", "closed": true}]`.

**Hooks**

* status: `<n> open: <port> <url> (<access>, <age>)[; ...]`;
* checks: `devtunnel installed` (fix `dot apply vscode`); `devtunnel logged in` (fix
  `devtunnel user login -g`). This login is separate from `code tunnel user login`, so say so in the
  detail;
* completer `tunnel`.

### 7.5 git

```python
plugin = Plugin("git", help="git helpers: remotes, identity, sync, export", requires=["projects"])
```

Bundle `git`: `requires: [common, tn, projects]`. It copies the public
`conf.d/git-forges.toml` (`[forges.*]` for github.com, gitlab.com, bitbucket). Your own
namespaces, a self-hosted forge and `[people.*]` identities go in a private
`conf.d/*-private.toml` you write by hand (shape: `bundles/git/private.toml.example`). Every command needs a git repo (`ctx.git_root`),
except `ignore --list` and `as --list`. Outside a repo it exits 2 `not inside a git repository`.

"The branch" means the current branch. Detached HEAD exits 1 for `pull`, `sync` and `feature new`.
"Remotes" means `git remote`, excluding one named `local`, as the old `_git-remotes.sh` did.

**`tn git pull [--remote R | --all]`**

* Default: `git pull` (the branch's upstream). With no upstream, exit 1 with
  `hint: tn git pull --remote <name>` and the list of remotes.
* `--remote R`: `git pull R <branch>`.
* `--all`: that, for each remote in order. It carries on past a failure and exits 1 if any failed.

JSON: `[{"remote", "branch", "ok": bool}]`.

**`tn git sync [--remote R]`** pulls from each target remote (default: all remotes; with
`--remote`, that one), then pushes to each: `git push <remote> <branch>`. Pushing is skipped for any
remote whose pull failed. JSON as for pull, plus `"pushed": bool`.

**`tn git remote add <forge> [--name NAME] [--path PATH] [--no-fetch]`**

1. The forge must exist in config (exit 2 with the choices).
2. `path` is the forge's `path` template with `{project}` and `{repo}` from the Context,
   `{group}` = the project's `group`, else the forge's `owner`, else the project, and `{owner}` =
   the forge's `owner`. Outside a project, `--path` is required (exit 2).
3. The URL is `ssh_url` (or `https_url` when the forge's `clone = "https"`).
4. The remote name is `--name`, else the forge's `remote`, else the forge key. If that name exists
   with another URL, exit 1; with the same URL, succeed with no change.
5. `git remote add <name> <url>`. Unless `--no-fetch`, run `git fetch <name>`. A failed fetch is a
   warning, because the remote repository may not exist yet:
   `create it: <web>/<path> (gh repo create <path> / glab repo create <path>)`.

JSON: `{"name", "url", "forge", "path", "fetched": bool}`.

**`tn git remote ls`** lists `{name, url, forge, path, web}` for each remote. `forge` and `path` are
null for a host that matches no forge.

**`tn git open [repo|pr|ci|issues] [--remote R] [--print]`**

1. The remote is `--remote`, else the upstream's, else `origin`, else the first. Its host is
   matched to a forge by `forge_for_url`; with no match, exit 1 `no forge in config for host <h>`.
2. The page URL is `web` + `/<path>` + a suffix:

   | page | github | gitlab | bitbucket |
   |---|---|---|---|
   | repo (default) | — | — | — |
   | pr | `/pulls` | `/-/merge_requests` | `/pull-requests` |
   | ci | `/actions` | `/-/pipelines` | `/pipelines` |
   | issues | `/issues` | `/-/issues` | `/issues` |

3. `webbrowser.open(url)`. With `--print`, no display (Linux without `DISPLAY` or
   `WAYLAND_DISPLAY`), or over ssh, print the URL instead. The URL always goes to stdout.

JSON: `{"url", "remote", "forge"}`.

**`tn git as <person> [--list]`**

* Match `person` case-insensitively against the people keys, aliases, names and email local parts.
  An exact key or alias wins; otherwise the best of prefix, then substring, then subsequence.
* Several at the best score: pick, or exit 2 with the choices.
* `me` is the `MY_NAME` / `MY_EMAIL` identity (§4.3); without one, exit 3
  `run: set MY_NAME/MY_EMAIL (dot apply asks for them once; ~/.config/dot/local.env)`.
* Set `git config user.name` and `user.email` locally, and print `committer: Name <email>`.
* `--list` prints the people table: `KEY NAME EMAIL`, JSON
  `[{"key", "name", "email", "aliases"}]`.

JSON: `{"key", "name", "email", "repo": "<git_root>"}`.

**`tn git whoami`** prints the effective identity: `git config user.name` / `user.email` with
`--show-origin`, giving the source `local`, `global` or `unset`. It also prints the project's
expected identity and whether the two match.

JSON: `{"name", "email", "source", "expected": {"key", "name", "email"} | null, "matches": bool | null}`.

**`tn git init [--forge F]`** is idempotent, and works in any directory (it needs no existing repo):

1. Without `.git`: `git init`, then set the identity (§7.1.4).
2. Without `.gitattributes`: write
   `* text=auto\n*.sh text eol=lf\n`. The old script wrote `.sh`, which matches nothing.
3. With `--forge`, add the remote as `remote add` does.

JSON: `{"path", "initialized": bool, "gitattributes": bool, "identity": {...} | null, "remote": {...} | null}`.

**`tn git ignore <template...> [--list]`** uses GitHub's official templates through the GitHub API.

1. `need("gh", fix="dot apply gh")`.
2. Get the names from `gh api gitignore/templates` (a JSON array). Match each argument to one name,
   case-insensitively; common short forms map to their template (`node` to `Node`, `python` to
   `Python`, `go` to `Go`). An unknown name exits 2 with close matches.
3. For each template, `gh api gitignore/templates/<Name>` gives `{"name", "source"}`.
4. Append to `.gitignore` in the git root (create it when missing) as a block
   `\n### <Name> (github/gitignore)\n<source>`. Skip a template whose header line is already
   present (`already there`).
5. A 401 from gh exits 3 `run: gh auth login`.
6. `--list` prints every template name.

JSON: `{"file", "added": ["Python"], "skipped": ["Node"]}`.

**`tn git log [RANGE] [--max-count N] [--author WHO]`** is a read-only compact log (default
`--max-count 20`; `--limit N` is an alias; N below 1 exits 2):
`git log --format=%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%D%x1f%s --max-count=N`. It has no `-n N`:
`-n` is the global `--dry-run` (§2.3), which core takes out before the plugin sees its
arguments, so `tn git log -n 5` would read `5` as RANGE.

| column | key |
|---|---|
| COMMIT | `short` |
| DATE | `date` |
| AUTHOR | `author_name` |
| SUBJECT | `subject` |
| — | `hash`, `author_email`, `refs` (list) |

The old `git-log.sh` did not list anything: it rewrote one commit's author with
`git filter-branch`. That is dropped (§8).

**`tn git changed`** parses `git status --porcelain=v2 -z`.

Rows: `{"path", "status": "modified"|"added"|"deleted"|"renamed"|"copied"|"untracked"|"conflicted"|"type-changed", "staged": bool, "unstaged": bool, "orig_path": null | "..."}`.
Text: STATUS, STAGED, PATH.

**`tn git authors`** runs `git shortlog -sne HEAD`.

Rows: `{"name", "email", "commits", "person": "<people key>" | null}`. Text: COMMITS, NAME, EMAIL,
PERSON.

**`tn git export [REF] [-o FILE]`**

1. `REF` defaults to `HEAD`.
2. The output defaults to `<project_dir>/rel/<project>-<repo>-<YYYYMMDD>.zip` (local date). Outside
   a project repo, `-o` is required (exit 2).
3. If the file exists, confirm overwriting it.
4. Create the directory, then `git archive --format=zip -o <file> <REF>` (with `-C <git_root>`).
5. The path goes to stdout.

JSON: `{"file", "ref", "commit": "<hash>", "bytes"}`.

**`tn git feature new <name> [--from BRANCH]`**: branch `feature/<name>` from `--from`, else
`develop` if it exists locally or on the primary remote, else the default branch. Then
`git switch -c feature/<name> <base>`. git-flow is not needed.

JSON: `{"branch", "base"}`.

**`tn git feature ls`** lists local and remote-tracking `feature/*` branches:
`{"name", "branch", "local": bool, "remote": "<remote>" | null, "ahead", "behind", "last_commit_date"}`.
The comparison is against the base (§above).

**Hooks**

* status: `<branch>, <n> changed, ahead <a>, behind <b>` for the Context's repo.
* checks:
  * `git installed` (fix `dot apply git`);
  * for each forge whose `cli` is installed: `gh auth status --hostname <host>` or
    `glab auth status --hostname <host>` succeeds (warn; fix `gh auth login --hostname <host>` or
    `glab auth login --hostname <host> --web`);
  * identity: for every project with an `identity`, every repo in its workspaces whose local
    `user.email` (read from `.git/config` directly, without a subprocess) differs is a `warn` row.
    The fix is `tn -C <repo> git as <key>`.
* completers `person`, `forge`.

### 7.6 tmux

```python
plugin = Plugin("tmux", help="plain tmux sessions")
```

Bundle `tmux`: `requires: [common, tn]`. Unix only (see §7.2 for the Windows exit). The prefix is
`C-a`, and `C-a d` detaches.

* **`tn tmux new [name] [-c DIR] [-d]`**
  * The name defaults to `ctx.slug`; the directory defaults to `ctx.path`.
  * If the session exists, attach to it instead.
  * Otherwise `tmux new-session -s <name> -c <dir>`, which attaches (handoff). With `-d` it is
    created detached, and the name goes to stdout.
  * Inside tmux, a new session is created detached and then `switch-client` is used.
  * JSON only with `-d`: `{"name", "dir", "created": bool}`.
* **`tn tmux attach [name]`**: pick among all sessions when no name is given. Then `switch-client`
  inside tmux, else hand off to `attach-session -t =<name>`.
* **`tn tmux kill [name | --all]`**: `kill-session -t =<name>`. The name must match exactly (no
  prefix or substring matching); otherwise exit 2 with the near misses as `choices`, killing
  nothing. With no name, pick; a lone session is confirmed rather than auto-picked. `--all` confirms
  and kills every session, agent sessions included (it replaces `tm-kill-all.sh`); the confirmation
  says how many are Claude sessions.
  JSON: `[{"name", "killed": true}]`.
* **`tn tmux ls`**: from
  `tmux list-sessions -F '#{session_name}\t#{session_windows}\t#{session_attached}\t#{session_created}\t#{@tn_kind}\t#{@claude_name}'`.
  Rows: `{"name", "windows", "attached", "started", "age_seconds", "kind": "claude"|"codex"|null}`.
  No server means an empty list.
* **Hooks**: status `<n> sessions`; check `tmux installed` (fix `dot apply tmux`); completer
  `session` for tmux names.

### 7.7 python

```python
plugin = Plugin("python", help="Python checks (uv)")
```

Bundle `python`: `requires: [common, tn]`. No commands: its group is the default (`python`),
which only labels the doctor row.

**Hooks**: check `uv installed` (warn, fix `dot apply python`; core covers `python 3.11+`). No
status.

`tn dj` (Django `manage.py`, `reset-password`) and `tn py serve` were removed as outdated, along
with the optional `local_db_password` secret: the bundle deletes
`~/.config/tn/secrets/local_db_password` (`absent`) where an earlier version wrote it.

## 8. Old scripts to new commands

There are **no aliases** for old names. The Claude skills move to `tn ... --json` in the same
change that deletes the `scripts` bundle.

| old | new |
|---|---|
| `_proj.py`, `_repo.py`, `_proj_dir.py`, `_repo_dir.py` | Context (§3); `tn status --json` gives `.context` |
| `_session_name.py` | `ctx.label()`, `ctx.session()` (§3.3) |
| `_machine.sh` | `tn config get machine` / `tn config set machine <name>` |
| `_claude_sessions.py`, `_claude_trust.py` | inside the claude plugin (ls, sessions hook; start's trust step) |
| `_os.sh`, `_ts.sh`, `_git-branch.sh`, `_git-remotes.sh`, `_dir-search-by-file.sh`, `_npm_dir.sh` | internal helpers of the plugins that need them |
| `proj-init.sh <name>` | `tn proj new <name>`; `tn proj ls` and `tn proj show` are new |
| `repo-init.sh <name>` | `tn repo new <name>` |
| `repo-clone.sh <src> [name]` | `tn repo clone <forge>:<path> [name]` (sets the project identity) |
| `repo-stats.sh` | `tn repo show` (and `tn repo ls` for every repo) |
| `repo-scan.sh <pattern>` | dropped: `git ls-files '*<pattern>*'` |
| `src-new.sh [NN]` | `tn ws new [NN]`; `tn ws ls` and `tn ws rm NN` are new |
| `claude-start [--no-trust] [--resume[=ID]] [dir] [name]` | `tn claude start [target] [--resume [ID]] [--ws NN\|new] [--name N] [--no-trust]` |
| `claude-list` / `-attach` / `-stop` / `-login` | `tn claude ls` / `attach [name]` / `stop [name\|--all]` / `login` |
| `codex-start` / `-list` / `-attach` / `-stop` / `-login` | `tn codex start` / `ls` / `attach [name]` / `stop` / `login` |
| `port-forward <port> [--public]` | `tn tunnel open [port...] [--public] [--for 2h]` |
| `port-list`, `port-stop [port\|--all]` | `tn tunnel ls`, `tn tunnel close [port...\|--all]` |
| `git-pull.sh [R]`, `git-pull-{github,gitlab,work,bitbucket,partner}.sh` | `tn git pull [--remote R \| --all]` |
| `git-sync.sh [R]`, `git-sync-*.sh` | `tn git sync [--remote R]` |
| `git-remote-{work,bitbucket,github,gitlab}.sh` | `tn git remote add <forge>` |
| `git-web-{bitbucket,github,gitlab}.sh` | `tn git open [pr\|ci\|issues]` |
| `git-<person>.sh` (about 40), `git-alex-personal.sh` | `tn git as <person>` (people in the private `conf.d/git-private.toml`) |
| `git-me.sh` | `tn git as me`; `tn git whoami` is new |
| `git-init.sh`, `git-attributes.sh` | `tn git init` |
| `git-ignore.sh` | `tn git ignore <template...>` (GitHub's official templates) |
| `git-modified.sh`, `git-commiters.sh`, `git-export.sh` | `tn git changed`, `tn git authors`, `tn git export [ref] [-o x.zip]` |
| `git-feature-start.sh`, `git-features.sh` | `tn git feature new <name>`, `tn git feature ls` (no git-flow) |
| `git-log.sh` (rewrote one commit's author with filter-branch) | dropped; `tn git log` is a plain log. To fix an author: `git rebase -i` and `git commit --amend --reset-author` |
| `mux-new`, `mux-kill` (zsh functions), `tm-kill-all.sh` | `tn tmux new [name]`, `tn tmux kill [name\|--all]`, `tn tmux attach`, `tn tmux ls` |
| `shell-reload.sh` | the `reload` zsh function (zsh bundle) |

**Dropped with no replacement:**

* `kitty-theme.sh` and its six theme wrappers: the kitty bundle is dropped;
* `mysql-*` (9), `psql-*` (8), `mongo-*` (2), `redis-run.sh`, `s3-*` (5): database and AWS helpers
  are not carried over;
* `ux-avatar-male.sh`, `ux-avatar-female.sh`: they fetch from a dead S3 bucket;
* `mail-git-request.sh`, `mail-proj-request.sh`, `mail-team.sh`: they built mailto links;
* `npm-install.sh`, `npm-install-dev.sh`, `npm-list.sh`: npm already finds the nearest
  `package.json`;
* `tar-dir.sh`, `untar-dir.sh`: tar ships with macOS, Linux and Windows 10+;
* `dj.sh`, `_dj_dir.sh`, `_db_password.sh` and every `dj-*.sh` (`dj-run`, `-console`, `-migrate`, `-test`, `-startapp`,
  `-pwd-reset`, `-migrate-gen`, `-syncdb`, `-startproject`), `py-http.sh`: outdated, not
  replaced. They briefly became `tn dj` and `tn py serve`, which were removed in turn; run
  `python manage.py ...` and `python3 -m http.server --bind 127.0.0.1` directly;
* `py-mail.sh`: it used `smtpd`, which Python 3.12 removed.

Build-time helpers (`jetbrains-closed.sh`) stay inside their bundles and never
go on PATH.

**The skills** call tn and read its JSON. They never parse text:

| skill | calls |
|---|---|
| project-new | `tn proj new`, `tn repo new --json`, `tn git whoami --json`, `tn git remote add` |
| project-clone | `tn repo clone --json` (after asking forge and account; `gh repo list` / `glab repo list` for browsing) |
| project-parallel | `tn ws new --json`, then `tn claude start <target> --json` (or `tn claude start --ws new` in one step) |
| claude-remote | `tn claude start [target] --json` (a missing target gives exit 2 with `choices`), `tn claude ls --json`, `tn claude stop <name> --json` |
| claude-resume | `tn claude resume [name | --all] --json`; `tn claude ls --json`; for sessions tn never recorded, transcripts under `~/.claude/projects/` and `tn claude start <dir> --resume <uuid> --json` |
| port-forward | `tn tunnel open <port> [--public] [--for D] --json`, `tn tunnel ls --json`, `tn tunnel close <port>` |

---

## 9. Testing

### 9.1 Layout and runner

```
bundles/tn/lib/tn/...            core
bundles/tn/tests/test_*.py       core tests
bundles/<b>/plugin.py            a plugin
bundles/<b>/tests/test_*.py      that plugin's tests (never copied to a machine: no bundle step names tests/)
test/tn-tests.sh                 runs them all
```

`test/tn-tests.sh [bundle...]`:

1. Makes a temp directory and fills `plugins/` with a **copy** of each `bundles/<b>/plugin.py` as
   `<b with - as _>.py`. Package plugins are copied as directories. Copies, not links, because
   that is what a machine gets.
2. For core and then for each bundle with a `tests/` directory (or those named), runs
   `python3 -m unittest discover -s bundles/<b>/tests -t bundles/<b>/tests` with
   `PYTHONPATH=bundles/tn/lib` and `TN_PLUGIN_PATH=<tmp>/plugins`. The core suite gets an empty
   plugin directory instead: it tests discovery, clashes and missing groups with its own demo
   plugins, which the repository's real plugins would disturb.
3. Lints, failing the run on any of these:
   * every plugin indexes with literal `Plugin(...)` arguments;
   * no two plugins in the repo claim a group;
   * each plugin's `requires` is a subset of its `bundle.yml` `requires` (a simple line parse of
     the `requires:` list);
   * every bundle with a `plugin.py` has a `copy` step to `~/.local/share/tn/plugins/<b>.py`;
   * every plugin byte-compiles under the oldest Python found (`python3.11` when on PATH), which
     catches syntax from 3.12 and later.
4. Uses `python3.11` when it is on PATH, else `python3`, printing which. Exits non-zero on any
   failure.

Tests never touch the real `$HOME`, never run real installers, tmux servers, VPNs, VMs or
devtunnel, and never use the network. They use real `git` in temp directories; a test that needs
it is skipped when git is absent. Whole-machine checks remain `test/sandbox.sh` and
`test/converge.sh`. After a converge run, `tn plugins --json` in the sandbox home must list exactly
the plugins of the applied bundles.

### 9.2 `tn.testing`

`tn.testing` ships in the core library and is importable from every test.

```python
from tn.testing import TnTestCase

class ClaudeStart(TnTestCase):
    def test_names_session_after_workspace(self):
        repo = self.make_project("acme", repos=["shop-app"], workspaces=["src-02"])
        self.fake("tmux", script=TMUX_FAKE)             # or stdout=/exit=
        self.fake("claude", stdout="[]")
        r = self.tn("claude", "start", "--json", cwd=repo.ws("src-02") / "shop-app")
        self.assertEqual(r.code, 0, r.stderr)
        self.assertEqual(r.json["tmux"], "claude-acme-shop-app-02")
        self.assertIn(["new-session", "-d", "-s", "claude-acme-shop-app-02"], [c[:5] for c in self.calls("tmux")])
```

| helper | does |
|---|---|
| `TnTestCase.setUp` | creates a temp dir holding `home/`, `bin/` and `state/`. Sets `HOME`, `USERPROFILE`, `XDG_CONFIG_HOME`, `XDG_STATE_HOME`, `XDG_CACHE_HOME`, `TN_HOME`, `TN_CONFIG_DIR`, `TN_STATE_DIR` under it; `MYPROJECTS_DIR=<home>/myprojects`, `MY_MACHINE=T1`, `MY_NAME`, `MY_EMAIL`, `NO_COLOR=1`. Sets `PATH=<tmp>/bin` plus the directories of `git` and the running Python only. Unsets `TN_CD_FILE`, `TMUX`, `SSH_CONNECTION`, `DISPLAY`, `GH_TOKEN`, `GITHUB_TOKEN`. Keeps `TN_PLUGIN_PATH` from the runner. Everything is restored in `tearDown`. |
| `self.home`, `self.tmp` | `Path`s |
| `self.fake(name, *, stdout="", stderr="", exit=0, script=None)` | writes an executable `bin/<name>`: a Python script with shebang `sys.executable` (plus a `.cmd` shim on Windows). It appends `{"argv": [...], "cwd": ..., "stdin": ...}` as a JSON line to `<tmp>/calls/<name>.jsonl`, then either prints the canned output and exits, or runs `script`: Python source with `argv`, `stdin`, `state_dir` and `log` in scope, for stateful fakes like tmux. |
| `self.calls(name) -> list[list[str]]` | argv lists (without the program) in call order; `self.call_records(name)` gives the full dicts |
| `self.config(text)`, `self.conf_d(name, text)`, `self.project_toml(project, text)` | write config files |
| `self.make_project(name, *, root="projects", repos=(), workspaces=(), remotes=None, toml=None) -> ProjectPaths` | creates the dirs, and `git init` plus one commit in each repo with the test identity; `remotes` maps a repo to `{name: url}`. `ProjectPaths` has `.dir`, `.ws(name)`, `.repo(name, ws="src")`. |
| `self.tn(*argv, cwd=None, stdin=None, tty=False, env=None) -> Result` | runs `tn.cli.main(list(argv))` **in process**, with `sys.stdin`, `sys.stdout` and `sys.stderr` swapped for StringIO and the cwd changed and restored. `tty=True` makes `tn.term.is_tty()` true for stdin and stderr, and the picker then reads `stdin`. `handoff` is intercepted: it records the argv in `Result.handoff` and returns the configured code instead of exec'ing. |
| `self.tn_proc(*argv, ...) -> Result` | the same, through `bundles/tn/bin/tn` as a subprocess, for the entry point and version gate |
| `Result` | `code`, `stdout`, `stderr`, `json` (parsed stdout, or None), `error` (parsed JSON error line from stderr, or None), `handoff` (argv or None), `cd` (the path written to `TN_CD_FILE`, which the helper always sets to a temp file) |
| `self.assertExit(result, code)` | asserts, printing stdout and stderr on failure |
| `self.freeze_time(ts)` | patches `tn.clock.now()`, which every age and expiry computation must use |

Core must be written so this works: time through `tn.clock`, TTY checks through `tn.term`, process
start through `tn.proc`, and no import-time reads of the environment.

Every command in §7 needs at least these tests: the happy path with `--json`; the usage error
(exit 2) and a missing prerequisite (exit 3 with its `run:` line); `--dry-run` making no change (no
mutating fake calls, no files); and the no-TTY rule for any picker or confirmation.

---

## 10. Implementation notes and open points

* **Order of work** (blueprint):
  1. core (entry, loader, context, config, output, exit codes, status, doctor, plugins, shell init
     and completion) with its tests;
  2. projects (proj, repo, ws, cd);
  3. claude and codex, plus `tn sessions` and the skills rewrite;
  4. git, vscode, tmux, python;
  5. delete the `scripts` bundle (done: PORTING.md "tn rework").

  `tn status`, `tn doctor`, `tn cd` and `--ws new` come with core and projects. Tunnel lifetimes
  and identity checks may follow.
* **Bundle wiring.** Every bundle with a plugin adds `copy: { ~/.local/share/tn/plugins/<b>.py: plugin.py }`
  after its packages and before any setup step that calls tn. The `tn` bundle also links
  `bundles/tn/tn.zsh` to `~/.config/zsh/conf.d/tn.zsh`. `common` must provide Python 3.11+. On
  Windows, common's `path: { ~/.local/bin: { persist: user } }` also writes the folder into the
  user's `Path` (HKCU\Environment), so `tn.cmd` is found from cmd, PowerShell and Explorer.
* **dot copy pruning.** A file deleted from `lib/tn` stays on a machine until dot's `copy` prunes
  directory copies. That is harmless, because nothing imports it. The index ignores
  `lib/tn/plugins/` contents other than `__init__.py`.
* **Deviations from the blueprint table**, made so that this spec is self-consistent:
  * `tn git remote ls` is added;
    without applying;
  * `tn codex stop` takes no name, because the daemon is shared;
  * `tn tmux kill` keeps the blueprint's verb, and is listed in §2.2 as a sanctioned extra.
* **Codex sessions** are a single daemon row until Codex offers a machine-readable listing.
