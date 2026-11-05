# claude

[Claude Code](https://claude.com/product/claude-code) (the terminal CLI, every profile), the
[Claude desktop app](https://claude.com/download) (desktops only), the skills in `skills/`, and
the `tn claude` commands (the tn plugin in `plugin.py`, copied to
`~/.local/share/tn/plugins/claude.py`; spec: [docs/tn.md §7.2](../../docs/tn.md#72-claude)).

## Installs

| | Linux | macOS | Windows |
|---|---|---|---|
| Claude Code | `claude.ai/install.sh` | same installer | `claude.ai/install.ps1` |
| Claude Desktop (desktops) | Anthropic's apt repository | cask `claude` | winget `Anthropic.Claude` |
| skills | `~/.claude/skills` -> `skills/` | same | same (a junction without Developer Mode) |
| `tn claude` | `plugin.py` copied into tn's plugins | same | sessions open in Windows Terminal tabs (no tmux) |

### Claude Code

The official installer puts everything under `$HOME`: `~/.local/share/claude/versions/` and a
`~/.local/bin/claude` link, which [common](../common/README.md) has on `PATH`. The step is skipped
while `claude` is on `PATH`; `dot apply --upgrade` runs `claude update` instead.

**It refuses to run under sudo**, and says so: with sudo it would install into root's home and the
`claude` command would not work from your own shell. So the step has no `sudo:`, and nothing here
may wrap it in sudo.

On Windows, Claude Code needs Git for Windows (Git Bash), which common and the git bundle install.

### Claude Desktop on Linux

Linux support is **beta**: Ubuntu 22.04+ / Debian 12+ on amd64 and arm64 only (the steps are
guarded with `arch: [x86_64, aarch64]`, so other CPUs skip rather than fail). Fedora, RHEL and
Arch are not supported; use the CLI there.

From the apt repository rather than a downloaded `.deb`, because **the app does not update itself
on Linux**: updates arrive only through apt (`dot apply --upgrade`, or `apt upgrade`).

The repository key is pinned to the fingerprint Anthropic publishes,
`31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE`: `package_repo` refuses a key that does not match
before anything is installed (a wrong key otherwise surfaces much later as an opaque
`NO_PUBKEY BAA929FF1A7ECACE` from `apt update`). The old installer's
`/etc/apt/sources.list.d/claude-desktop.list` and its keyring in `/usr/share/keyrings/` are
removed in favour of dot's deb822 `claude-desktop.sources`.

### Cowork needs KVM

Cowork runs its agentic tasks in a QEMU/KVM virtual machine, so it needs more than the package:

- hardware virtualization enabled in firmware;
- `qemu-system-x86`, `ovmf`, `virtiofsd`: recommended packages of `claude-desktop`, so absent if
  apt is configured with `--no-install-recommends`;
- membership of the **`kvm` group**, which the `user` step adds (dot prints a "log out and back in"
  notice). Join it even if `/dev/kvm` already works for you: Cowork also needs
  `/dev/vhost-vsock`, which only group members can open. Takes effect at the next login.

Not in the Linux beta: Computer Use, dictation, and the Quick Entry global hotkey on native
Wayland.

## Skills

`skills/` is linked to `~/.claude/skills`, so skills are tracked config like any other dotfile and
identical on every machine. **Only that subdirectory**: `~/.claude` itself holds runtime state
(sessions, projects, caches, credentials) that must never be linked into git. New or changed
skills load in a new session.

Claude's skill sync writes its runtime state into the linked directory as `skills/synced/`;
this bundle's `.gitignore` keeps it out of the repository.

| skill | what |
|---|---|
| `claude-remote` | start a Remote Control session on a project in tmux (`tn claude start`) |
| `claude-resume` | wake a stopped session, keeping its conversation |
| `port-forward` | expose a port through a VS Code dev tunnel |
| `project-clone` | clone GitHub / GitLab repositories into `~/myprojects` |
| `project-new` | create a project or a repository in `~/myprojects` |
| `session-clone` | clone the repository another Claude session (named by the user) works in and its related repositories, then start a session on it, on main / master |
| `project-parallel` | a parallel `src-NN` workspace of clean clones |

They drive `tn` with `--json` and never parse text: `tn claude start|ls|stop`, `tn proj`,
`tn repo`, `tn ws` (the projects bundle), `tn git` and `tn tunnel`. They follow the
project layout convention in the repository's CLAUDE.md. Session names use `$MY_MACHINE` (asked
once by `dot apply`, kept in `~/.config/dot/local.env`; `tn config set machine <name>`).

## `tn claude`: sessions in tmux, for Remote Control

    tn claude start [target] [--ws NN|new] [--resume [ID]] [--name NAME] [--no-trust]
    tn claude ls                      # TMUX NAME CONTEXT STATUS AGE ATTACHED DIRECTORY
    tn claude attach [name]           # join one in this terminal; detach with C-a d
    tn claude stop [name | --all]     # the conversation is kept; prints the resume line
    tn claude restart [name]          # stop, then resume the same conversation, same names
    tn claude resume [name | --all]   # wake sessions that died: crash, reboot, account switch
    tn claude login [--console] [--sso] [--email ADDR] [-- args]

`tn sessions` lists these next to Codex's; `tn status` shows the count and the session running
here; `tn doctor` checks claude, tmux, the login, the first-run setup and `MY_MACHINE`. They replace the old
`claude-start`, `claude-list`, `claude-attach`, `claude-stop` and `claude-login` scripts and their
helpers `_claude_sessions.py`, `_claude_trust.py` and `_session_name.py` (no aliases).

- **tmux, not `--bg`.** Each session is an ordinary interactive `claude` in a detached tmux
  session. A `--bg` session goes offline in the desktop app after a long idle stretch; one in
  tmux has a live terminal behind it and stays up until stopped. tmux comes from the tmux bundle,
  which this bundle does not require. Windows has none: there `start` opens the session in a
  new Windows Terminal tab (a `cmd` window without `wt`) and the tab is the session, so closing
  it ends it. tn keeps `~/.claude/tn-sessions.json` so `ls` still lists a closed session,
  `attach` reopens it with `--resume` (it cannot raise a tab that is still open), and `stop`
  ends the process and forgets it.
- **Target.** `start` takes what `tn cd` takes (`acme/shop-web`, `acme/shop-web@02`, a repo,
  `client/engagement`, `falcon` found through a remote, a directory), else the current
  directory. A project holding one repo resolves to it; a subdirectory runs at its git root.
  `--ws new` makes the next `src-NN` workspace first (`tn ws new`).
- **Names.** The title is `<Project> <Repo> #<Machine>-<Workspace>` (`Acme Shop Web #U1-02`),
  given both to `--remote-control` (the desktop app) and `-n` (`claude agents`, `/resume`). The
  tmux session is `claude-<project>-<repo>-<ws>` (`claude-acme-shop-web-02`). `--name` overrides
  both; there is no name prompt. Without `MY_MACHINE` it exits 3 rather than invent one.
- **The uuid is pinned** with `--session-id`, so the transcript
  (`~/.claude/projects/<dir with non-alphanumerics as ->/<uuid>.jsonl`) is known from the start.
  `--resume` alone takes the newest transcript there; `--resume <uuid>` needs the full uuid. It
  refuses a uuid already running in tmux, or one `claude agents --json` shows with a live pid
  outside tmux: two processes on one transcript corrupt it.
- **Resume: dead versus ended.** A reboot takes the tmux sessions and their options with it, so
  on every platform `start` records each session in `~/.claude/tn-sessions.json` with the
  account it runs on (`claude auth status` e-mail), `stop` marks it stopped, and `ls` adopts
  live sessions started before the registry existed (account unknown). `resume` sorts each
  entry by what it left behind:

  | state | evidence | `--all` |
  |---|---|---|
  | `running` | its tmux session is up, same account | - |
  | `account` | recorded account differs from the current login (tmux up: restarted) | wakes |
  | `rebooted` | booted after it started, and its transcript ends abruptly or was last written within 10 minutes of the boot | wakes |
  | `crashed` | no reboot, transcript ends without the `cost-state` row Claude writes as it exits | wakes |
  | `exited` | transcript ends with `cost-state`: `/exit`, or archived in the desktop app | - |
  | `stopped` | `tn claude stop` ended it | - |
  | `outside` / `missing` | a claude runs it outside tmux / directory or transcript gone | never |

  `resume <name>` also brings back a `stopped` or `exited` one. After an account switch run
  `tn claude login` first: a running claude keeps the login it started with, and Remote Control
  lists it under the old account. Archiving and `/exit` look the same on disk; tn cannot tell
  them apart, and it does not need to.
- **First-run setup.** Until `claude` has been run once in a terminal on a machine
  (`hasCompletedOnboarding` in `~/.claude.json`), it opens its theme and login-method screens
  before anything else, Remote Control included. A detached session sits on them unanswered and
  stays alive, so the startup check cannot see it. `start` therefore exits 3 first, with
  `run: claude` (finish the screens, then exit). Being signed in is not enough: a machine
  signed in by Remote Control's own spawner still shows them.
- **Trust.** A vendored `skills-dir` plugin (a repository's `.claude/skills/`) loads only in a
  trusted directory, and a detached session cannot answer the trust prompt. So `start` sets
  `projects.<dir>.hasTrustDialogAccepted` in `~/.claude.json` first (atomically; invalid JSON is
  left alone and fails the start). On Windows the key is the path with forward slashes
  (`C:/Users/alex/...`), as Claude Code writes and reads it: a backslash key is ignored and the
  prompt still comes up. `--no-trust`, or `[claude] trust = false` in
  `~/.config/tn/config.toml`, opts out. Trust is read at startup, and every running Claude writes
  the whole file back, so a concurrent write can still lose it: check after starting.
- **Environment.** A running tmux server gives new sessions its own environment, so `PATH` and
  `MY_MACHINE` are passed with `-e`. The `@claude_*` / `@tn_*` options are set in the same tmux
  call, so they land even if Claude dies at once; `start` waits 2 s and reports that case with
  the command to run by hand.
- **`login`** reads `claude auth status --json` (`loggedIn`: the exit code is 0 either way), asks
  before replacing a login, and passes its flags to `claude auth login`. `--json` prints the
  status only.
- Global flags are taken by tn anywhere before `--`: pass extra `claude auth login` arguments
  after `--`.

## Authentication

Neither app is signed in by dot: it is an interactive browser or SSO flow, once per machine. For
the CLI, `tn claude login` wraps it and reports the account you are already signed in as first. The desktop app does **not** accept a Console API key; use the CLI for API-key
auth.

## Gotchas

- On a Mac with an older, manually downloaded Claude.app in `/Applications`, the cask's `--adopt`
  fails (the app differs from the cask's version): move the app aside and re-run.
- A vendored `skills-dir` plugin (a repository's `.claude/skills/`) loads only in a trusted
  directory; a detached session cannot accept the trust prompt, so `tn claude start` trusts the
  directory itself (see above, and the repository's CLAUDE.md, "Claude and Codex").
