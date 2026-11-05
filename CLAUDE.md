# fresh-boot

Machine setup for macOS, Ubuntu desktop, Ubuntu server and Windows, driven by
[`dot`](https://github.com/trungngo/dot-cli) (one Rust binary; no dotbot, no submodules), plus
**`tn`**, an optional helper command (Python 3.11+, standard library only; a core and one plugin
per bundle; specification: [docs/tn.md](docs/tn.md)). This repository is **public and holds no
secrets**: it installs a small default set (git, gh, glab, tailscale, zsh, tmux, vim, ghostty)
and offers everything else as opt-in bundles (`dot apply <bundle>`). On a machine it is checked
out at `~/.dot` (the installers' default and `dot`'s fallback; `dot apply --host` syncs a copy
there). The configs are opinionated; people are expected to fork and edit them.

`dot`'s own reference: `dot --help`, `dot <cmd> --help`, `dot schema bundle|repo|secrets` (JSON
Schema; every YAML file here names it for editor completion), and `PLAN.md` in the dot-cli
repository ("As built" sections describe every directive's exact behaviour).

## Layout

    dot.yml               profiles (mac, ubuntu-desktop, ubuntu-server, windows), bundle selection,
                          repo vars, link/shell defaults, package name map
    .env                  committed, shared, non-secret, NON-PERSONAL values (empty today)
    .env.example          every key a machine needs (personal prompts), with no values
    install/              install.sh (detects the platform) + one bootstrap script per platform
                          (clone over https, dot, apply)
    *.example             shapes of private files kept outside the repo (docs/private-overlay.md)
    test/privacy-check.sh publishability scan (generic leaks + a local denylist)
    bundles/<name>/
      bundle.yml          manifest + ordered steps (the only place a bundle is described)
      README.md           what it installs and WHY (the durable knowledge; keep it current)
      <files>             what its steps link, copy or template, named after their target
      <name>.zsh          optional shell integration, linked into ~/.config/zsh/conf.d/
      plugin.py           optional tn plugin, COPIED to ~/.local/share/tn/plugins/<name>.py
      tests/test_*.py     that plugin's tests (never copied to a machine)
    bundles/tn/           the tn core (lib/tn, bin/tn, bin/tn.cmd, tn.zsh) and its tests
    docs/tn.md            the tn specification: commands, plugin API, config, testing
    docs/private-overlay.md  personal values and private tn config kept outside the repo
    docs/keymap.md        the cross-tool keymap tmux/ghostty/vim/vscode/zed/idea share
    test/tn-tests.sh      tn core + every plugin's tests, then the plugin lint
    test/sandbox.sh       run dot as another platform in a throwaway HOME (see Testing)
    test/converge.sh      whole-profile apply twice + status in a sandbox (see Testing)
    test/pre-push         git hook: privacy check + gitleaks before a push
    test/fixtures.py      local release-API / download stand-in for converge.sh
    test/fakebin/         fake sudo, apt-get, dpkg-query, brew, snap, curl, gpg, git, code, ...

There is no build list and no per-OS file: a bundle exists, a profile selects it, `when:` decides
what runs where, `requires` / `after` decide the order.

## Profiles and `when:`

| profile | matches | selects (the default install) |
|---|---|---|
| `mac` | `os: macos` | git gh glab tailscale zsh tmux vim ghostty |
| `ubuntu-desktop` | `os: linux, family: debian, role: desktop` | same as mac |
| `ubuntu-server` | `os: linux, family: debian, role: server` | the same without ghostty |
| `windows` | `os: windows` | git gh glab tailscale vim |

- `common` is `implicit: true` and never listed. Every other bundle is **opt-in**: no profile
  selects it (`dot apply docker`), languages, editors, apps and games alike. A bundle pulled in
  by `requires` needs no selection; `tn` comes along with the bundles whose plugin requires it.
- Desktop vs server is the **`role` fact** (graphical session / display manager), never the
  hostname, so VM and host names are free. Pin a machine with `DOT_ROLE=server` or
  `DOT_PROFILE=<name>` in `~/.config/dot/local.env`.
- Bundle-level `when:` says where a bundle can run at all (`{ os: [linux, macos] }`, `{ role:
  desktop }` for GUI apps). A selected bundle whose `when` fails is dropped silently; a required
  one is an error. Step-level `when:` carries the per-platform differences inside one bundle.
- `when` keys are facts only (`os family distro version codename arch role env pkg init`), never
  the profile name. Values may be lists (any matches) or negated (`os: "!windows"`, quoted).
- Needs systemd (snap, `service` with systemd): `when: { init: systemd }`.
- Every `shell` step in a bundle that can run on Windows carries `when: { os: ... }`: the windows
  profile sets `interpreter: pwsh`, so an unguarded `bash` command would run in PowerShell.

## Writing a bundle

`bundles/common/bundle.yml` is the reference. Rules:

1. **Manifest.** `name` = directory name; a one-line `description`; **`requires: [common]`
   always** (it orders common first and makes its `path:` / `env:` visible: `path`/`env`
   entries are only seen along `requires`/`after` edges). `after:` for ordering without pulling a
   bundle in. `provides:` for
   capabilities others may `requires: [cap:x]`.
2. **Directives before shell.** Use, in this order of preference: `package` (+ `package_repo`
   for vendor apt repos / taps), `github_release`, `download` (tarballs, `.deb`, `latest:`),
   `link`, `copy`, `template`, `block`, `service`, `user`, `path` / `env`,
   `macos_defaults`, `create`, `absent`. **Install only from official sources**: package
   managers, vendor apt repos, the project's own GitHub / GitLab releases, vendor installers
   (Homebrew, rustup, claude). **No `git:` directive and no clone of third-party code** (no
   oh-my-zsh, vim-plug or pyenv checkouts; no submodules). `shell` only when nothing fits
   (vendor installers with their own update logic: rustup, claude; `fnm install --lts`,
   `uv python install`), and then:
   - always `unless:` (the fast "already installed" check), plus `upgrade:` when the tool can
     update itself (`rustup update`), so `dot apply --upgrade` upgrades it;
   - a shell function the command needs comes from `prelude:` (step or
     `defaults: { shell: { prelude } }`), which runs before `cmd`, `unless` and `upgrade`;
   - `sudo: true` if the command uses sudo (asked once up front; never let sudo prompt mid-run),
     `interactive: true` if it must prompt;
   - `&&`, never `&` (`mkdir ~/.ssh & chmod` is a race that leaves `~/.ssh` at 775).
3. **Every step has a `label:`**: what it achieves ("Install fnm", "Link the Ghostty config").
   **Guards** on any step, instead of a shell wrapper: `if: <Jinja expression over variables>`
   (`godot_mono`, `'client_id != ""'`, `'codename in ["jammy", "noble"]'`; OR across values,
   which negated `when:` lists cannot say), `only_if: <cmd>` (run the step only when it exits 0:
   the idea bundle skips its template while an IDE runs) and `unless: <cmd>` (skip it when it
   exits 0: `unless: command -v docker` on a cask). Command guards are asked only when the step
   has work. Retire an old link with `absent: { <path>: { only: link } }` (a real file or
   directory there is kept), or `{ pointing_into: <dir> }`.
4. **Links** inherit `create: true, relink: true, on_conflict: backup` from `dot.yml`: never
   repeat them. Link config the tool edits in place (VS Code settings, gh
   `config.yml`) so UI changes land in the repo; `copy`/`template` what must differ per machine.
5. **Paths.** Tools that use XDG on macOS too (ghostty, zed, gh): literal `~/.config/...`.
   Tools that use the native location (VS Code): `{{ config_dir }}/Code/User` - macOS
   `~/Library/Application Support`, Linux `~/.config`, Windows `%APPDATA%`. Also `data_dir`,
   `cache_dir`, `appdata`, `localappdata`, `documents` (Windows' Documents known folder, OneDrive
   redirection included: `$PROFILE` lives there), `winget_links`, and `homebrew_prefix`
   (`/opt/homebrew` or `/usr/local` by arch). After a winget / scoop install dot re-reads PATH
   from the registry, so a tool installed earlier in the run needs no `path:` step or
   `$env:Path` line to be found. User executables go to `~/.local/bin` (the default of
   `github_release` and `download` `bin:`); nothing installs into the repo checkout.
6. **Package names** that differ per manager go in `dot.yml` `packages:` only when several
   bundles share them; otherwise use the mapping form in the bundle
   (`package: { apt: [...], brew: [...], cask: [...], snap: [...], winget: [...] }`; a manager
   not on this machine is simply skipped).
   **Helper commands are tn plugins** (see "tn: the helper command"), never scripts put on
   PATH: no bundle links or copies a directory of scripts onto PATH. Build-time helpers a
   `shell` step runs (`jetbrains-closed.sh`) stay in their bundle, off PATH.
7. **One bundle, one directory.** Touch only your own `bundles/<name>/`. Shared files
   (`dot.yml`, `.env*`, `README.md`, `CLAUDE.md`) take the smallest additive edit,
   and only when unavoidable.
8. **README.md per bundle**: what it installs, from where, why that source, and every gotcha a
   user would otherwise hit. It is the durable knowledge; keep it current.

## Shell integration: nobody but `zsh` touches ~/.zshrc

`~/.zshrc` is a symlink into this repo (`bundles/zsh/zshrc`). Any installer that appends to it
dirties the working tree and duplicates what zshrc already does. The contract:

- **PATH** -> a `path:` step in your bundle. **Environment variables** -> an `env:` step. Both
  apply to later steps of the same run and are recorded in dot's state; zshrc runs
  `source "$(dot env --shell zsh --cache)"` (kept in `~/.cache/dot/env.zsh`, rewritten when
  dot's state, `local.env`, `dot.yml`, `.env*` or the binary changed), which exports them plus
  every non-sensitive environment-style repo var (`MY_NAME`, `MY_MACHINE`, ...; lowercase
  `projects_dir` stays a template variable). Never a secret: dot never writes sensitive values
  there.
- **Anything else** (`eval "$(fnm env --use-on-cd --shell zsh)"`, completions, aliases)
  -> `bundles/<name>/<name>.zsh`, linked to `~/.config/zsh/conf.d/<name>.zsh`. zshrc sources
  `conf.d/*.zsh` in name order after `compinit`, its aliases and the starship prompt (a file that must run early/late may be named `00-<name>.zsh` / `99-<name>.zsh`), then
  `~/.local.zshrc` last (machine-local, untracked, created empty by the zsh bundle). Guard every
  line (`command -v x >/dev/null && ...`, `[[ -d ~/.foo ]]`): the file may exist before the tool.
- `block:` is for files dot does not own (`~/.bashrc`, `~/.profile`, `/etc/...`), **never
  `~/.zshrc`**.

Installers known to write into shell rc files, and how to stop them:

| installer | suppression |
|---|---|
| fnm | `--skip-shell` (the nodejs bundle no longer runs it: `github_release` of the zip on Linux) |
| rustup | `-y --no-modify-path` (else it edits `~/.profile`, `~/.bashrc`, `~/.zshenv`) |
| Codex | not run: the codex bundle installs the release tarball (`github_release openai/codex`); the installer appends a `# >>> Codex installer >>>` block when `~/.local/bin` is not on PATH |
| uv | not run: `github_release astral-sh/uv` (its installer edits rc files unless told not to) |
| devtunnel | no flag: it appends a PATH line when `~/bin` is not on PATH (zshrc keeps `~/bin` on PATH when it exists). Not run: the vscode bundle `download`s the same binary to `~/.local/bin` |
| oh-my-zsh | dropped: zshrc does what its lib/ and plugins did; its `tools/install.sh` moved a symlinked `~/.zshrc` aside even with `--unattended` |
| Homebrew | writes nothing (only prints a hint); brew's PATH comes from common |
| Unity CLI | no flag known: it appends `. "$HOME/.unity/env"` (PATH to `~/.unity/bin`) to `~/.zshrc`; delete that line, the unity bundle's `path:` step replaces it |

A new installer: read its script for `>> ~/.zshrc` / `.profile` / `.bashrc` before using it.

## No pinned versions

Every installer resolves the current stable release at run time. Pinning rots a setup repository:
an nvm, Go, .NET or Python stuck at a years-old build keeps downloading fine, so nothing fails;
it just installs obsolete software. **Do not write a version number into
this repo** (URLs, package names, assets). How "latest" is resolved:

| bundle | latest via |
|---|---|
| go | `download` with `latest: https://go.dev/VERSION?m=text` (first line), checked against `sha256_url` |
| java | Temurin **LTS** by package ID (`temurin-25-jdk`, cask `temurin@25`, winget `EclipseAdoptium.Temurin.25.JDK`): the one sanctioned version number, because the unversioned IDs track the newest feature release, not the LTS. Bump at the next LTS |
| maven | the package manager's `maven` |
| python | uv's GitHub release; CPython = the newest stable minor uv knows, `uv python install --default --upgrade 3.X` |
| codex, starship, uv | latest GitHub release (`github_release`) |
| jetbrains-toolbox | `download` with `latest:` from JetBrains' release feed, checked against its `.sha256` |
| nodejs | `fnm install --lts` |
| rust | rustup `stable`, `upgrade: rustup self update && rustup update stable` |
| dotnet | `package` pattern `dotnet-sdk-*` (newest match in the Ubuntu archive; a bare version beats `-source-built-artifacts`) |
| gh, docker, vscode, claude desktop | the vendor apt repo's candidate (`package_repo`; gh pins both keys of its keyring) |
| glab, ghostty, zed, godot | latest release (`github_release` / `download: { release: ... }`, GitLab for glab) |
| casks, snaps, winget | the manager's current version |

`dot apply --upgrade` upgrades everything that can be; plain `dot apply` only installs what is
missing. Vendor repos are **pinned by key fingerprint** (`fingerprint:` on `package_repo`), which
is not a version: that is required, not forbidden.

**apt freshness is dot's job.** Hand-written `refresh_apt` helpers are unnecessary because `apt-cache policy`
trusts whatever the last `apt-get update` fetched, so a stale cache silently answered "up to
date". dot refreshes at most once a day, treats stale lists as unknown and refreshes before
trusting a candidate, and a changed `package_repo` forces a refresh. Never write `apt-get update`.

## macOS: casks

`package: { cask: [...] }`. dot adds `--adopt` itself to casks whose artifact is an `app` (a
fresh Mac usually has some apps already in `/Applications` that brew did not put there), checked
against `https://formulae.brew.sh/api/cask/<token>.json`; `.pkg` casks (`dotnet-sdk`,
`openvpn-connect`) cannot be adopted and run `sudo installer`, so they need a terminal (the
`cask-pkg-sudo` hint says so). Adopt fails when the installed app differs from the cask's
version: move the app aside (`brew-adopt-conflict` hint). Do not set
`HOMEBREW_NO_REQUIRE_TAP_TRUST`; `package_repo: { brew: tap }` trusts the tap.

## Clean-machine assumptions

Assume nothing about the machine's prerequisites:

- **No SSH keys.** The bootstrap clones this repository over `https://`. SSH keys are never synced:
  generate per machine, register with `gh ssh-key add` / `glab ssh-key add`.
- **Nothing beyond `common`** exists: need a tool, `requires` its bundle or install it.
- **No login session state**: new group membership (`docker`, `libvirt`, `kvm`) needs a re-login
  (the `user` directive prints a notice); a `systemd --user` service needs `linger: true` to
  survive logout.
- **No systemd** in containers / WSL without `[boot] systemd=true`: guard with `init: systemd`.
- **sudo only through dot**: `sudo: true` on shell steps, `root: true` on file directives; the
  password is asked once, up front.

## Bootstrap: the install/ scripts

`trungngo/dot-cli` (dot) and this repository are both **public**, so a fresh machine needs
nothing but a shell and `curl`. `install/install.sh` detects the platform (macOS; Linux with
`role` desktop or server, `FRESH_BOOT_ROLE` overrides) and runs `mac.sh`, `ubuntu-desktop.sh` or
`ubuntu-server.sh` (a sibling when run from a checkout, downloaded when piped from curl);
`windows.ps1` is the Windows one. Each installs the prerequisites (Homebrew, or `curl` and
`git`), `git clone`s this repository to `~/.dot` over https, installs dot from its public release
(checksum-verified, no token) and `exec dot apply` (with `--profile` on Ubuntu). They must stay
self-contained (they run before the repository exists) and idempotent. Rules that follow:

- No login, no token. Never write a token into this repository, a bundle, `dot.yml`, a test or
  an example command; never add a step that exports `GITHUB_TOKEN` / `GH_TOKEN` (an environment
  token overrides gh's stored credentials). `gh auth login` is a post-install step for the user.
- `dot cloud-init` would put credentials in user data (readable by the cloud provider): set up
  VMs with `dot apply --host`, which downloads dot's release for the VM on the local machine and
  copies the binary over. It forwards `persist: local` vars, except `per_machine: true` ones.
- The `$schema` URLs at the top of the YAML files point at dot's public release assets;
  `dot schema bundle|repo|secrets` prints them locally.

## Secrets: none in this repository

This repository is public and holds **no secret, ever**: no token, password, key, VPN profile or
private config, not even in a comment, test fixture or example. fresh-boot needs none: `gh` and
`glab` log in interactively, and every other login is the tool's own prompt.

- Never export a secret into every shell. Never export `GH_TOKEN` or `GITLAB_TOKEN`: an
  environment token shadows stored credentials (it breaks `gh auth switch`, and an empty
  `GITLAB_TOKEN` leaves gitlab.com at 401). gh and glab authenticate into the system keyring.
- A fork that needs a secret declares it with dot, outside the committed tree: a logical name
  (`<bundle>_<what>`, generic: never a person, company or host) resolved by `{{ secret("name") }}`
  or `secret_file` from a provider or `~/.config/dot/secrets.env` (0600); see
  docs/private-overlay.md §3. Pass it to a command through dot's env var or stdin
  (`printf '%s\n' "{{ secret(...) }}" | tool --stdin`), never argv, which `ps` shows.
- Never write a secret through a path that is a symlink into this repo. `.gitignore` catches
  `*.ovpn`, `*.pem`, `*.key`, `secrets.env` as a backstop, not a license.
- Before pushing: `test/privacy-check.sh` and gitleaks (`test/pre-push` runs both).

## Privacy (absolute rule): this repository is publishable

Nothing personal is committed either: no real name, e-mail address (only `@example.com` /
`@example.org`), user or account name, `/Users/<name>` or `/home/<name>` path, machine name,
private or company host, company, client or project code name or ssh host, not in code, docs, skills, tests, fixtures or comments. Use
example data (`alex`, `Alex Doe`, `acme/shop`, `gitlab.example.com`). Personal values live
in the private overlay (docs/private-overlay.md): dot's prompts in `~/.config/dot/local.env`,
and private tn config (`~/.config/tn/conf.d/*-private.toml`) written by the user, with a
committed `*.example` showing its shape.
`test/privacy-check.sh` must pass (it also reads a denylist of real identifiers kept OUTSIDE the
repo, `~/.config/dot/privacy-denylist`); intentional references (only where dot and this
repository are published) go in `test/privacy-allowlist`.

## Variables

- Repo vars (`dot.yml`): lower_snake paths `projects_dir` (`~/myprojects`), `learning_dir`;
  common exports `projects_dir` as `MYPROJECTS_DIR`.
- Personal values are `prompt:` vars with `persist: local` in `dot.yml`: `MY_NAME`, `MY_EMAIL`
  (and `MY_MACHINE` below). The first interactive `dot apply` asks once and keeps them in
  `~/.config/dot/local.env`; `test/sandbox.sh` presets example values.
- `.env` (committed): UPPER_SNAKE shared values that are neither secret nor personal (none
  today). `.env.<profile>` for profile-specific ones.
- `MY_MACHINE` (this machine's short name, used in Claude/Codex session names like
  `Acme Shop #U1-00`): a `prompt:` var with `persist: local`, so the first interactive
  `dot apply` asks once and writes it to `~/.config/dot/local.env`. A non-interactive run without
  it fails up front: set it in `local.env` first, or pass `--var MY_MACHINE=<name>`. It must
  never be in a tracked file. It is `per_machine: true`: `dot apply --host` never copies this
  machine's value to another one; it asks for the remote's (kept in the remote's `local.env`)
  or takes `--var`. Any other variable that names or belongs to one machine must be declared
  `per_machine: true` too.
- Machine-local overrides: `~/.config/dot/local.env` (also `DOT_PROFILE`, `DOT_ROLE`,
  `DOT_REPO`), never committed. `dot vars` shows every value and where it came from.

## tn: the helper command

`tn` is the one helper command, optional on a machine (a bundle needs it only when it ships a
plugin). Spec: [docs/tn.md](docs/tn.md). Rules:

- **One plugin per bundle**: `bundles/<b>/plugin.py` (or a `plugin/` package), with
  `plugin = Plugin("<b with - as _>", help=..., requires=[...], groups=[...])` at module level,
  **literal arguments only** (discovery reads it with `ast`, without importing). A group name
  is claimed by exactly one plugin; built-in names (`status doctor sessions plugins config
  shell`) cannot be groups.
- **Wiring**: the bundle says `requires: [common, tn]` (plus `projects` when the plugin imports
  it; a plugin's `requires` must be a subset of its bundle's) and has a step, after its packages
  and before anything that calls tn:

      - label: Copy the tn plugin
        copy:
          ~/.local/share/tn/plugins/<b>.py: plugin.py

  **Copied, never linked**, as the core is: a machine has exactly the commands of the bundles
  applied on it, and tn keeps working while this checkout moves.
- **Python 3.11+, standard library only** (`common` installs it). No 3.12+ syntax or APIs.
- **Command language**: `tn <group> <verb> [target] [flags]`, verbs from docs/tn.md §2.2
  (`new ls show rm open close start stop attach ...`). Global flags (`-C -n -y -q -v -h`,
  `--json --dry-run --yes --quiet --verbose --no-color`) belong to core: a plugin never
  declares them. Exit codes: 0 ok, 1 failed, 2 usage (with `choices` in JSON), 3 missing
  prerequisite (always with a `run: <fix>` line). `--json` never prompts; `--dry-run` changes
  nothing (use `tn.proc` / `tn.fs`, which honour it).
- **Through core, never around it**: processes via `tn.proc` (`run`, `capture`, `need`,
  `handoff`, `spawn_detached`), files via `tn.fs`, time via `tn.clock`, TTY checks via
  `tn.term`, output via `tn.out`, prompts via `tn.prompt`; no environment reads at import time.
  That is what makes the tests work.
- **Personal data** (people, forge owners) comes from private config in
  `~/.config/tn/conf.d/*-private.toml` (see Privacy), never from the plugin or a committed
  `conf.d` file.
- **Tests**: `bundles/<b>/tests/test_*.py` with `tn.testing.TnTestCase` (temp HOME, fake
  executables, `self.tn(...)` in process). Every command needs the `--json` happy path, the
  usage error, the missing prerequisite, `--dry-run` making no change and the no-TTY rule.
  Never the real `$HOME`, network, tmux server or VM. Run:

      test/tn-tests.sh                 # core, every plugin suite, then the lint
      test/tn-tests.sh git projects    # some suites (and the lint)

## The project layout convention (tn, claude, codex)

The machine organises work under one root:

    $MYPROJECTS_DIR/<project>/src/<repo>                  # ~/myprojects

tn derives its Context (root, project, workspace, repo) from `$PWD` (docs/tn.md §3);
`tn status --json` prints it.

Outside the convention the Context is empty, and every command that needs a project or repo
says so (exit 2) instead of guessing (a resolver that falls back to `$HOME` goes wrong silently).

Parallel workspaces `src-01`, `src-02` beside `src/` (`tn ws new`) are clean clones reset to the
remote's main branch, not `git worktree`s, because a worktree writes into the source repo's
`.git`. Paths are never rebuilt with a hardcoded `src` (inside `src-01/<repo>` that returns the
original repo). `tn proj new` / `tn repo new` are the sanctioned way to create
either level; `tn repo new` adds no remote unless asked (`tn git remote add <forge>`).

## Claude and Codex

- Never link `~/.claude` into git: it holds runtime state. If a bundle links skills, link only a
  `skills/` subdirectory; they load in a new session.
- `tn claude start` names sessions `<Project> <Repo> #<Machine>-<Workspace>` (`#U1-00`: `00`
  for `src/`, `01` for `src-01`); `<Machine>` is `$MY_MACHINE`, which tn reads from the
  environment `dot env` provides (or `~/.config/dot/local.env`), never invents.
- Sessions run in detached tmux (`claude-<slug>`, tagged `@claude_name` / `@claude_dir` /
  `@claude_uuid`), not `--bg` (those went offline after long idle); `--session-id` pins the uuid so
  `tn claude start --resume <full uuid>` works.
- A vendored `skills-dir` plugin (a repo's `.claude/skills/`) loads only in a **trusted**
  directory (`~/.claude.json` `projects.<path>.hasTrustDialogAccepted`); a detached session can
  never accept the prompt, so `tn claude start` trusts by default (`--no-trust` opts out) and a
  fresh project needs one interactive `claude` there. Trust is read at startup.
- The Claude Code installer refuses sudo; Codex's daemon refuses `CODEX_HOME` under `/tmp`, and
  its socket path must stay under 108 bytes.

## Testing

Never test against the real `$HOME` and never run real installers. `test/sandbox.sh` runs `dot`
with `HOME` / `XDG_*` in a throwaway directory (`env -i`: nothing of your environment leaks in),
`DOT_REPO` set to this checkout, `DOT_FACTS` simulating the platform, root-owned files
(`package_repo` keyrings and sources, `root: true` copies and downloads, `/etc/shells`) under
`$SANDBOX/root` (`DOT_SYSROOT`), and `test/fakebin` first on `PATH` and kept ahead of every
`path:` step (`DOT_PATH_FIRST`), so a mac run never reaches the real `/opt/homebrew/bin`. A mac
sandbox starts without Homebrew, as a fresh Mac does: `homebrew_prefix` is overridden (in the
sandbox's `local.env`) to `$SANDBOX/root/opt/homebrew` (Intel: `.../usr/local`), common's
"Install Homebrew" step runs a fake installer that puts `test/fakebrew/brew` there, and each
formula it installs gets a stub in that `bin/` (Homebrew zsh as the login shell). Each
fake logs its argv to `$SANDBOX/calls.log` and keeps state under `$SANDBOX/state`:

    export DOT=/path/to/dot              # or have dot on PATH
    test/sandbox.sh srv check                              # every file and the graph
    for p in mac desk srv win; do test/sandbox.sh $p plan <bundle>; done
    test/converge.sh desk <bundle>...    # apply, apply again (0 changed), status (in sync)
    test/converge.sh mac                 # the whole mac profile
    cat "${TMPDIR:-/tmp}/dot-converge-desk/calls.log"      # what would have run
    test/tn-tests.sh                     # tn core and plugin tests (no sandbox needed)
    test/privacy-check.sh                # nothing personal committed (must pass)

`test/converge.sh` starts `test/fixtures.py` (a local
stand-in for the GitHub / GitLab release APIs, release assets, go.dev and the devtunnel blob,
reached through `DOT_GITHUB_API`, `DOT_GITLAB_API` and `DOT_URL_REWRITE`), and tells fake curl /
gpg which fingerprints each pinned `package_repo` key has. `sandbox.sh` passes those variables,
`GITHUB_TOKEN` and `DOT_SNAPD` (default 1) through.

`DOT_FACTS` is `fact=value,...` (`os`, `family`, `distro`, `version`, `codename`, `arch`, `pkg`,
`role`, `env` with `+` between values, `init`); the presets are `mac` (Apple silicon),
`mac-intel`, `desk`, `srv` (Ubuntu 24.04, x86_64) and `win`. Windows is plan-only from a Unix host (its known folders
resolve under the sandbox home). When a bundle needs a tool the fakes lack, add a small generic
fake to `test/fakebin/` (log argv, keep state under `$FAKE_STATE`, refuse to write outside the
sandbox: the stand-in installers of fake `curl` check that `$HOME` and their target lie under
the sandbox directory, the parent of `$FAKE_STATE`). Never run a fake or a fake installer from
your own shell: it inherits your real `HOME`, `CARGO_HOME` (a fake rustup-init run
that way once replaced the real `~/.cargo/bin/rustup` with a stub). Whole-machine tests belong in a throwaway VM, never
on a workstation.

Definition of done for a bundle: `dot check` clean, `dot plan` sensible on all four presets, a
sandbox apply that converges (second run: 0 changed, `status` in sync), `test/tn-tests.sh <b>`
passing when it has a plugin, README.md written, `test/privacy-check.sh` clean (and
`gitleaks detect` when installed).

## Reading dot's output

Failures show the step's last 20 output lines, a `hint:` for known failures (dpkg lock, adopt
conflict, untrusted tap, sudo without a terminal, ...) and the log path; every run's full log is
in `~/.local/state/dot/logs/`. `-v` lists every step, `-vv` streams command output. `dot plan`
changes nothing and needs no secrets; `dot status` shows drift; `dot why <bundle>` explains the
selection; `dot graph` the order.
