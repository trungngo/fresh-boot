# localsend

[LocalSend](https://localsend.org): send files and text between nearby devices (phones
included) over the local network, with no account and no cloud. Desktops only
(`role: desktop`).

## Installs

| | how |
|---|---|
| Ubuntu / Debian desktop | upstream's `.deb` from the latest [GitHub release](https://github.com/localsend/localsend/releases) (`github_release` with `package: localsend`), x86_64 or arm64 |
| macOS | cask `localsend` (dot adds `--adopt`) |
| Windows | winget `LocalSend.LocalSend` |

Nothing is linked: LocalSend keeps only its own generated settings.

## Why the .deb

LocalSend publishes no apt repository; its Linux options are the `.deb`, an AppImage, a tarball,
Flathub and the snap. The `.deb` from the release is upstream's own build, needs no snapd or
flatpak, and dot installs the latest release (nothing is pinned); a run after a new release, or
`dot apply --upgrade`, moves it on.

## Gotchas

- **Firewall.** LocalSend listens on port 53317 (TCP and UDP multicast). Ubuntu's `ufw` is off
  by default; if you turned it on, allow the port (`sudo ufw allow 53317`) or the device stays
  invisible to others. macOS asks once to allow incoming connections.
- **Same network.** Discovery uses multicast on the local network; guest Wi-Fi with client
  isolation, or a VPN that takes all traffic, hides the devices from each other.
- **Device name.** The bundle sets the name other devices see to `MY_MACHINE` on macOS
  (`flutter.ls_alias` in the app's sandboxed preferences, with `defaults`) and on Linux (the same
  key in `~/.local/share/org.localsend.localsend_app/shared_preferences.json`, rewritten with
  `python3`; the file also holds the app's private key, so only that one key changes). It runs
  only once the app has been launched here, and LocalSend keeps its in-memory name, so quit the
  app before a run that changes it. On Windows the same key is set in
  `%APPDATA%\LocalSend\settings.json` (UTF-8 without a BOM, rewritten through a temporary file);
  quit LocalSend first, since it rewrites that file on exit.
- A command-line LocalSend (`LocalSend-CLI-*`) is in the same releases; it is not installed here.
