# idea

JetBrains IDE host tuning. **Opt-in**: no profile selects it; run `dot apply idea`. Linux, macOS
and Windows. On a headless server (`role: server`) only the inotify half applies: a JetBrains
Gateway / remote-development backend watches the project on that machine and needs the higher
limit just as a local IDE does (the old module was opt-in on any Linux host, servers included).
The Markdown half is `role: desktop`.

## Installs

No IDE itself. On a desktop it requires [jetbrains-toolbox](../jetbrains-toolbox/README.md)
(`requires_if: { when: { role: desktop } }`), which installs the Toolbox App; the IDEs are
installed and updated from there. On a server Toolbox (a GUI app) is not pulled in, so `dot
apply idea` still works there. It configures two things:

- **inotify watch limit** (Linux only): `idea.conf` is copied as root to
  `/etc/sysctl.d/idea.conf` (`fs.inotify.max_user_watches = 524288`), and a `reload-sysctl`
  handler runs `sudo sysctl --system` only when that copy changed, so the limit applies without a
  reboot. The IDE needs it to watch large projects.
- **Markdown opens in Preview only**: `markdown.xml` (`MarkdownSettings.splitLayout =
  SHOW_PREVIEW`) is written into every installed product's `options/` directory, matching the
  `workbench.editorAssociations` entry in [vscode](../vscode/README.md).

The one JetBrains config this repository owns besides these is `~/.ideavimrc`, from the
[vim](../vim/README.md) bundle. Fonts, keymaps and the rest live in the same `options/`
directories, which the IDE rewrites constantly: not tracked.

## Markdown preview

The setting is per product, not global (one machine had nine JetBrains products), in:

| OS | directory |
|---|---|
| Linux | `~/.config/JetBrains/<Product>/options/` |
| macOS | `~/Library/Application Support/JetBrains/<Product>/options/` |
| Windows | `%APPDATA%\JetBrains\<Product>\options\` |

The `template` step's destination is the glob `{{ config_dir }}/JetBrains/*/options/markdown.xml`:
one file per product whose `options` directory exists when dot runs. A product installed later
(or first started later) gets it on the next `dot apply idea`.

Valid values come from `TextEditorWithPreview.Layout`: `SHOW_EDITOR`, `SHOW_PREVIEW`,
`SHOW_EDITOR_AND_PREVIEW`. "Preview only" is `SHOW_PREVIEW`.

**A running IDE overwrites this on exit.** So the template step has an `only_if:` guard
(`jetbrains-closed.sh`: `pgrep -if` for the product launchers under `bin/` or `Contents/MacOS/`,
and the classic `com.intellij.idea.Main`; `Get-Process idea64, pycharm64, ...` on Windows). It is
asked only when a file needs writing; while an IDE is running the step is skipped with the reason
(`only_if: sh jetbrains-closed.sh failed`) and the rest of the bundle still applies. Close the IDE
and re-run `dot apply idea`. (The old script failed the whole run instead.)

The template owns the whole `markdown.xml`. The old script left a file alone when it already
contained `SHOW_PREVIEW`; dot compares the whole content, so if an IDE adds other Markdown options
to that file, `dot status` reports it as drift and the next apply writes it back (the first
overwrite of a file dot did not write is saved under dot's state `backups/`).

## Notes

- **inotify is Linux-only**, so that step has `when: { os: linux, env: "!container" }`; macOS and
  Windows get the Markdown half only.
- Since Linux 5.11 the kernel's default `max_user_watches` scales with RAM (about 1% of memory,
  capped at 1048576), so on a machine with a lot of RAM (roughly 64 GB and up) the fixed 524288
  here is lower than the default. Check `sysctl fs.inotify.max_user_watches` without this file
  before relying on it there.
- `sysctl --system` fails inside a container, and the limit is the host kernel's anyway, so the
  inotify step does not run there (`env: "!container"`): raise it on the host.
- `dot remove idea` deletes `/etc/sysctl.d/idea.conf` (as root) but does not re-run sysctl; the
  raised limit stays until a reboot.
