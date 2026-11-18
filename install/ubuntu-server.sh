#!/bin/bash
# New Ubuntu server (headless): curl and git, this repository in ~/.dot, dot, then `dot apply`.
# Run it through install.sh, or copy it into a terminal or ssh session; extra arguments go to
# `dot apply`.
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

# 2. This repository (public: no login), then dot from its public release.
[ -d "$HOME/.dot/.git" ] || git clone "$REPO" "$HOME/.dot"
if ! command -v dot >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/dot" ]; then
  run_installer https://raw.githubusercontent.com/trungngo/dot-cli/main/install.sh sh
fi
PATH="$HOME/.local/bin:$PATH"

# 3. This machine's short name (MY_MACHINE) is asked once; a headless run cannot guess it.
# Asked again until it matches dot.yml's pattern (dot would refuse anything else). With no
# terminal it is left to dot, which stops up front and says to pass --var MY_MACHINE=<name>.
conf="${XDG_CONFIG_HOME:-$HOME/.config}/dot"
mkdir -p "$conf"
if ! grep -qs '^MY_MACHINE=' "$conf/local.env" && (: </dev/tty) 2>/dev/null; then
  name=
  until printf '%s' "$name" | grep -Eqx '[A-Za-z0-9][A-Za-z0-9-]*'; do
    printf 'Short name for this machine (letters, digits, dashes; e.g. S1): ' >&2
    read -r name </dev/tty
  done
  printf 'MY_MACHINE=%s\n' "$name" >> "$conf/local.env"
fi

rm -rf "$tmp"

# Piped from curl, stdin is the pipe, not a terminal; dot asks its questions (your name, e-mail,
# this machine's name) on the terminal, so hand it /dev/tty when there is one.
if [ ! -t 0 ] && (: </dev/tty) 2>/dev/null; then
  exec dot apply --profile ubuntu-server "$@" </dev/tty
fi
exec dot apply --profile ubuntu-server "$@"
