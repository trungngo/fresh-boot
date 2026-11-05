# zoom

[Zoom Workplace](https://zoom.us/download), Zoom's desktop client for meetings and team chat.
Desktops only (`role: desktop`): macOS, Ubuntu desktop (x86_64) and Windows. **Opt-in**: no
profile selects it; `dot apply zoom`.

## Installs

| | how |
|---|---|
| Ubuntu / Debian desktop (x86_64) | Zoom's `.deb` (`https://zoom.us/client/latest/zoom_amd64.deb`), installed as the package `zoom` |
| macOS | cask `zoom` (a `.pkg`: Homebrew asks for the sudo password in the terminal) |
| Windows | winget `Zoom.Zoom` (an MSI, installed for all users) |

Nothing is linked: Zoom keeps its settings with your Zoom account and in its own directories.

## Why the .deb

Zoom publishes no apt repository for Ubuntu; its Linux downloads are the `.deb`, an `.rpm` and a
tarball. `client/latest/` redirects to the current build on `cdn.zoom.us`, so
nothing is pinned. The `.deb`'s install script adds **no** apt source (it registers MIME types,
makes the CEF sandbox setuid and installs an AppArmor profile for Zoom's web view), so there is
no repository to clash with and updates come from this bundle: a later `dot apply` downloads the
file again when Zoom's server reports it changed. Zoom publishes no checksum for the `latest`
file; the download is over https from Zoom's own host.

## Gotchas

- **x86_64 only on Linux.** Zoom ships no arm64 `.deb` (`zoom_arm64.deb` does not exist); on an
  arm64 desktop the step is skipped. The web client (<https://app.zoom.us/wc>) works in a
  browser.
- **macOS: the sudo prompt.** The cask is a `.pkg`, so Homebrew runs `sudo installer` and asks
  for the password in the terminal (dot's plan says so). A non-interactive run needs
  passwordless sudo for it. The package's post-install script opens Zoom once; Homebrew closes
  it again.
- **macOS over ssh** (`dot apply --host`): replacing or installing an app in `/Applications` from
  an ssh session needs App Management permission for `/usr/libexec/sshd-keygen-wrapper`
  (docs/provision-mac.md); otherwise the install fails with "Operation not permitted".
- **Windows: UAC.** `Zoom.Zoom` is a machine-wide MSI; Windows asks for elevation while it
  installs. Without an answer (or with UAC prompts blocked) the step fails: run dot from an
  elevated terminal.
- **Updates on macOS and Windows** come from Zoom's own updater (the cask is `auto_updates`),
  so `brew upgrade` leaves it alone.
- **An existing Zoom** installed by hand: on Linux an installed `zoom` package satisfies the
  step; on macOS a `.pkg` cask cannot be adopted, so Homebrew installs over it.
