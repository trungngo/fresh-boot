# chrome

[Google Chrome](https://www.google.com/chrome/). Desktops only (`role: desktop`).

## Installs

| | how |
|---|---|
| Ubuntu / Debian desktop (x86_64) | Google's `.deb` (`google-chrome-stable_current_amd64.deb`), installed as the package `google-chrome-stable` |
| macOS | cask `google-chrome` (dot adds `--adopt`) |
| Windows | winget `Google.Chrome` |

Nothing is linked: Chrome keeps its profile in its own directories and syncs settings,
bookmarks and extensions through your Google account.

## Default browser (Windows)

The bundle makes Chrome the default browser on Windows. Windows lets only its Settings app
write the http/https choice (the `UserChoice` key carries a hash tied to the user and the
time), so no tool can set it silently: the step runs `chrome --make-default-browser`, which
opens Settings > Default apps on Google Chrome, and you click **Set default**. The step's check
reads the `UserChoiceLatest` (current Windows 11) or `UserChoice` ProgId of `http` and `https`;
until both are Chrome's `ChromeHTML`, every `dot apply` opens that page again.

## Why the .deb, and no `package_repo`

Google's `.deb` sets up Google's apt repository itself when it is installed
(`/etc/apt/sources.list.d/google-chrome.list` plus Google's signing key), and a daily cron job
from the package puts them back if they go missing. From then on `apt upgrade` updates Chrome.
Adding the same repository from dot as well would give apt two entries for one repository with
different `Signed-By`, and apt then refuses to read **any** source, which breaks every apt
install on the machine (the claude bundle's Claude Desktop had exactly that). So this bundle
installs the `.deb` once and leaves the repository to Google.

The download is over https from `dl.google.com`; Google publishes no checksum for the
`_current_` file, so it is not checked against one.

## Gotchas

- **x86_64 only on Linux.** Google ships no arm64 Chrome for Linux; on an arm64 desktop the
  step is skipped (`chromium` from your distribution is the alternative).
- **macOS over ssh** (`dot apply --host`): replacing or adopting an app in `/Applications` from
  an ssh session needs App Management permission for `/usr/libexec/sshd-keygen-wrapper`
  (docs/provision-mac.md); otherwise Homebrew fails with "Operation not permitted".
- **An existing Chrome** installed by hand: on macOS dot adopts it (`--adopt`) when it is the
  same version; on Linux, an installed `google-chrome-stable` already satisfies the step.
