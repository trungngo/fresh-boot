# fresh-boot

One command on a new machine installs the software you use and sets it up. fresh-boot is a set
of **bundles** (git, zsh, tmux, vim, Ghostty, Tailscale, the GitHub and GitLab CLIs, plus
dozens of opt-in ones) for macOS, Ubuntu desktop, Ubuntu server and Windows, driven by
[`dot`](https://github.com/trungngo/dot-cli): one static binary that reads `dot.yml` and
`bundles/*/bundle.yml`, detects the platform, and installs and links what the machine's profile
selects. It installs from official sources only (package managers, vendor apt repositories, the
projects' own releases), always the current stable version, and re-running it is safe.

This repository holds **no secrets** and nothing personal. Your name, e-mail and machine name are
asked once and kept on the machine ([docs/private-overlay.md](docs/private-overlay.md)).

> **Fork it.** The configs are opinionated (zsh, tmux, vim, Ghostty, keymap): they are the
> author's. Fork the repository, change `dot.yml` to select what you want and edit the bundles
> to taste; every bundle has a README saying what it installs and why. Conventions for changing
> anything: [CLAUDE.md](CLAUDE.md).

## Install

On a new Mac or Ubuntu machine, one command (it detects the platform, installs `git`, clones
this repository to `~/.dot`, installs `dot` from its public release, checksum-verified, and
runs `dot apply`):

    curl -fsSL https://raw.githubusercontent.com/trungngo/fresh-boot/main/install/install.sh | sh

On Windows, in PowerShell:

    irm https://raw.githubusercontent.com/trungngo/fresh-boot/main/install/windows.ps1 | iex

The repository is public, so no GitHub login is needed. Read the scripts first if you like:
[install/install.sh](install/install.sh) picks one of [mac.sh](install/mac.sh),
[ubuntu-desktop.sh](install/ubuntu-desktop.sh) and [ubuntu-server.sh](install/ubuntu-server.sh)
(`FRESH_BOOT_ROLE=server` overrides the desktop/server guess); [windows.ps1](install/windows.ps1)
is the Windows one. They are safe to rerun, and arguments go on to `dot apply`
(`... | sh -s -- --upgrade`).

`dot apply` shows its plan and asks before changing anything. It asks once for your name and
e-mail (the git author) and this machine's short name (`MY_NAME`, `MY_EMAIL`, `MY_MACHINE`),
and keeps them in `~/.config/dot/local.env`.

A server can also be set up from a workstation over ssh, with nothing but ssh on it:
[docs/provision-ubuntu-server.md](docs/provision-ubuntu-server.md),
[docs/provision-mac.md](docs/provision-mac.md). Windows:
[docs/provision-windows.md](docs/provision-windows.md); it is the **least tested** platform.

### Default set and opt-in

The default install is small: **git, gh, glab, tailscale, zsh, tmux, vim and ghostty** (what
exists for the platform), plus `common`, the baseline every bundle assumes. Everything else is
opt-in, so a run installs no surprises:

    dot apply nodejs python rust    # languages
    dot apply vscode docker         # dev tools
    dot apply claude codex          # AI coding CLIs
    dot apply slack chrome          # apps

`dot apply <bundle>` installs it with what it requires. List every bundle with `dot graph`, and
see why one is (not) part of a machine with `dot why <bundle>`. To make a bundle part of your
default, add it to your profile in `dot.yml` in your fork.

### Day to day

    dot apply                  # converge this machine (idempotent: re-run any time)
    dot apply --upgrade        # also upgrade whatever is outdated
    dot apply docker           # one bundle (and what it requires)
    dot plan                   # what would change, changing nothing
    dot status                 # drift and orphans
    dot why <bundle>           # why a bundle is (not) part of this machine
    dot self-update            # newest dot release

To change the configuration, edit the checkout (`~/.dot`, or wherever you cloned your fork),
commit and push; on another machine `git -C ~/.dot pull`, then `dot apply`.

### The `tn` helper

`tn` is an optional helper command (Python 3.11+, standard library only): a core from the `tn`
bundle plus one plugin per bundle, copied in by that bundle, so a machine has exactly the
commands of the bundles applied on it. `tn --help`, `tn status`, `tn doctor`; the full
specification is [docs/tn.md](docs/tn.md). Bundles with a plugin (git, projects, claude, codex,
tmux, vscode, python) bring `tn` in with them; the other bundles never need it.

## Profiles

Chosen from detected facts; `dot facts` shows them. Desktop vs server is the `role` fact
(graphical session or display manager), not the hostname. Pin with `DOT_PROFILE=<name>` or
`DOT_ROLE=server` in `~/.config/dot/local.env`.

| profile | machine |
|---|---|
| `mac` | macOS |
| `ubuntu-desktop` | Ubuntu / Debian with a graphical session |
| `ubuntu-server` | headless Ubuntu / Debian |
| `windows` | Windows 10 / 11 (least tested) |

## Bundles

Columns: **M** mac, **U** ubuntu-desktop, **S** ubuntu-server, **W** windows. `✓` = in the
default set, `·` = opt-in (`dot apply <bundle>`), `req` = pulled in by a bundle that requires it,
`-` = not available.

### Shell and terminal

| bundle | what | M | U | S | W |
|---|---|---|---|---|---|
| [common](bundles/common/README.md) | baseline packages, PATH, directories everything assumes (always applied) | ✓ | ✓ | ✓ | ✓ |
| [tn](bundles/tn/README.md) | the optional `tn` helper command: core, `status`, `doctor`, `sessions`, `config`, shell integration ([docs/tn.md](docs/tn.md)) | req | req | req | req |
| [projects](bundles/projects/README.md) | `tn proj`, `repo`, `ws`, `cd`: the project layout convention | req | req | req | req |
| [zsh](bundles/zsh/README.md) | login shell (plain zsh, starship prompt, autosuggestions, syntax highlighting), the `zshrc` that sources every bundle's shell file | ✓ | ✓ | ✓ | - |
| [tmux](bundles/tmux/README.md) | terminal multiplexer; `tn tmux` | ✓ | ✓ | ✓ | - |
| [ghostty](bundles/ghostty/README.md) | Ghostty terminal and its config | ✓ | ✓ | - | - |

### Editors

| bundle | what | M | U | S | W |
|---|---|---|---|---|---|
| [vim](bundles/vim/README.md) | plain vim (no plugins), and `ideavimrc` | ✓ | ✓ | ✓ | ✓ |
| [vscode](bundles/vscode/README.md) | VS Code, settings, extensions, tunnel, `tn tunnel` port forwarding (servers: tunnel and devtunnel only) | · | · | · | · |
| [zed](bundles/zed/README.md) | Zed editor, `settings.json` and `keymap.json` | · | · | - | · |
| [jetbrains-toolbox](bundles/jetbrains-toolbox/README.md) | JetBrains Toolbox App (installs and updates the IDEs) | · | · | - | · |
| [idea](bundles/idea/README.md) | JetBrains host tuning (inotify limit, Markdown preview; servers: inotify only) | · | · | · | · |

### Source control

| bundle | what | M | U | S | W |
|---|---|---|---|---|---|
| [git](bundles/git/README.md) | global git config and credential helpers; `tn git` | ✓ | ✓ | ✓ | ✓ |
| [gh](bundles/gh/README.md) | GitHub CLI and its `config.yml` | ✓ | ✓ | ✓ | ✓ |
| [glab](bundles/glab/README.md) | GitLab CLI, for gitlab.com and the self-hosted instance | ✓ | ✓ | ✓ | ✓ |

### Languages and runtimes

| bundle | what | M | U | S | W |
|---|---|---|---|---|---|
| [nodejs](bundles/nodejs/README.md) | Node.js LTS via fnm | · | · | · | · |
| [python](bundles/python/README.md) | uv and the current CPython | · | · | · | - |
| [java](bundles/java/README.md) | Eclipse Temurin JDK (LTS) from Adoptium's apt repo, the cask, winget | · | · | · | · |
| [maven](bundles/maven/README.md) | Maven from apt / Homebrew | · | · | · | - |
| [rust](bundles/rust/README.md) | Rust via rustup (+ rust-analyzer, rust-src) | · | · | · | - |
| [go](bundles/go/README.md) | Go toolchain | · | · | · | · |
| [dotnet](bundles/dotnet/README.md) | .NET SDK | · | · | · | - |

### Everything else

| bundle | what | M | U | S | W |
|---|---|---|---|---|---|
| [claude](bundles/claude/README.md) | Claude Code CLI, Claude desktop app; `tn claude` | · | · | · | · |
| [codex](bundles/codex/README.md) | Codex CLI (GitHub release), and the desktop app on macOS; `tn codex` | · | · | · | - |
| [bb](bundles/bb/README.md) | bb, the self-customizing IDE (Linux x86_64, Apple Silicon) | · | · | - | - |
| [tailscale](bundles/tailscale/README.md) | Tailscale mesh VPN (Tailscale's apt repo, cask, winget); log in once with `tailscale up` | ✓ | ✓ | ✓ | ✓ |
| [slack](bundles/slack/README.md) | Slack desktop client | · | · | - | · |
| [localsend](bundles/localsend/README.md) | LocalSend, file sharing over the local network | · | · | - | · |
| [chrome](bundles/chrome/README.md) | Google Chrome | · | · | - | · |
| [vietnamese](bundles/vietnamese/README.md) | Vietnamese language packs and Telex input (IBus Unikey on Ubuntu, the built-in Telex keyboard on Windows) | - | · | - | · |
| [libreoffice](bundles/libreoffice/README.md) | LibreOffice office suite (Ubuntu desktop) | - | · | - | - |
| [flameshot](bundles/flameshot/README.md) | Flameshot screenshots on `Print` (GNOME shortcut; on Windows Flameshot's own key, started at sign-in) | - | · | - | · |
| [rectangle](bundles/rectangle/README.md) | Rectangle, window snapping (free build, Homebrew cask); starts at login | · | - | - | - |
| [evernote](bundles/evernote/README.md) | Evernote notes app (cask on macOS, winget on Windows) | · | - | - | · |
| [microsoft-todo](bundles/microsoft-todo/README.md) | Microsoft To Do (Microsoft Store via winget; macOS off for now) | - | - | - | · |
| [zoom](bundles/zoom/README.md) | Zoom Workplace desktop client (Linux: x86_64) | · | · | - | · |
| [teams](bundles/teams/README.md) | Microsoft Teams (Linux: the unofficial teams-for-linux) | · | · | - | · |
| [godot](bundles/godot/README.md) | Godot game engine | · | · | - | · |
| [unity](bundles/unity/README.md) | Unity Hub (editors are installed from the Hub) | · | - | - | · |
| [ghidra](bundles/ghidra/README.md) | Ghidra reverse engineering suite (release zip on Linux / Windows, Homebrew formula on macOS; needs java) | · | · | · | · |
| [gimp](bundles/gimp/README.md) | GIMP image editor (apt, cask, winget) | · | · | - | · |
| [blender](bundles/blender/README.md) | Blender 3D creation suite (the Blender Foundation's snap, cask, winget) | · | · | - | · |
| [steam](bundles/steam/README.md) | Steam game launcher (winget; Windows only for now) | - | - | - | · |
| [battlenet](bundles/battlenet/README.md) | Battle.net game launcher (winget; Windows only for now) | - | - | - | · |
| [discord](bundles/discord/README.md) | Discord chat (Linux: Discord's `.deb`, x86_64) | · | · | - | · |
| [roblox](bundles/roblox/README.md) | Roblox player (Roblox's signed installer; Windows only for now) | - | - | - | · |
| [roblox-studio](bundles/roblox-studio/README.md) | Roblox Studio (winget; Windows only for now) | - | - | - | · |
| [docker](bundles/docker/README.md) | Docker Desktop on macOS, Windows and x86_64 Linux desktops; Docker Engine + compose/buildx on the other Linux machines | · | · | · | · |

## Adding a bundle

1. `mkdir bundles/<name>` and write `bundles/<name>/bundle.yml`:

   ```yaml
   # yaml-language-server: $schema=https://github.com/trungngo/dot-cli/releases/latest/download/bundle.schema.json
   name: <name>
   description: What it installs, in one line
   requires: [common]
   when: { os: [linux, macos] }          # where it can run at all
   steps:
     - label: Install <tool>
       package: { apt: [<tool>], brew: [<tool>] }
     - label: Link its config
       link:
         ~/.config/<tool>/config: config
   ```

   Prefer a directive to `shell`; a `shell` step always has `unless:`. No version numbers, no
   secret values, never touch `~/.zshrc` (use `path:` / `env:` or a `<name>.zsh` shell file).
   The full rules are in [CLAUDE.md](CLAUDE.md).
2. Add a `README.md` next to it: what, from where, why, and the gotchas. A helper command goes
   in a tn plugin (`bundles/<name>/plugin.py`, tests in `bundles/<name>/tests/`), never a
   script on PATH: see [docs/tn.md](docs/tn.md) §5 and [CLAUDE.md](CLAUDE.md).
3. Select it in the profiles of `dot.yml` that should get it (or leave it opt-in), and add a row
   above.
4. Test without touching this machine:

       test/sandbox.sh srv check
       test/sandbox.sh mac plan <name>
       test/converge.sh desk <name>     # apply twice + status, fakes and a local fixture server
       test/tn-tests.sh <name>          # its tn plugin's tests, then the plugin lint
       test/privacy-check.sh            # nothing personal committed

`dot adopt ~/.config/<tool>/config --bundle <name>` moves an existing file into a bundle and
links it back.

## After the first apply

Things that need a person, once per machine:

- **CLI logins**: `gh auth login`, `glab auth login`, and for the opt-in ones `tn claude login`,
  `tn codex login`, `code tunnel user login`. All store credentials in the keyring or the
  tool's own config; fresh-boot never handles a token.
- **Re-login** after being added to `docker`, `libvirt` or `kvm`.
- **macOS**: an app installed by hand that differs from its cask blocks `--adopt`: move it
  aside once.

## Keymap

One key per action across tmux, ghostty, vim, VS Code, Zed and IDEA: see
[docs/keymap.md](docs/keymap.md).

## Contributing

Issues and pull requests are welcome. Run `test/tn-tests.sh` and `test/privacy-check.sh` before
sending one, and install the pre-push hook (`ln -sf ../../test/pre-push .git/hooks/pre-push`,
see [docs/private-overlay.md](docs/private-overlay.md) §4). Nothing personal and no secret may
be committed.

## License

[MIT](LICENSE).
