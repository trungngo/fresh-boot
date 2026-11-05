#!/bin/sh
# Run `dot` against this repository in a throwaway HOME, as another platform, without touching
# the real machine. See CLAUDE.md "Testing".
#
#   test/sandbox.sh <platform> <dot command and args...>
#
#   platform  mac (Apple silicon) | mac-intel | desk (ubuntu-desktop) | srv (ubuntu-server) | win
#             (plan only), or raw DOT_FACTS such as os=linux,family=debian,codename=questing,pkg=apt
#
# Environment:
#   DOT       the dot binary (default: dot on PATH)
#   SANDBOX   sandbox directory (default: ${TMPDIR:-/tmp}/dot-sandbox); HOME is $SANDBOX/home,
#             root-owned files (apt keyrings and sources, /etc/shells, `root: true` copies) go
#             under $SANDBOX/root (DOT_SYSROOT), fake-tool state is $SANDBOX/state and their
#             argv log $SANDBOX/calls.log
#   FAKES=0   do not put test/fakebin first on PATH (default: fakes on, and kept ahead of every
#             `path:` step, so apply never runs a real package manager, sudo, curl or installer)
#   RESET=1   wipe the sandbox first
#   Passed through when set: DOT_URL_REWRITE (send download URLs to a local fixture server),
#   DOT_GITHUB_API / DOT_GITLAB_API (release lookups), GITHUB_TOKEN, DOT_SNAPD (1|0: snapd
#   there or not; default 1). test/converge.sh runs whole profiles with a fixture server.
#
# MY_MACHINE is preset to "test" in the sandbox's local.env, and MY_NAME and MY_EMAIL
# to example values, so runs never stop to ask.
#
# macOS: the sandbox starts without Homebrew (test/fakebrew/brew is not on PATH). Its
# {{ homebrew_prefix }} is overridden in local.env to $SANDBOX/root/opt/homebrew (Apple silicon)
# or $SANDBOX/root/usr/local (Intel), exported as FAKE_BREW_PREFIX: common's "Install Homebrew"
# step runs the fake installer, which puts the fake brew there, and a formula the fake installs
# gets a stub in its bin/ (so Homebrew zsh as the login shell resolves inside the sandbox).
#
# Examples:
#   test/sandbox.sh srv check
#   test/sandbox.sh mac plan zsh
#   RESET=1 test/sandbox.sh srv apply --yes --plain git
#   test/sandbox.sh srv status; cat "${TMPDIR:-/tmp}/dot-sandbox/calls.log"
set -eu

here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
[ $# -ge 2 ] || { sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

case "$1" in
  mac)  facts="os=macos,arch=aarch64,pkg=brew,role=desktop,init=launchd,distro=,family=,version=26.0,codename=,env=" ;;
  mac-intel) facts="os=macos,arch=x86_64,pkg=brew,role=desktop,init=launchd,distro=,family=,version=26.0,codename=,env=" ;;
  desk) facts="os=linux,family=debian,distro=ubuntu,version=24.04,codename=noble,arch=x86_64,pkg=apt,role=desktop,init=systemd,env=" ;;
  srv)  facts="os=linux,family=debian,distro=ubuntu,version=24.04,codename=noble,arch=x86_64,pkg=apt,role=server,init=systemd,env=" ;;
  win)  facts="os=windows,arch=x86_64,pkg=winget,role=desktop,init=other,distro=,family=,version=,codename=,env=" ;;
  *=*)  facts=$1 ;;
  *)    echo "unknown platform: $1" >&2; exit 2 ;;
esac
shift

sandbox=${SANDBOX:-${TMPDIR:-/tmp}/dot-sandbox}
case "$sandbox" in
  /*) ;;
  *) echo "SANDBOX must be an absolute path" >&2; exit 2 ;;
esac
[ "${RESET:-0}" = 1 ] && rm -rf "$sandbox"
mkdir -p "$sandbox/home/.config/dot" "$sandbox/state" "$sandbox/root/etc"
# /etc/shells as a fresh machine has it (the `user` directive adds a shell it lacks).
[ -f "$sandbox/root/etc/shells" ] ||
  printf '/bin/sh\n/bin/bash\n/usr/bin/bash\n/bin/zsh\n/usr/bin/zsh\n' > "$sandbox/root/etc/shells"
touch "$sandbox/calls.log"
local_env="$sandbox/home/.config/dot/local.env"
grep -q '^MY_MACHINE=' "$local_env" 2>/dev/null || echo "MY_MACHINE=test" >> "$local_env"
# The personal prompts (dot.yml), with example values: a sandbox never holds real ones.
grep -q '^MY_NAME=' "$local_env" || echo 'MY_NAME="Alex Doe"' >> "$local_env"
grep -q '^MY_EMAIL=' "$local_env" || echo "MY_EMAIL=alex@example.com" >> "$local_env"

brew_prefix=
case ",$facts," in
  *,os=macos,*)
    case ",$facts," in
      *,arch=x86_64,*) brew_prefix="$sandbox/root/usr/local" ;;
      *) brew_prefix="$sandbox/root/opt/homebrew" ;;
    esac
    grep -v '^homebrew_prefix=' "$local_env" > "$local_env.tmp" || true
    echo "homebrew_prefix=$brew_prefix" >> "$local_env.tmp"
    mv "$local_env.tmp" "$local_env" ;;
esac

path=/usr/bin:/bin:/usr/sbin:/sbin
first=
[ "${FAKES:-1}" = 1 ] && { path="$here/fakebin:$path"; first="$here/fakebin"; }
dot=${DOT:-$(command -v dot || true)}
[ -n "$dot" ] || { echo "no dot binary: set DOT=/path/to/dot" >&2; exit 2; }

h="$sandbox/home"
exec env -i \
  PATH="$path" HOME="$h" USER="${USER:-tester}" LC_ALL=C TERM=dumb \
  XDG_CONFIG_HOME="$h/.config" XDG_STATE_HOME="$h/.local/state" \
  XDG_CACHE_HOME="$h/.cache" XDG_DATA_HOME="$h/.local/share" \
  DOT_REPO="$repo" DOT_FACTS="$facts" DOT_SYSROOT="$sandbox/root" \
  ${first:+DOT_PATH_FIRST="$first"} DOT_SNAPD="${DOT_SNAPD:-1}" \
  ${DOT_URL_REWRITE:+DOT_URL_REWRITE="$DOT_URL_REWRITE"} \
  ${DOT_GITHUB_API:+DOT_GITHUB_API="$DOT_GITHUB_API"} \
  ${DOT_GITLAB_API:+DOT_GITLAB_API="$DOT_GITLAB_API"} \
  ${GITHUB_TOKEN:+GITHUB_TOKEN="$GITHUB_TOKEN"} \
  ${brew_prefix:+FAKE_BREW_PREFIX="$brew_prefix"} \
  FAKE_LOG="$sandbox/calls.log" FAKE_STATE="$sandbox/state" \
  "$dot" "$@"
