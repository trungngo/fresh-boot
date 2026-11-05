# battlenet

[Battle.net](https://download.battle.net/en-us/desktop), Blizzard's game launcher. Windows
desktops only for now. **Opt-in**: no profile selects it; `dot apply battlenet`.

## Installs

| | how |
|---|---|
| Windows | winget `Blizzard.BattleNet` (Blizzard's `Battle.net-Setup.exe`) |

Nothing is linked: settings and games belong to your Battle.net account and the launcher.

## Gotchas

- **The setup is a bootstrapper.** It downloads the launcher itself, asks for elevation (UAC)
  and opens the launcher's login window when it finishes; sign in there.
- **Updates** come from the launcher itself; winget's version only matters for the first install.
- Not tried on a machine yet. macOS has a Homebrew cask (an installer that needs the GUI);
  there is no Linux client.
