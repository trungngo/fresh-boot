# nodejs

Node.js through [fnm](https://github.com/Schniz/fnm) (Fast Node Manager), then the current LTS.

## Installs

| | fnm | Node |
|---|---|---|
| macOS | `brew install fnm` | `fnm install --lts`, made the default (`lts-latest`) |
| Linux | latest GitHub release (`fnm-linux.zip` / `fnm-arm64.zip`) into `~/.local/bin` | same |
| Windows | winget `Schniz.fnm` | same, in pwsh |

`dot apply --upgrade` runs `fnm install --lts` again: a newer LTS is installed and becomes the
default. Older versions stay installed (`fnm list`, `fnm uninstall <version>`). A project's own
version comes from its `.nvmrc` / `.node-version` (`fnm use`, or automatically on `cd`).

## Shell integration

`nodejs.zsh` (linked to `~/.config/zsh/conf.d/`) runs `fnm env --use-on-cd --shell zsh`, which
puts the default Node on `PATH` and switches versions on `cd`. On Windows a managed block in the
PowerShell profile (`{{ documents }}/PowerShell/Microsoft.PowerShell_profile.ps1`, i.e.
`$PROFILE`) does the same. `{{ documents }}` is Windows' Documents known folder, so a Documents
folder redirected to OneDrive gets the block where PowerShell reads it. winget's fnm is found in
the same run because dot re-reads PATH from the registry after every winget install.

## Why fnm, and the gotchas carried over

- **fnm replaced nvm**, which was pinned at v0.33.11 (a 2018 build under the old `creationix`
  org, no Apple silicon support). fnm is one binary, not a shell function, so it adds none of
  nvm's shell startup cost, and it reads `.nvmrc`, so existing projects work unchanged.
- **fnm's installer must not touch `~/.zshrc`.** The old repo ran it with `--skip-shell`. On
  Linux the bundle no longer runs the script at all: it installs the same release zip the
  script would download, with `github_release`, into `~/.local/bin` (already on `PATH` via
  common). No script, no rc edits, and every `dot apply` moves fnm to a newer release when
  there is one (macOS / Windows: `dot apply --upgrade`, through brew / winget).
- fnm needs `unzip` at startup on Linux; `common` installs it.
- Nothing is pinned: `--lts` resolves the current LTS at run time.

## Dropped from the old repo

- The old zshrc added `~/.local/share/fnm` (where the install script put fnm) to `PATH`; fnm
  now lives in `~/.local/bin`. On a machine set up by the old repo, the old binary in
  `~/.local/share/fnm/fnm` is unused and can be deleted (the Node versions next to it are
  still fnm's and stay).
- `export PATH=~/.npm-global/bin:$PATH` (an nvm-era npm prefix nothing configures any more:
  with fnm, global packages live in the active Node's own directory).
- The `# pnpm` block (appended by pnpm's own installer, with a hardcoded Linux home path).
  Use `corepack enable pnpm` under fnm's Node instead.
