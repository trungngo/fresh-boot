# rust

The Rust toolchain through [rustup](https://rustup.rs), the official installer on Linux and
macOS. Ubuntu packages `rustc`, but it lags well behind (25.10 carries 1.85.1).

## Installs

- Linux: `build-essential`. rustup brings no linker, and without `cc` the first `cargo build`
  fails with "linker `cc` not found". (macOS has one from the Command Line Tools, which Homebrew
  already required.)
- `CARGO_HOME=~/.cargo` (`env:`) and `~/.cargo/bin` on `PATH` (`path:`), before the installer,
  so the rest of the run and every shell (`dot env`) find `rustup`, `cargo` and what
  `cargo install` puts there.
- `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --no-modify-path
  --profile default -c rust-analyzer,rust-src`: the `default` profile (rustc, cargo, rustfmt,
  clippy) plus `rust-analyzer` and `rust-src`. Skipped while `$CARGO_HOME/bin/rustup` exists.
- `dot apply --upgrade`: `rustup self update && rustup update stable && rustup component add
  rust-analyzer rust-src` (the last is a no-op unless a component was removed).

## Gotchas carried over

- **`--no-modify-path`**: otherwise rustup-init prepends `~/.cargo/bin` in `~/.profile`,
  `~/.bashrc` and `~/.zshenv`. The `path:` / `env:` steps do that job for dot and for zsh
  (through `dot env`), so nothing writes into shell profiles.
- rustup updates itself and the toolchain, so nothing is pinned: `stable` is whatever is current.
- The old installer ignored a failing `rustup self update` (`|| true`). Here the upgrade stops on
  it: rustup is always the one this bundle installed (`$CARGO_HOME/bin/rustup`), where
  self-update works; a distro- or brew-packaged rustup (which refuses to self-update) is not
  used by this bundle.
- Not on Windows: rustup there needs the MSVC build tools (Visual Studio), which nothing here
  installs.
