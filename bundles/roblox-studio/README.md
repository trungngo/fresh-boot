# roblox-studio

[Roblox Studio](https://create.roblox.com/), Roblox's editor for building experiences. Windows
desktops only for now. **Opt-in**: no profile selects it; `dot apply roblox-studio`. The player
is its own bundle, [roblox](../roblox/README.md).

## Installs

| | how |
|---|---|
| Windows | winget `Roblox.RobloxStudio` (Roblox's `RobloxStudioInstaller.exe`) |

## Gotchas

- **Per user**, under `%LOCALAPPDATA%\Roblox`: no UAC prompt. The installer opens Studio when
  it finishes; sign in there with a Roblox account.
- **Updates** come from Studio itself on launch.
- macOS has a Homebrew cask; Roblox has no Linux client.
