#!/bin/bash
# New Ubuntu server (headless): curl and git, this repository in ~/.dot, dot, then `dot apply`.
# Run it through install.sh, or copy it into a terminal or ssh session; extra arguments go to
# `dot apply`.
set -eu

REPO="${FRESH_BOOT_REPO:-https://github.com/trungngo/fresh-boot.git}"

# 1. curl and git.
sudo apt-get update
sudo apt-get install -y curl git ca-certificates

# 2. This repository (public: no login), then dot from its public release.
[ -d "$HOME/.dot/.git" ] || git clone "$REPO" "$HOME/.dot"
if ! command -v dot >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/dot" ]; then
  curl -fsSL https://raw.githubusercontent.com/trungngo/dot-cli/main/install.sh | sh
fi
PATH="$HOME/.local/bin:$PATH"

# 3. This machine's short name (MY_MACHINE) is asked once; a headless run cannot guess it.
conf="${XDG_CONFIG_HOME:-$HOME/.config}/dot"
mkdir -p "$conf"
if ! grep -qs '^MY_MACHINE=' "$conf/local.env" 2>/dev/null; then
  printf 'Short name for this machine (e.g. S1): ' >&2
  read -r name </dev/tty
  printf 'MY_MACHINE=%s\n' "$name" >> "$conf/local.env"
fi

exec dot apply --profile ubuntu-server "$@"
