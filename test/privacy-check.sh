#!/usr/bin/env bash
# Scans a repository for personal data before it is published (docs/private-overlay.md).
#
#   test/privacy-check.sh [--history REF]... [REPO]        default REPO: this repository
#
# Every tracked and untracked (not ignored) file under REPO, .git excluded, and every file
# path, is checked for the rules below. A binary file (one with a NUL byte: .pyc, images, ...)
# is not skipped: every run of 4+ printable characters in it is checked like a line.
#
# --history REF (repeatable) also checks what a push of REF publishes: the author and committer
# name and e-mail and the message of every commit reachable from REF, and the user.name /
# user.email git would put on the next commit. Run it on the branch you are about to publish.
#
#   email     an e-mail address outside example.com / example.org / example.net, *.example,
#             *.invalid, *.test and noreply addresses
#   path      /Users/<name>/, /home/<name>/, C:\Users\<name> with a name that is not a
#             placeholder (me, user, tester, a single letter, ...: PLACEHOLDERS below)
#   host      a private-looking host name: *.internal, *.lan, *.corp, *.intranet, *.home.arpa,
#             or a self-hosted gitlab.<domain> (example.* hosts are fine)
#   denylist  a literal from the LOCAL denylist, matched case-insensitively as a whole word
#             (only letters and digits join a word, so `_`, `-`, `.` are boundaries, and a
#             camelCase word is split: `JaneDoeMBP` holds the words Jane, Doe, MBP). An entry
#             of 6+ letters and digits also matches inside any word once separators are dropped
#             (`Jane Doe` finds `janedoe`, `Jane_Doe`, `JaneDoeMBP`); `*entry` does that for a
#             shorter one. Default ~/.config/dot/privacy-denylist, override with
#             PRIVACY_DENYLIST. It holds the real names, companies, hosts and codenames, so it
#             lives outside every
#             repository and is never committed. Missing: a warning, and only the generic
#             checks run.
#
# Intentional references are listed in the committed allowlist test/privacy-allowlist (and
# REPO/.privacy-allowlist when REPO has one; PRIVACY_ALLOWLIST adds another file): one literal
# per line, e.g. the URL the tools are published at. The path rule runs on the line as it is;
# the other rules run after each allowlisted literal is removed, and only where it stands on
# its own: not inside a longer word, and a bare `owner/repo` slug not right after a `/` (so
# `/Users/<name>/repo` or `~/src/<name>/repo` is never cleared by it).
# Exit 0 when clean, 1 listing every hit, 2 on a usage error.
set -euo pipefail

refs=()
while [ $# -gt 0 ]; do
  case $1 in
    --history) [ $# -ge 2 ] || { echo "privacy-check: --history needs a REF" >&2; exit 2; }
               refs+=("$2"); shift 2 ;;
    --history=*) refs+=("${1#--history=}"); shift ;;
    -h|--help) sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 0 ;;
    --) shift; break ;;
    -*) echo "privacy-check: unknown option: $1" >&2; exit 2 ;;
    *) break ;;
  esac
done
[ $# -le 1 ] || { echo "privacy-check: too many arguments" >&2; exit 2; }

here=$(cd "$(dirname "$0")" && pwd)
repo=${1:-$(dirname "$here")}
[ -d "$repo" ] || { echo "privacy-check: no such directory: $repo" >&2; exit 2; }
repo=$(cd "$repo" && pwd)
git -C "$repo" rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "privacy-check: not a git repository: $repo" >&2; exit 2; }

denylist=${PRIVACY_DENYLIST:-$HOME/.config/dot/privacy-denylist}
allowlists=("$here/privacy-allowlist")
[ -f "$repo/.privacy-allowlist" ] && allowlists+=("$repo/.privacy-allowlist")
[ -n "${PRIVACY_ALLOWLIST:-}" ] && allowlists+=("$PRIVACY_ALLOWLIST")

