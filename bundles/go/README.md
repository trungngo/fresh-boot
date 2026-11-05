# go

The Go toolchain. **Opt-in**: no profile selects it, `dot apply go`.

## Installs

| | how | latest via |
|---|---|---|
| macOS | `brew install go` | Homebrew |
| Windows | winget `GoLang.Go` (the official MSI, into Program Files; it adds itself to `PATH`) | winget |
| Linux | the official tarball `https://go.dev/dl/<version>.linux-<amd64\|arm64>.tar.gz`, unpacked as the tree `/usr/local/go` (root-owned), `/usr/local/go/bin` on `PATH` | `https://go.dev/VERSION?m=text` (first line, e.g. `go1.24.0`) |

Every OS also gets `~/go/bin` on `PATH`: where `go install` puts programs (the default GOPATH).

On Linux the `download` step is satisfied while the recorded download is still what go.dev
serves; when a new version is out, `dot apply` (no `--upgrade` needed: the URL itself changed)
replaces the whole tree. The location is the bundle var `go_root` (default `/usr/local/go`, what
go.dev documents; `--var go_root=...` or `local.env` to change it).

## Gotchas carried over

- **Replace, never extract over.** go.dev says not to untar over an existing tree: stale files
  from the old version linger and break the build. The old script's `rm -rf /usr/local/go`
  first did that by hand (without it, re-running never really upgraded); `replace: true` swaps
  the tree whole and keeps a tree dot did not install as `/usr/local/go.dot-backup`.
- **No pinned version.** This module used to hardcode go1.15.6 (December 2020), amd64 only.
  amd64 and arm64 are both handled (the `goarch` var maps dot's `arch` fact to go.dev's names;
  another architecture fails the plan instead of fetching the wrong build).
- Ubuntu's `golang-go` package lags upstream and splits `GOROOT` awkwardly, hence the tarball.
- The tarball is checked against the SHA-256 go.dev publishes for it
  (`sha256_url: https://dl.google.com/go/{latest}.linux-<arch>.tar.gz.sha256`, read when
  downloading; no digest is written into this repository).
