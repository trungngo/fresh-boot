# codex

[Codex CLI](https://developers.openai.com/codex/cli) (OpenAI's terminal coding agent) on Linux and
macOS, and the [Codex desktop app](https://openai.com/codex) on macOS.

## Installs

| | Linux | macOS |
|---|---|---|
| Codex CLI | latest release of `openai/codex`: `codex-<arch>-unknown-linux-musl.tar.gz` | `codex-<arch>-apple-darwin.tar.gz` |
| helpers | `ripgrep`, `bubblewrap` (apt) | `ripgrep` (brew) |
| Codex desktop | **not available** | cask `codex-app` |

The CLI is a `github_release` step: the tarball holds one executable named after its target
triple, installed as `~/.local/bin/codex` (on `PATH` via [common](../common/README.md)) and
checked against the release's SHA-256. Linux takes the static musl build, the only Linux build
OpenAI publishes. `dot apply` installs it when missing; `dot apply --upgrade` replaces it when a
newer release is out (`releases/latest` skips the alpha prereleases). Not selected on Windows.

The release carries many other assets (`codex-package-*`, `codex-app-server-*`,
`codex-npm-*`, `bwrap-*`, and `.zst` / `.dmg` / `.sigstore` variants of each), which is why the
step maps each platform to its asset explicitly.

### What the official installer adds, and how it is replaced

`chatgpt.com/codex/install.sh` no longer installs just the binary: it unpacks
`codex-package-<target>` under `~/.codex/packages/standalone/releases/<version>` (`bin/codex`,
`bin/codex-code-mode-host`, `codex-path/rg`, on Linux `codex-resources/bwrap`), points
`~/.local/bin/codex` at it, and keeps its own lock and auto-update marker there. This bundle
does not run it:

- **No shell script edits `~/.zshrc`.** The installer appends a `# >>> Codex installer >>>`
  block to `~/.zshrc` (a link into this repository) whenever `~/.local/bin` is not on `PATH` or
  another package manager owns `codex`; there is no flag to stop it. With a release asset there
  is nothing to stop.
- **ripgrep**: the package's `codex-path/rg` goes on the `PATH` of the commands Codex runs;
  with the plain binary the distro's / Homebrew's `rg` serves instead.
- **bubblewrap** (Linux): Codex's sandbox looks for `codex-resources/bwrap` beside the
  executable, then for `bwrap` on `PATH` (and warns when there is none), so apt's
  `bubblewrap` is installed.
- `codex-code-mode-host` (macOS helper for code mode) is not installed. If a feature asks for
  it and you run the official script by hand, drop codex from this machine's bundles too: the
  next `dot apply` would retire the installer's `~/.local/bin/codex` link again (next section).
- Never `npm i -g @openai/codex` or `brew install codex` on these machines either: two
  managers owning one `codex` is what the installer's `conflict_manager` guards against.

### Migrating from the official installer

Machines set up by the old repository (and by earlier versions of this bundle) ran the official
`install.sh`, which left `~/.local/bin/codex` as a link into
`~/.codex/packages/standalone/releases/<version>/bin/codex`. `github_release` refuses to install
over an executable it did not install, so the first step is
`absent: { ~/.local/bin/codex: { pointing_into: ~/.codex/packages } }`: it removes that link
(only a link into `~/.codex/packages`; a real file or a link elsewhere is left to the next step)
and keeps no backup of it. The install step also says `replace: true`, for two reasons: `dot
plan` judges each step against the machine as it is, so without it the plan would still show the
installer's link as a conflict (and exit 1) although apply removes it first; and any other
`codex` found there (neither dot's nor the installer's) is replaced but kept as
`~/.local/bin/codex.dot-backup`.

The installer's tree is left alone: once `codex --version` answers from the release,
`rm -rf ~/.codex/packages` by hand (it holds only the installer's releases, lock and
auto-update marker; `~/.codex` itself keeps the login, config and sessions).

### No Linux desktop app

OpenAI publishes the desktop app for macOS only: the download host serves
`Codex-darwin-arm64-<version>.zip` and `Codex-darwin-x64-<version>.zip`, while the matching
`Codex-linux-*` URLs return 404, and there is no Linux cask, `.deb` or AppImage. Not a real loss:
Remote Control lets the macOS or mobile app drive sessions running on a Linux machine.

## Authentication

`codex login` is an interactive ChatGPT sign-in, once per machine; `tn codex login` (below)
picks between the browser and device-code flows. It also gates everything else: Remote Control
registers the machine against the account, so until you sign in `codex remote-control start`
fails with "Remote control is enabled on <host> but the connection is errored" (`tn codex start`
checks the login first and exits 3 with `run: tn codex login`).

## Sessions are shaped differently from Claude's

| | Claude | Codex |
|---|---|---|
| background unit | one process per session | **one shared app-server daemon** hosting every session |
| naming | `--remote-control <name>` + `-n <name>` | sessions are named on the daemon, not at launch |
| listing | `claude agents --json` | `codex agents`: a **full-screen browser**, no JSON |
| attach | `claude attach <short-id>` | `codex resume <name-or-uuid>` |
| Remote Control | per session | **per daemon** (`codex remote-control start` / `pair`) |

So there is no per-directory background session to start and name: `tn codex start` brings the
daemon up and pairs it instead (next section).

The daemon refuses to run with `CODEX_HOME` under `/tmp`, and its control socket path must stay
under `SUN_LEN` (108 bytes): both show up as confusing connect failures if `CODEX_HOME` is moved
somewhere long or temporary.

## `tn codex`: the daemon and its sessions

This bundle ships the tn plugin `codex` (copied to `~/.local/share/tn/plugins/codex.py`; spec:
`docs/tn.md` §7.3), which replaces the old `codex-start`, `codex-list`, `codex-attach`,
`codex-stop` and `codex-login` scripts. It requires the `tn` and `projects` bundles (targets are
resolved as `tn claude start` resolves them). The verbs match `tn claude`, their meaning follows
the daemon:

| command | what it does |
|---|---|
| `tn codex start [target] [--ws NN\|new]` | checks the login, resolves the target (project, `project/repo[@ws]`, repo, path; default: here) to its git root, runs `codex remote-control start` (a no-op when the daemon runs) and `codex remote-control pair`, printing the pairing code; hints `codex -C <dir>` |
| `tn codex ls` | one row for the daemon (running, status, versions from `codex app-server daemon version`, login). Never opens `codex agents`, the full-screen browser |
| `tn codex attach [name]` | hands the terminal to `codex resume <name>` (name or uuid); with no name, to `codex resume --all`, Codex's own picker, which needs a terminal |
| `tn codex stop` | daemon-wide: confirms (`--yes` skips), then `codex remote-control stop`. Conversations are kept |
| `tn codex login [--device-auth \| --with-api-key \| --with-access-token]` | prints the current state, confirms before replacing a login, then runs `codex login`. No flag: the browser flow on macOS, or on Linux with `DISPLAY` / `WAYLAND_DISPLAY`, and not over ssh; otherwise `--device-auth`. The two `--with-*` flags read the secret from stdin: `printenv OPENAI_API_KEY \| tn codex login --with-api-key` |

`--json` works on `start`, `ls`, `stop` and `login` (status only, no sign-in); `-n` shows what
would run. `tn sessions` lists the daemon as one `codex` row while it runs (Codex has no
machine-readable session list), `tn status` says `daemon running` / `daemon stopped`, and
`tn doctor` checks that codex is installed and signed in.

`codex login status` prints "Not logged in" and still exits 0, with no `--json`: the plugin
matches the text (`ot logged in`) on the captured output. The old scripts learned the hard way
that piping it into `grep -q` under `pipefail` SIGPIPEs codex and inverts the test.

## Still unverified (from the old TODO)

`codex remote-control start` succeeding and `codex remote-control pair` printing a code both need
a signed-in account; whether `remote-control start` is idempotent on a running daemon (which
`tn codex start` assumes) is unconfirmed, and so is whether `pair` returns at once after printing
the code or waits for a device (`tn codex start` streams its output in text mode, but captures it
for `--json`). The `codex-app` cask has never been installed by this repo.
