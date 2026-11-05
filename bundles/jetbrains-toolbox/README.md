# jetbrains-toolbox

The [JetBrains Toolbox App](https://www.jetbrains.com/toolbox-app/), which installs, updates and
launches the JetBrains IDEs (IntelliJ IDEA, PyCharm, GoLand, Rider, ...). Desktop only (`role:
desktop`): macOS, Ubuntu desktop and Windows profiles select it. The IDEs themselves are not dot's
job: pick them in Toolbox. The opt-in [idea](../idea/README.md) bundle (host tuning) requires this
one on a desktop.

## Installs

| | source | where |
|---|---|---|
| macOS | Homebrew cask `jetbrains-toolbox` (dot adds `--adopt`) | `/Applications/JetBrains Toolbox.app` |
| Windows | winget `JetBrains.Toolbox` | `%LOCALAPPDATA%\JetBrains\Toolbox` |
| Linux x86_64 / aarch64 | `download:` of JetBrains' tarball | `~/.local/share/JetBrains/Toolbox/bin`, linked as `~/.local/bin/jetbrains-toolbox` |

Linux has no apt repository and no GitHub release; JetBrains' own download service is the
official source. The step asks its release feed
(`https://data.services.jetbrains.com/products/releases?code=TBA&latest=true&type=release`) for the
latest build (`latest:` with a pattern over the `linux` link, `jetbrains-toolbox-<build>.tar.gz`),
downloads `https://download.jetbrains.com/toolbox/jetbrains-toolbox-<build>.tar.gz`
(`-arm64.tar.gz` on aarch64) and checks it against the `.sha256` JetBrains publishes beside it.
Nothing is pinned. (`https://data.services.jetbrains.com/products/download?platform=linux&code=TBA`
redirects to the same file, but gives no digest to check.)

The tarball is `jetbrains-toolbox-<build>/bin/...`; `strip: 2` unpacks the contents of `bin/`
into `~/.local/share/JetBrains/Toolbox/bin`, which is where Toolbox installs itself when first run
from anywhere else. So the first launch finds itself in place, and the IDEs go next to it under
`~/.local/share/JetBrains/Toolbox/apps`.

## First run

Start it once (`jetbrains-toolbox`, or the app on macOS / Windows) and sign in. On Linux it then
creates its own `~/.local/share/applications/jetbrains-toolbox.desktop` and an autostart entry;
dot writes neither, so they are Toolbox's and match what it expects.

## Updates

Toolbox updates itself (and the IDEs) in place. dot keeps out of its way:

- Linux: the tarball is **merged** into `bin/`, not `replace: true`: Toolbox rewrites that
  directory when it updates, and a replaced tree would make every self-update look like drift
  (and `replace` of the whole `Toolbox/` directory would take the installed IDEs with it). The
  step is satisfied while the build dot recorded is still JetBrains' latest; when a newer one is
  out, `dot apply` unpacks it over what is there, which is what Toolbox would have done anyway.
- macOS / Windows: the cask / winget package is installed once; `dot apply --upgrade` brings the
  manager's record up to date.

## Notes

- `dot remove jetbrains-toolbox` on Linux removes the `~/.local/bin` link and dot's record; the
  unpacked files (merged, and rewritten by Toolbox) and the installed IDEs stay. Uninstall from
  Toolbox's own settings first if the IDEs should go too.
- The old repo never installed Toolbox (its idea module only tuned inotify and a Markdown
  setting); this bundle is new.
