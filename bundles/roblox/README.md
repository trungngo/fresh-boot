# roblox

The [Roblox](https://www.roblox.com/download) player. Windows desktops only for now.
**Opt-in**: no profile selects it; `dot apply roblox`. Roblox Studio is its own bundle,
[roblox-studio](../roblox-studio/README.md).

## Installs

| | how |
|---|---|
| Windows | Roblox's own `RobloxPlayerInstaller.exe`, from `https://www.roblox.com/download/client?os=win` |

## Why not winget

winget's `Roblox.Roblox` is a `portable` package: winget stores `RobloxPlayerInstaller.exe` in
its package directory (and links it onto PATH), but never runs it, so Roblox is not
installed and no Start menu entry appears. The bundle runs the installer itself, in a `shell`
step:

- the download link redirects to the current installer on Roblox's CDN, so nothing is pinned;
- Roblox publishes no checksum, so the file must carry a **valid Authenticode signature whose
  subject is `O=Roblox Corporation`** before it runs (anything else fails the step and is
  deleted);
- `unless:` skips it once `%LOCALAPPDATA%\Roblox\Versions\version-*\RobloxPlayerBeta.exe` exists.

There is no `upgrade:`: the player updates itself every time it launches.

## Gotchas

- **The installer is a GUI.** It installs per user (no UAC prompt) and shows its own window; the
  step waits until that window closes, so close it when it says Roblox is installed.
- macOS has a Homebrew cask; Roblox has no Linux client.