# The denylist holds the real identifiers: it must never sit inside a git work tree.
if [ -f "$denylist" ] \
   && git -C "$(dirname "$denylist")" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "privacy-check: the denylist is inside a git repository; move it out: $denylist" >&2
  exit 2
fi

for r in ${refs[@]+"${refs[@]}"}; do
  git -C "$repo" rev-parse --verify --quiet "$r^{commit}" >/dev/null \
    || { echo "privacy-check: --history: no such commit: $r" >&2; exit 2; }
done

refs_joined=$(IFS=$'\n'; echo "${refs[*]+"${refs[*]}"}")
exec python3 - "$repo" "$denylist" "$refs_joined" "${allowlists[@]}" <<'PY'
import os, re, subprocess, sys

repo, denylist, refs, allowlists = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
refs = [r for r in refs.split("\n") if r]

PLACEHOLDERS = {
    "me", "you", "user", "username", "someone", "tester", "runner", "linuxbrew", "example",
    "alice", "bob", "alex", "jdoe", "name", "shared", "public", "default", "admin",
}
OK_DOMAINS = ("example.com", "example.org", "example.net")
OK_SUFFIXES = (".example", ".invalid", ".test", ".localhost")


def lines_of(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [l.rstrip("\n") for l in f]
    except (OSError, UnicodeDecodeError):
        return []


def literals(path):
    return [l.strip() for l in lines_of(path) if l.strip() and not l.lstrip().startswith("#")]


def allow_re(a):
    # A bare owner/repo slug is not cleared right after a "/": there it is the tail of a path
    # such as /Users/<name>/repo or ~/src/<name>/repo. Entries with a host (github.com/o/r) or
    # an API prefix (repos/o/r) are URL paths, so a "/" before them is expected.
    slug = a.count("/") == 1 and "." not in a.split("/", 1)[0]
    left = r"(?<![A-Za-z0-9_/])" if slug else r"(?<![A-Za-z0-9_])"
    if not a[:1].isalnum():
        left = ""
    right = r"(?![A-Za-z0-9_])" if a[-1:].isalnum() else ""
    return re.compile(left + re.escape(a) + right)


allow = [allow_re(a) for a in
         sorted({a for p in allowlists for a in literals(p)}, key=len, reverse=True)]
deny = []
if os.path.isfile(denylist):
    deny = literals(denylist)
else:
    print("privacy-check: warning: no denylist at %s (only generic checks run)" % denylist,
          file=sys.stderr)


def compact(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def camel_split(s):
    # JaneDoeMBP -> Jane Doe MBP, host2Name -> host2 Name
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", s)


deny_rules = []                  # (entry, whole-word regex, compact substring or None)
for d in deny:
    sub = d.startswith("*")
    d = d[1:].strip() if sub else d
    if not d:
        continue
    word = re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(d), re.I)
    c = compact(d)
    deny_rules.append((d, word, c if c and (sub or len(c) >= 6) else None))

email_re = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})\b")
# Only a root-level /Users or /home ("$SANDBOX/home/x" is a sandbox, not a user's home).
path_re = re.compile(r"(?<![A-Za-z0-9_.})$-])(?:/Users/|/home/|[A-Za-z]:\\+Users\\+)"
                     r"([A-Za-z0-9][A-Za-z0-9._-]*)")
host_re = re.compile(r"\b((?:[A-Za-z0-9-]+\.)+(?:internal|lan|corp|intranet|home\.arpa))\b")
gitlab_re = re.compile(r"\bgitlab\.((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})\b")


def email_ok(local, domain):
    d = domain.lower()
    if local.lower() == "git":                    # git@host:path is an ssh URL, not an address
        return True
    if "noreply" in local.lower() or "no-reply" in local.lower() \
            or d == "users.noreply.github.com" or d.endswith(".noreply.github.com"):
        return True
    return d in OK_DOMAINS or d.endswith(tuple("." + x for x in OK_DOMAINS)) \
        or d.endswith(OK_SUFFIXES)


