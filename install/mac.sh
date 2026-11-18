#!/bin/bash
# New Mac: Homebrew, this repository in ~/.dot, dot, then `dot apply`.
# Run it through install.sh, or copy it into Terminal; extra arguments go to `dot apply`.
set -euo pipefail

REPO="${FRESH_BOOT_REPO:-https://github.com/trungngo/fresh-boot.git}"

# A remote installer is downloaded whole before it runs: `curl | sh` runs whatever part arrived
# when the connection drops, and `bash -c "$(curl ...)"` runs an empty script (and succeeds)
# when curl fails.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
run_installer() { # <url> <interpreter>
  curl -fsSL "$1" -o "$tmp/installer"
  "$2" "$tmp/installer"
}

# 1. Homebrew (it also installs the Xcode command line tools, so git).
if ! command -v brew >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/brew ] && [ ! -x /usr/local/bin/brew ]; then
  run_installer https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh /bin/bash
fi
for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$($b shellenv)"; done

# 2. This repository (public: no login), then dot from its public release, then apply.
[ -d "$HOME/.dot/.git" ] || git clone "$REPO" "$HOME/.dot"
if ! command -v dot >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/dot" ]; then
  run_installer https://raw.githubusercontent.com/trungngo/dot-cli/main/install.sh sh
fi
PATH="$HOME/.local/bin:$PATH"

rm -rf "$tmp"

# Piped from curl, stdin is the pipe, not a terminal; dot asks its questions (your name, e-mail,
# this machine's name) on the terminal, so hand it /dev/tty when there is one.
if [ ! -t 0 ] && (: </dev/tty) 2>/dev/null; then
  exec dot apply "$@" </dev/tty
fi
exec dot apply "$@"
