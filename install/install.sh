#!/bin/sh
# fresh-boot: one command on a new Mac or Ubuntu machine.
#
#   curl -fsSL https://raw.githubusercontent.com/trungngo/fresh-boot/main/install/install.sh | sh
#
# Detects the platform and runs the matching script of this directory (mac.sh, ubuntu-desktop.sh,
# ubuntu-server.sh). From a checkout it runs the sibling script; piped from curl it downloads it.
# Arguments go on to `dot apply` (`sh -s -- --yes`). Windows: install/windows.ps1 (README).
#
#   FRESH_BOOT_ROLE=server|desktop   override the desktop/server guess on Linux
#   FRESH_BOOT_REF=<branch or tag>   script revision to download when piped (default main)
set -eu

raw="https://raw.githubusercontent.com/trungngo/fresh-boot/${FRESH_BOOT_REF:-main}/install"

case "$(uname -s)" in
  Darwin) script=mac.sh ;;
  Linux)
    if [ -r /etc/os-release ]; then . /etc/os-release; fi
    case " ${ID:-} ${ID_LIKE:-} " in
      *" ubuntu "*|*" debian "*) ;;
      *) echo "fresh-boot: unsupported Linux (${ID:-unknown}); Ubuntu and Debian only" >&2; exit 1 ;;
    esac
    role=${FRESH_BOOT_ROLE:-}
    if [ -z "$role" ]; then
      # A graphical session, or a default target that starts one, is a desktop.
      if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] ||
         [ "$(systemctl get-default 2>/dev/null || true)" = graphical.target ]; then
        role=desktop
      else
        role=server
      fi
    fi
    case "$role" in
      desktop) script=ubuntu-desktop.sh ;;
      server) script=ubuntu-server.sh ;;
      *) echo "fresh-boot: FRESH_BOOT_ROLE must be desktop or server" >&2; exit 2 ;;
    esac ;;
  *) echo "fresh-boot: unsupported platform $(uname -s); on Windows run install/windows.ps1" >&2; exit 1 ;;
esac

here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
if [ -n "$here" ] && [ -f "$here/$script" ]; then
  exec bash "$here/$script" "$@"
fi
command -v curl >/dev/null 2>&1 || { echo "fresh-boot: curl is required (sudo apt-get install -y curl)" >&2; exit 1; }
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
curl -fsSL "$raw/$script" -o "$tmp"
# stdin is the curl pipe here: give the script the terminal, so it can ask its questions.
if [ ! -t 0 ] && (: </dev/tty) 2>/dev/null; then
  bash "$tmp" "$@" </dev/tty
else
  bash "$tmp" "$@"
fi
