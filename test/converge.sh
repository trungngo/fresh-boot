#!/bin/sh
# Whole-profile convergence test in a throwaway sandbox (test/sandbox.sh), with the fakes of
# test/fakebin and a local fixture server (test/fixtures.py) standing in for the GitHub / GitLab
# release APIs, go.dev and the devtunnel download. Nothing real is installed; the network is
# not used for installs; the real $HOME is never touched.
#
#   test/converge.sh <mac|mac-intel|desk|srv> [dot apply args, e.g. bundle names]
#
# Runs: a fresh `apply --yes`, the installed `tn --help` (when tn was applied; it must write no
# bytecode under ~/.local/share/tn), a second `apply --yes` that must change nothing, then
# `status`, which must be in sync. Exit status 0 only when all of these hold.
#
# Environment: DOT (the dot binary), SANDBOX (default ${TMPDIR:-/tmp}/dot-converge-<preset>),
# PORT (fixture server port, default 18765), LOCAL_ENV (extra lines for the sandbox's
# ~/.config/dot/local.env; example values only).
set -eu

here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
[ $# -ge 1 ] || { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
preset=$1; shift
case "$preset" in mac|mac-intel|desk|srv) ;; *) echo "preset must be mac, mac-intel, desk or srv" >&2; exit 2 ;; esac

SANDBOX=${SANDBOX:-${TMPDIR:-/tmp}/dot-converge-$preset}
PORT=${PORT:-18765}
export SANDBOX
rm -rf "$SANDBOX"
mkdir -p "$SANDBOX/home/.config/dot" "$SANDBOX/state"
[ -z "${LOCAL_ENV:-}" ] || printf '%s\n' "$LOCAL_ENV" > "$SANDBOX/home/.config/dot/local.env"

# The fingerprints fake curl/gpg report for each package_repo key URL: the ones the bundles pin.
awk '
  /^[[:space:]]*key:[[:space:]]*https:/ { url = $2; next }
  url != "" && /^[[:space:]]*fingerprint:[[:space:]]*[0-9A-Fa-f]/ {
    sub(/^[[:space:]]*fingerprint:[[:space:]]*/, ""); gsub(/[[:space:]]/, ""); print url, $0; url = ""; next }
  url != "" && /^[[:space:]]*fingerprint:[[:space:]]*$/ { list = 1; line = url; next }
  list && /^[[:space:]]*-[[:space:]]*[0-9A-Fa-f]/ { sub(/^[[:space:]]*-[[:space:]]*/, ""); gsub(/[[:space:]]/, ""); line = line " " $0; next }
  list { print line; list = 0; url = "" }
' "$repo"/bundles/*/bundle.yml > "$SANDBOX/state/keys"

python3 "$here/fixtures.py" "$PORT" &
server=$!
trap 'kill $server 2>/dev/null || true' EXIT INT TERM
i=0
until curl -fsS "http://127.0.0.1:$PORT/go/VERSION" >/dev/null 2>&1; do
  i=$((i + 1)); [ $i -lt 50 ] || { echo "fixture server did not start" >&2; exit 1; }
  sleep 0.1
done

DOT_GITHUB_API="http://127.0.0.1:$PORT/gh"
DOT_GITLAB_API="http://127.0.0.1:$PORT/gl"
DOT_URL_REWRITE="https://github.com/=http://127.0.0.1:$PORT/ghdl/,https://gitlab.com/=http://127.0.0.1:$PORT/gldl/"
DOT_URL_REWRITE="$DOT_URL_REWRITE,https://tunnelsassetsprod.blob.core.windows.net/=http://127.0.0.1:$PORT/blob/,https://go.dev/=http://127.0.0.1:$PORT/go/,https://dl.google.com/go/=http://127.0.0.1:$PORT/gosum/,https://dl.google.com/linux/=http://127.0.0.1:$PORT/gchrome/,https://zoom.us/=http://127.0.0.1:$PORT/zoom/,https://discord.com/=http://127.0.0.1:$PORT/discord/,https://desktop.docker.com/=http://127.0.0.1:$PORT/dockerdesktop/"
DOT_URL_REWRITE="$DOT_URL_REWRITE,https://data.services.jetbrains.com/=http://127.0.0.1:$PORT/jbdata/,https://download.jetbrains.com/=http://127.0.0.1:$PORT/jbdl/"
export DOT_GITHUB_API DOT_GITLAB_API DOT_URL_REWRITE

sb() { "$here/sandbox.sh" "$preset" "$@"; }
rc=0
echo "== $preset: first apply"
sb apply --yes --plain "$@" > "$SANDBOX/apply1.log" 2>&1 || { rc=1; echo "first apply FAILED"; }
tail -3 "$SANDBOX/apply1.log"
# Run the installed tn once (bytecode on, as on a machine): what it writes must not be drift.
tn_bin=$SANDBOX/home/.local/bin/tn
if [ -x "$tn_bin" ]; then
  echo "== $preset: tn --help"
  env -u XDG_CACHE_HOME -u XDG_CONFIG_HOME -u XDG_STATE_HOME -u XDG_DATA_HOME -u TN_HOME \
    -u TN_PLUGIN_PATH -u PYTHONPATH -u PYTHONDONTWRITEBYTECODE -u PYTHONPYCACHEPREFIX \
    HOME="$SANDBOX/home" "$tn_bin" --help > "$SANDBOX/tn.log" 2>&1 || { rc=1; echo "tn --help FAILED"; }
  if [ -n "$(find "$SANDBOX/home/.local/share/tn" -name __pycache__ -print 2>/dev/null)" ]; then
    rc=1; echo "tn wrote __pycache__ under ~/.local/share/tn"
  fi
fi
echo "== $preset: second apply"
sb apply --yes --plain "$@" > "$SANDBOX/apply2.log" 2>&1 || { rc=1; echo "second apply FAILED"; }
tail -3 "$SANDBOX/apply2.log"
grep -q ' 0 changed' "$SANDBOX/apply2.log" || { rc=1; echo "second apply changed something"; }
echo "== $preset: status"
sb status "$@" > "$SANDBOX/status.log" 2>&1 || { rc=1; echo "status NOT in sync"; }
tail -3 "$SANDBOX/status.log"
echo "logs: $SANDBOX/{apply1,tn,apply2,status}.log, fake calls: $SANDBOX/calls.log"
exit $rc
