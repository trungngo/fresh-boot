#!/bin/bash
# New Ubuntu desktop: curl and git, this repository in ~/.dot, dot, then `dot apply`.
# Run it through install.sh, or copy it into a terminal; extra arguments go to `dot apply`.
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

# 1. curl, git and CA certificates (a re-run that has them asks for no sudo password).
if ! command -v curl >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1 ||
   [ ! -s /etc/ssl/certs/ca-certificates.crt ]; then
  sudo apt-get update
  sudo apt-get install -y curl git ca-certificates
fi

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
  exec dot apply --profile ubuntu-desktop "$@" </dev/tty
fi
exec dot apply --profile ubuntu-desktop "$@"
