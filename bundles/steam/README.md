# steam

[Steam](https://store.steampowered.com/about/), Valve's game store and launcher. Windows
desktops only for now. **Opt-in**: no profile selects it; `dot apply steam`.

## Installs

| | how |
|---|---|
| Windows | winget `Valve.Steam` (Valve's own installer) |

Nothing is linked: Steam keeps its settings and library with your Steam account and in its own
directory.

## Gotchas

- **UAC.** Steam installs for all users under `Program Files (x86)`, so Windows asks for
  elevation while it installs; without an answer the step fails (run dot from an elevated
  terminal).
- **Updates** come from Steam itself on launch; winget's version only matters for the first
  install.
- macOS (cask `steam`) and Ubuntu (Valve's `.deb`, or the `steam-installer` package from
  multiverse) are not wired up yet.
