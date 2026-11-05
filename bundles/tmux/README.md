# tmux

The terminal multiplexer, its one config file, and the `tn tmux` commands.

## Installs

`tmux`: apt on Linux, Homebrew on macOS (the distribution's build is fine; nothing here needs a
newer one). No Windows equivalent; the bundle is `os: [linux, macos]`.

## Links and copies

- `~/.tmux.conf` -> `tmux.conf` (linked: `C-a C-r` reloads the repo's file)
- `~/.local/share/tn/plugins/tmux.py` <- `plugin.py` (copied, as every tn plugin; `tests/` is
  never copied). The bundle `requires: [common, tn]` so `tn` itself is there.

## Commands (`tn tmux`, docs/tn.md §7.6)

They replace the `mux-new` / `mux-kill` zsh functions and `tm-kill-all.sh` of the old scripts.

| command | does |
|---|---|
| `tn tmux new [name] [-c DIR] [-d]` | creates a session and attaches. The name defaults to the context's slug (`acme-shop-web-02` in `~/myprojects/acme/src-02/shop-web`, the directory name outside the project trees), the directory to the context's path (the repo root, not the subdirectory you are in). An existing session of that name is attached instead. `-d` creates it detached and prints the name (`--json`: `{"name", "dir", "created"}`). Inside tmux it creates it detached and switches the client, since tmux refuses to nest. |
| `tn tmux attach [name]` | joins a session: exact name, else prefix, else part of the name (or of a Claude session's title); picks when no name or several match. Inside tmux it switches the client. |
| `tn tmux ls` | every session, agent sessions included: `NAME KIND WINDOWS ATTACHED AGE`; `KIND` is `claude` / `codex` for sessions the agent plugins started. `--json` rows: `{"name", "windows", "attached", "started", "age_seconds", "kind"}`. No tmux server is an empty list. |
| `tn tmux kill [name \| --all]` | `kill-session`. The name must be exact: no prefix or part-of-name matching, so a typo exits 2 and kills nothing (near misses are listed as choices). With no name it picks among several sessions, and asks before killing a lone one (`--yes` skips that). `--all` asks first (`--yes` skips it), naming how many are Claude or Codex sessions, and kills the session tn runs in last. `--json`: `[{"name", "killed": true}]`. |

Sessions are always addressed as `=<name>` (tmux's exact match), and `kill` takes only an exact
name, so killing `work` never kills `workshop` and `tn tmux kill foo` never kills `foobar`. Names cannot contain `.` or `:` (tmux rejects them). `tn status` shows
`tmux  <n> sessions; here: <name>` when a session carries this context's name, `tn doctor` checks
that tmux is installed, and the session name arguments complete in zsh/bash. `new` without `-d`
and `attach` take the terminal, so they refuse `--json`. On Windows (no tmux) every command exits
3 with `run: wsl, then tn tmux there`; the bundle itself is `os: [linux, macos]`.

Killing a Claude session with `tn tmux kill` keeps its conversation, but `tn claude stop` also
prints the `tn claude start <dir> --resume <uuid>` line to bring it back.

## Why it matters beyond the terminal

- The Claude session commands (`tn claude start`, the claude bundle's plugin) run each Claude
  session in a **detached tmux session** (`claude-<slug>`, tagged `@tn_kind` / `@claude_name` /
  `@claude_dir` / `@claude_uuid`), because `claude --bg` sessions went offline in the desktop app
  after a long idle. They refuse to run without tmux. `tn claude attach` (or `tn tmux attach`)
  opens one; detach with `C-a d`.
- The zsh bundle defines the old oh-my-zsh tmux aliases (`ta tl ts tkss`), which need tmux:
  another reason this bundle is selected wherever zsh is.

## Keys

The prefix is **`C-a`** (`C-a C-a` jumps to the last window, `C-a C-d` detaches, `C-a C-r`
reloads this file). After the prefix, the split keys are the ones every tool in
[docs/keymap.md](../../docs/keymap.md) shares:

| key | action |
|---|---|
| `\|`, `\`, `v` | split right (50%, same directory) |
| `-`, `_` | split down |
| `h j k l` | focus left / down / up / right |
| `H J K L` | resize by 10 cells (repeatable) |
| `Tab` | next pane |

tmux keeps `C-a` while ghostty uses `ctrl+space`: a terminal emulator consumes its own leader
before the byte reaches the PTY, so a tmux inside it would never see a shared one.

## Gotchas

- **The backslash binding must be quoted** (`bind-key '\' ...`). Unquoted, tmux swallows the
  following space and silently drops the binding.
- Resize amounts are **cells** here; ghostty's are pixels (see the keymap).
- Windows and panes are numbered from 1 (`base-index`, `pane-base-index`) to match the keyboard.

## Tests

`tests/` (never copied to a machine) runs the plugin against a stateful fake `tmux` on PATH
(`tests/_tmuxfake.py`), never a real tmux server: `test/tn-tests.sh tmux`.
