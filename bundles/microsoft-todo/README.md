# microsoft-todo

[Microsoft To Do](https://to-do.office.com): task lists synced with a Microsoft account.
Desktops only, and only macOS and Windows (`when: { role: desktop, os: [macos, windows] }`):
on an Ubuntu desktop the bundle is selected but does nothing.

## Installs

| | how |
|---|---|
| macOS | the Mac App Store app (id `1274495053`, bundle id `com.microsoft.to-do-mac`) through [`mas`](https://github.com/mas-cli/mas): formula `mas`, then `mas get 1274495053` unless `/Applications/Microsoft To Do.app` exists |
| Windows | the Microsoft Store app (`9NBLGGH5R558`, package family `Microsoft.Todos_8wekyb3d8bbwe`): `winget install --id 9NBLGGH5R558 --source msstore`, unless `winget list` finds it there |
| Ubuntu / Debian desktop | nothing: Microsoft ships no Linux app. Use the web app, <https://to-do.office.com> (install it as an app from Chrome or Edge, "Install page as app", for a window and launcher of its own). Unofficial wrappers exist; they are third-party code, not installed here, use them at your own risk |

Nothing is linked: lists and settings live in your Microsoft account.

## Why the stores

Microsoft publishes To Do only through the two app stores: there is no Homebrew cask (Homebrew
does not package App Store apps) and no winget-community manifest. dot has no App Store package
manager, so macOS uses a `shell` step around `mas`; `mas get` is mas's command for free apps
(`purchase` is its older name; `mas install` only re-installs apps the Apple Account already
has). On Windows dot's winget `package` items cannot name a source, so the step runs winget
itself with `--source msstore`.

`dot apply --upgrade` runs `mas update 1274495053` on macOS. Both stores also update the app on
their own.

## Gotchas

- **Sign in to the App Store first** (macOS). `mas get` needs an Apple Account signed in to the
  App Store app, and macOS may ask for Touch ID or the Apple Account password for the free
  "purchase" (System Settings > Apple Account > Media & Purchases > Free Downloads). With no
  account signed in the step fails; sign in and run `dot apply microsoft-todo` again.
- **Over ssh** (`dot apply --host`): the App Store sign-in and its password prompts belong to
  the logged-in GUI session, so `mas get` fails over ssh unless the account is already signed in
  there and free downloads need no password. Run this bundle from the Mac's own Terminal
  otherwise. `mas` also needs root: dot asks for the sudo password up front (`sudo: true`).
- **Already installed by hand**: the step checks `/Applications/Microsoft To Do.app` (macOS) and
  `winget list` against the msstore source (Windows), so an existing install is left alone.
- **macOS 14 or later** for `mas`: Homebrew's `mas` 7 formula has bottles only for macOS 14+;
  on macOS 13 Homebrew builds it from source, which needs a newer Xcode than macOS 13 runs, so
  the step fails there. Install To Do from the App Store app by hand on such a Mac.
- **Microsoft Store disabled** (Windows, some managed machines turn the store or winget's
  `msstore` source off): the step fails; install To Do from the company portal instead.
