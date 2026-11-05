#!/bin/bash
# New Ubuntu desktop: curl and git, this repository in ~/.dot, dot, then `dot apply`.
# Run it through install.sh, or copy it into a terminal; extra arguments go to `dot apply`.
set -eu

REPO="${FRESH_BOOT_REPO:-https://github.com/trungngo/fresh-boot.git}"

# 1. curl and git.
sudo apt-get update
sudo apt-get install -y curl git ca-certificates

# 2. This repository (public: no login), then dot from its public release, then apply.
[ -d "$HOME/.dot/.git" ] || git clone "$REPO" "$HOME/.dot"
if ! command -v dot >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/dot" ]; then
  curl -fsSL https://raw.githubusercontent.com/trungngo/dot-cli/main/install.sh | sh
fi
PATH="$HOME/.local/bin:$PATH"

# Piped from curl, stdin is the pipe, not a terminal; dot asks its questions (your name, e-mail,
# this machine's name) on the terminal, so hand it /dev/tty when there is one.
if [ ! -t 0 ] && (: </dev/tty) 2>/dev/null; then
  exec dot apply --profile ubuntu-desktop "$@" </dev/tty
fi
exec dot apply --profile ubuntu-desktop "$@"
