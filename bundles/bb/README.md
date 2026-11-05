# bb

[bb](https://getbb.app) ([source](https://github.com/get-bb/bb)): an IDE that can control and
customize itself. Desktops only (`role: desktop`).

## Installs

| | how |
|---|---|
| Ubuntu / Debian desktop, x86_64 | the AppImage from the latest GitHub release of `get-bb/bb`, saved as `~/.local/share/bb/bb.AppImage`, plus a desktop entry |
| macOS, Apple Silicon | the latest disk image (`getbb.app/download/macos`) copied into `~/Applications/bb.app` |

No sudo anywhere. Nothing is pinned: a new release replaces the AppImage on the next apply, and
`dot apply --upgrade bb` reinstalls the Mac app.

## Not installed

- **Intel Macs and Linux arm64:** upstream publishes no build; the steps skip there.
- **Windows:** upstream supports it only through WSL (`npx bb-app@latest` inside WSL).
- **Servers:** it is a GUI app; the `bb` CLI is on npm as `bb-app` (`npx bb-app@latest`).

## Gotchas

- **Why `~/Applications`:** user-owned, so no sudo, and macOS's App Management protection, which
  blocks ssh sessions from changing `/Applications`, does not apply.
- **Why the disk image, not the zip:** dot's zip unpacker skips symlinks, which an Electron
  `.app` relies on; `ditto` from the mounted image keeps the bundle intact.
- **AppImage launch:** the desktop entry passes `--appimage-extract-and-run`, so no FUSE
  (`libfuse2`) is needed. If Ubuntu 24.04's unprivileged-user-namespace restriction makes the
  sandbox refuse to start, bb needs `--no-sandbox` (or an AppArmor profile); not applied here.
- **Codex** is its own bundle (`bundles/codex`).
