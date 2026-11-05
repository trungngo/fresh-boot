# evernote

[Evernote](https://evernote.com): notes, tasks and an archive, with the desktop app.

## Installs

| | how |
|---|---|
| macOS | cask `evernote` (auto-updates itself; dot adds `--adopt` when the app is already in `/Applications`) |
| Windows | winget `Evernote.Evernote` |

Nothing is linked: the app keeps its account and data in its own store.

## Gotchas

- **Sign in once** in the app; the account is not part of this repository.
- **Desktop only.** Ubuntu is skipped (Evernote has no Linux desktop build here).
- The Windows package ID was not checked on a Windows machine; if `winget` cannot find it,
  look it up with `winget search Evernote`.
