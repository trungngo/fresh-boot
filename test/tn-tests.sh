#!/bin/sh
# Run the tn tests: core (bundles/tn/tests) and every bundle's plugin tests, then the plugin
# lint. See docs/tn.md §9.
#
#   test/tn-tests.sh [bundle...]     # default: tn, then every bundle with a tests/ directory
#
# Plugins are COPIED (not linked, as dot does on a machine) into a temp plugins/ directory named
# by TN_PLUGIN_PATH; PYTHONPATH is bundles/tn/lib. Uses python3.11 when it is on PATH (the
# oldest Python tn supports), else python3. No test touches the real $HOME or the network.
# Exits non-zero when any suite or the lint fails.
set -u

here=$(cd "$(dirname "$0")" && pwd)
repo=$(dirname "$here")
cd "$repo" || exit 2

if command -v python3.11 >/dev/null 2>&1; then
  PY=python3.11
else
  PY=python3
fi
echo "tn-tests: using $PY ($("$PY" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])'))"
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "tn-tests: $PY is older than 3.11; tn needs 3.11+" >&2
  exit 2
fi
[ "$PY" = python3.11 ] || echo "tn-tests: note: python3.11 not on PATH; 3.12+ syntax is only caught by the 3.11 grammar check"

tmp=$(mktemp -d "${TMPDIR:-/tmp}/tn-tests.XXXXXX") || exit 2
trap 'rm -rf "$tmp"' EXIT INT TERM
mkdir -p "$tmp/plugins"

# 1. Every plugin, copied as a machine gets it: plugin.py -> <b with - as _>.py, plugin/ -> dir.
for b in bundles/*/; do
  b=${b%/}; name=$(basename "$b" | tr '-' '_')
  if [ -f "$b/plugin.py" ]; then
    cp "$b/plugin.py" "$tmp/plugins/$name.py"
  elif [ -f "$b/plugin/__init__.py" ]; then
    mkdir -p "$tmp/plugins/$name"
    (cd "$b/plugin" && tar cf - --exclude=__pycache__ .) | (cd "$tmp/plugins/$name" && tar xf -)
  fi
done

# 2. Which suites: tn first, then the named bundles or every bundle with tests/.
if [ $# -gt 0 ]; then
  suites=$*
else
  suites=tn
  for b in bundles/*/tests; do
    [ -d "$b" ] || continue
    name=$(basename "$(dirname "$b")")
    [ "$name" = tn ] || suites="$suites $name"
  done
fi

export PYTHONPATH="$repo/bundles/tn/lib"
export TN_PLUGIN_PATH="$tmp/plugins"
export PYTHONDONTWRITEBYTECODE=1

passed=""; failed=""
for s in $suites; do
  dir="bundles/$s/tests"
  if [ ! -d "$dir" ]; then
    echo "tn-tests: $s: no tests/ directory" >&2
    failed="$failed $s"
    continue
  fi
  echo "== $s"
  # The core suite tests discovery, clashes and missing groups with its own demo plugins, so it
  # runs against an empty plugin directory; plugin suites see every repo plugin (they import
  # each other: projects, for claude/codex/git).
  plugin_path=$tmp/plugins
  [ "$s" = tn ] && plugin_path=$tmp/no-plugins && mkdir -p "$plugin_path"
  if TN_PLUGIN_PATH=$plugin_path "$PY" -m unittest discover -s "$dir" -t "$dir" -p 'test_*.py' </dev/null; then
    passed="$passed $s"
  else
    failed="$failed $s"
  fi
done

# 3. Lint: literal Plugin() arguments, group clashes, requires vs bundle.yml, copy steps,
#    reserved flags, and every plugin and core file compiling under $PY with the 3.11 grammar.
echo "== lint"
lint_ok=1
"$PY" -m tn.lint "$repo" </dev/null || lint_ok=0
if ! "$PY" - "$repo/bundles/tn/lib/tn" "$repo/bundles/tn/bin/tn" <<'EOF'
import ast, sys
from pathlib import Path
bad = 0
for root in sys.argv[1:]:
    p = Path(root)
    files = [p] if p.is_file() else sorted(f for f in p.rglob("*.py") if "__pycache__" not in f.parts)
    for f in files:
        text = f.read_text(encoding="utf-8")
        try:
            compile(text, str(f), "exec", dont_inherit=True)
            ast.parse(text, filename=str(f), feature_version=(3, 11))
        except SyntaxError as e:
            print("lint: %s:%s: %s" % (f, e.lineno, e.msg), file=sys.stderr)
            bad += 1
sys.exit(1 if bad else 0)
EOF
then
  lint_ok=0
fi
if [ "$lint_ok" = 1 ]; then passed="$passed lint"; else failed="$failed lint"; fi

echo
echo "tn-tests: passed:${passed:- none}"
if [ -n "$failed" ]; then
  echo "tn-tests: FAILED:$failed"
  exit 1
fi
echo "tn-tests: all passed"
