#!/usr/bin/env bash
# Regression tests for test/privacy-check.sh, in scratch git repositories under a temp dir with
# a made-up denylist (Jane Doe, Acmecorp). Nothing reads the real denylist or $HOME.
#
#   test/privacy-check-tests.sh
#
# Personal-looking fixtures are assembled at run time (U=/Users, AT=@) so this file itself
# passes the check. Exit 0 when every case passes, 1 otherwise.
set -u

here=$(cd "$(dirname "$0")" && pwd)
check=$here/privacy-check.sh
tmp=$(mktemp -d "${TMPDIR:-/tmp}/privacy-tests.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT INT TERM

U=/Users
AT=@
mkdir -p "$tmp/deny"
printf '%s\n' "Jane Doe" "janedoe" "acmecorp" "*zeta" > "$tmp/deny/denylist"
printf '%s\n' "github.com/janedoe/tool" "repos/janedoe/tool" "janedoe/tool" > "$tmp/deny/allow"
export PRIVACY_DENYLIST=$tmp/deny/denylist PRIVACY_ALLOWLIST=$tmp/deny/allow
export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_NOSYSTEM=1

pass=0; fail=0
n=0
new_repo() {                                   # new_repo: sets $r to a new empty repository
  n=$((n + 1))
  r=$tmp/r$n
  git init -q "$r"
  git -C "$r" config user.name "Example Dev"
  git -C "$r" config user.email "dev${AT}example.com"
}
one_file() {                                   # one_file CONTENT: sets $r to a repo with a.txt
  new_repo; printf '%s\n' "$1" > "$r/a.txt"
}
commit() {                                     # commit MESSAGE in $r
  echo ok > "$r/a.txt"; git -C "$r" add a.txt; git -C "$r" commit -qm "$1"
}
expect() {                                     # expect NAME RC PATTERN -- privacy-check args
  local name=$1 rc=$2 pat=$3 out got; shift 4
  out=$("$check" "$@" 2>&1); got=$?
  if [ "$got" = "$rc" ] && { [ -z "$pat" ] || printf '%s' "$out" | grep -q -- "$pat"; }; then
    pass=$((pass + 1)); echo "ok   $name"
  else
    fail=$((fail + 1)); echo "FAIL $name (exit $got, want $rc${pat:+, /$pat/})"
    echo "$out" | sed 's/^/     /'
  fi
}

# Baseline: clean content, and a published URL and slug on the allowlist.
one_file "see https://github.com/janedoe/tool/releases and \`janedoe/tool\`"
expect "allowlisted URL and slug are clean" 0 "clean" -- "$r"

# An allowlisted owner/repo slug must not clear a home path or the name in it.
one_file "clone $U/janedoe/tool here"
expect "slug inside a home path: path hit" 1 "\[path\]" -- "$r"
expect "slug inside a home path: denylist hit" 1 "\[denylist\] janedoe" -- "$r"
one_file "see ~/src/janedoe/tool"
expect "slug after a / is not cleared" 1 "\[denylist\] janedoe" -- "$r"
one_file "GET /repos/janedoe/tool/releases and https://api.github.com/repos/janedoe/tool"
expect "API path entry is cleared after a /" 0 "clean" -- "$r"
one_file "see https://github.com/janedoe/toolbox"
expect "allowlist entry is not a prefix match" 1 "\[denylist\] janedoe" -- "$r"

# Joined forms of a denied name.
one_file 'host = "janedoe_mac"'
expect "underscore is a word boundary" 1 "\[denylist\] janedoe" -- "$r"
one_file 'name = "JaneDoeMBP"'
expect "camelCase joined name" 1 "\[denylist\]" -- "$r"
one_file 'user = jane.doe'
expect "separated form of a spaced entry" 1 "\[denylist\] Jane Doe" -- "$r"
one_file 'ACMECORP_TOKEN=x'
expect "upper-case prefix of a variable" 1 "\[denylist\] acmecorp" -- "$r"
one_file 'project = "betazetagamma"'
expect "*entry matches inside a word" 1 "\[denylist\] zeta" -- "$r"
one_file 'plain text about zebras'
expect "no false hit on unrelated words" 0 "clean" -- "$r"

# Binary files (.pyc and friends) are scanned, not skipped.
new_repo
printf 'xx\0\0%s/janedoe/src/x.py\0yy' "$U" > "$r/x.cpython-314.pyc"
expect "binary with a home path" 1 "\[path, binary\]" -- "$r"
new_repo
printf '\0\0\1\2plain binary\0' > "$r/b.bin"
expect "binary without personal data is clean" 0 "clean" -- "$r"

# Commit metadata and messages with --history.
new_repo
echo ok > "$r/a.txt"; git -C "$r" add a.txt
GIT_AUTHOR_NAME="Jane Doe" GIT_AUTHOR_EMAIL="jane${AT}acmecorp.com" git -C "$r" commit -qm first
expect "without --history the tree alone is clean" 0 "clean" -- "$r"
expect "--history: author e-mail" 1 "\[email, author\]" -- --history HEAD -- "$r"
expect "--history: author name" 1 "\[denylist, author\] Jane Doe" -- --history HEAD -- "$r"
new_repo; commit "port the acmecorp scripts"
expect "--history: commit message" 1 "\[denylist, message\] acmecorp" -- --history HEAD -- "$r"
new_repo; commit first
git -C "$r" config user.email "jane${AT}acmecorp.com"
expect "--history: user.email of the next commit" 1 "git config user.email" -- --history HEAD -- "$r"
new_repo
git -C "$r" config user.email "123+dev${AT}users.noreply.github.com"
commit first
expect "--history: noreply identity is clean" 0 "clean" -- --history HEAD -- "$r"
expect "--history: unknown ref is a usage error" 2 "no such commit" -- --history nope -- "$r"

echo
echo "privacy-check-tests: $pass passed, $fail failed"
[ "$fail" = 0 ]