def scan(text):
    """[(kind, match)] for one line (or path). Paths are checked on the raw text, the rest with
    allowlisted literals removed first."""
    hits = []
    for m in path_re.finditer(text):
        name = m.group(1)
        if len(name) > 1 and name.lower() not in PLACEHOLDERS:     # /home/u is a placeholder
            hits.append(("path", m.group(0)))
    for rx in allow:
        text = rx.sub(" ", text)
    for m in email_re.finditer(text):
        token = re.split(r"[\s'\"`(<]", text[:m.start()])[-1]
        if "://" in token:                  # https://user[:token]@host is a URL, not an address
            continue
        if not email_ok(m.group(1), m.group(2)):
            hits.append(("email", m.group(0)))
    for m in host_re.finditer(text):
        if "example" not in m.group(1).lower():
            hits.append(("host", m.group(1)))
    for m in gitlab_re.finditer(text):
        dom = m.group(1).lower()
        if dom != "com" and not dom.startswith("example.") and dom not in ("com",) \
                and not dom.endswith(OK_SUFFIXES):
            hits.append(("host", m.group(0)))
    if deny_rules:
        split, flat = camel_split(text), compact(text)
        for d, word, c in deny_rules:
            if word.search(text) or word.search(split) or (c and c in flat):
                hits.append(("denylist", d))
    return hits


def strings(data, least=4):
    """The printable runs of a binary file, as `strings` prints them."""
    return [m.group(0).decode("ascii") for m in re.finditer(rb"[\x20-\x7e\t]{%d,}" % least, data)]


files = subprocess.run(["git", "-C", repo, "ls-files", "-z", "-co", "--exclude-standard"],
                       check=True, capture_output=True).stdout.decode().split("\0")
total = 0
for rel in sorted(set(f for f in files if f)):
    path = os.path.join(repo, rel)
    if not os.path.isfile(path) or os.path.islink(path):
        continue
    for kind, what in scan(rel):
        print("%s: [%s, file name] %s" % (rel, kind, what))
        total += 1
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        continue
    if b"\0" in data:                           # binary: check its printable strings
        seen = set()
        for s in strings(data):
            for kind, what in scan(s):
                if (kind, what) not in seen:
                    seen.add((kind, what))
                    print("%s: [%s, binary] %s" % (rel, kind, what))
                    total += 1
        continue
    for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        for kind, what in scan(line):
            print("%s:%d: [%s] %s" % (rel, n, kind, what))
            total += 1


def git(*argv):
    r = subprocess.run(["git", "-C", repo] + list(argv), capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


if refs:
    # What a push publishes besides the tree: who wrote each commit and what it says, and the
    # identity the next commit here would carry.
    for key in ("user.name", "user.email"):
        value = git("config", "--get", key).strip()
        for kind, what in scan(value):
            print("git config %s: [%s] %s" % (key, kind, what))
            total += 1
    log = git("log", "-z", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B", *refs, "--")
    for rec in (r for r in log.split("\0") if r.strip()):
        h, an, ae, cn, ce, body = (rec.lstrip("\n").split("\x1f", 5) + [""] * 6)[:6]
        seen = set()
        for field, value in (("author", an + " <" + ae + ">"),
                             ("committer", cn + " <" + ce + ">")):
            for kind, what in scan(value):
                if (field, kind, what) not in seen:
                    seen.add((field, kind, what))
                    print("commit %s: [%s, %s] %s" % (h[:12], kind, field, what))
                    total += 1
        for line in body.splitlines():
            for kind, what in scan(line):
                if ("message", kind, what) not in seen:
                    seen.add(("message", kind, what))
                    print("commit %s: [%s, message] %s" % (h[:12], kind, what))
                    total += 1

if total:
    print("privacy-check: %d hit(s) in %s" % (total, repo), file=sys.stderr)
    sys.exit(1)
print("privacy-check: clean (%s)" % repo, file=sys.stderr)
PY
