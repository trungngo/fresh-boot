"""tn plugin for the git bundle: ``tn git ...`` (docs/tn.md §7.5).

Remotes, identity, pull/sync, browser pages, .gitignore templates, log, export and feature
branches. It replaces the old ``git-*.sh`` scripts: the per-forge variants (``git-pull-github.sh``)
and the per-person ones (``git-<person>.sh``) are data now: the public forges in
``conf.d/git-forges.toml`` (shipped next to this plugin), the people, own namespaces and the
self-hosted forge in the private ``conf.d/git-private.toml`` (written by hand; docs/private-overlay.md).

Every command works on the git repository around the cwd (``ctx.git_root``; ``-C`` moves it),
except ``init`` (any directory), ``ignore --list`` and ``as --list``. "Remotes" means
``git remote`` without one named ``local``, as the old ``_git-remotes.sh`` did.

Global flags are stripped before this plugin's parser runs, so ``-n`` is always --dry-run:
``tn git log`` takes ``--max-count N`` (alias ``--limit``).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from tn import (Cancelled, Context, Fail, Missing, Plugin, Problem, UsageError, arg,
                can_prompt, capture, clock, confirm, fs, git, need, out, pick, run, split_url)
from tn.match import subsequence
from tn.plugins import projects

plugin = Plugin("git", help="git helpers: remotes, identity, sync, export", requires=["projects"])

GIT_FIX = "dot apply git"
GH_FIX = "dot apply gh"

# `tn git open` page suffixes by forge kind.
PAGES = ("repo", "pr", "ci", "issues")
PAGE_SUFFIX = {
    "github": {"repo": "", "pr": "/pulls", "ci": "/actions", "issues": "/issues"},
    "gitlab": {"repo": "", "pr": "/-/merge_requests", "ci": "/-/pipelines", "issues": "/-/issues"},
    "bitbucket": {"repo": "", "pr": "/pull-requests", "ci": "/pipelines", "issues": "/issues"},
}

# Short forms `tn git ignore` accepts for GitHub's template names.
IGNORE_ALIASES = {
    "node": "Node", "nodejs": "Node", "js": "Node", "javascript": "Node", "npm": "Node",
    "py": "Python", "python": "Python", "python3": "Python", "django": "Python",
    "go": "Go", "golang": "Go", "rust": "Rust", "java": "Java", "maven": "Maven",
    "gradle": "Gradle", "c#": "VisualStudio", "csharp": "VisualStudio", "dotnet": "VisualStudio",
    "cpp": "C++", "c++": "C++", "godot": "Godot", "unity": "Unity", "terraform": "Terraform",
}

STATUS_NAMES = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied",
                "T": "type-changed", "U": "conflicted"}


# == repository helpers =====================================================================


def _root(ctx: Context) -> Path:
    """The git repository around the cwd, or exit 2."""
    root = ctx.git_root
    if root is None:
        raise UsageError("not inside a git repository")
    need("git", GIT_FIX)
    return root


def _out(r) -> str:
    return (r.stdout or "").strip()


def _err_line(r) -> str | None:
    lines = (r.stderr or "").strip().splitlines()
    return lines[-1] if lines else None


def _branch(root) -> str | None:
    """The current branch (also on an unborn branch); None when HEAD is detached."""
    r = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    return (_out(r) or None) if r.returncode == 0 else None


def _need_branch(root) -> str:
    b = _branch(root)
    if b is None:
        raise Fail("HEAD is detached: check out a branch first",
                   hint="git switch <branch>")
    return b


def _remotes(root) -> list:
    """``git remote`` in its order, without one named ``local``."""
    r = git(root, "remote")
    return [n for n in _out(r).splitlines() if n.strip() and n.strip() != "local"]


def _upstream_remote(root, branch: str | None) -> str | None:
    if not branch:
        return None
    r = git(root, "config", "--get", "branch.%s.remote" % branch)
    name = _out(r)
    return name if r.returncode == 0 and name and name != "." else None


def _has_upstream(root) -> bool:
    return git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").returncode == 0


def _primary_remote(root, branch: str | None = None) -> str | None:
    """The upstream's remote, else ``origin``, else the first remote."""
    remotes = _remotes(root)
    up = _upstream_remote(root, branch if branch is not None else _branch(root))
    if up and up in remotes:
        return up
    if "origin" in remotes:
        return "origin"
    return remotes[0] if remotes else None


def _check_remote(root, name: str) -> str:
    remotes = _remotes(root)
    if name not in remotes:
        raise UsageError("no remote %r in this repository" % name, choices=remotes or None,
                         hint=None if remotes else "add one: tn git remote add <forge>")
    return name


def _ref_exists(root, ref: str) -> bool:
    return git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}").returncode == 0


def _remote_url(root, name: str) -> str | None:
    r = git(root, "remote", "get-url", name)
    return (_out(r) or None) if r.returncode == 0 else None


def _git_run(root, *args, check: bool = False) -> int:
    """A changing git command; its output goes to stderr (stdout carries results only)."""
    return run(["git", "-C", str(root), *args], check=check, quiet=True)


# == pull, sync =============================================================================


@plugin.command(help="pull the branch from its upstream, one remote, or every remote")
@arg("--remote", metavar="R", help="pull the branch from remote R")
@arg("--all", action="store_true", help="pull from every remote in turn")
def pull(ctx, args):
    root = _root(ctx)
    if args.remote and args.all:
        raise UsageError("--remote and --all exclude each other")
    branch = _need_branch(root)
    rows = []
    if args.remote or args.all:
        targets = [_check_remote(root, args.remote)] if args.remote else _remotes(root)
        if not targets:
            raise Fail("this repository has no remotes", hint="tn git remote add <forge>")
        for r in targets:
            out.info("pull %s %s" % (r, branch))
            ok = _git_run(root, "pull", r, branch) == 0
            if not ok:
                out.warn("pull from %s failed" % r)
            rows.append({"remote": r, "branch": branch, "ok": ok})
    else:
        if not _has_upstream(root):
            remotes = _remotes(root)
            raise Fail("branch %s has no upstream" % branch,
                       hint="tn git pull --remote <name> (remotes: %s)"
                       % (", ".join(remotes) if remotes else "none; tn git remote add <forge>"))
        up = _upstream_remote(root, branch)
        out.info("pull %s" % branch)
        ok = _git_run(root, "pull") == 0
        rows.append({"remote": up, "branch": branch, "ok": ok})
    out.result(rows)
    return 0 if all(r["ok"] for r in rows) else 1


@plugin.command(help="pull from each remote, then push the branch to each")
@arg("--remote", metavar="R", help="only this remote (default: every remote)")
def sync(ctx, args):
    root = _root(ctx)
    branch = _need_branch(root)
    targets = [_check_remote(root, args.remote)] if args.remote else _remotes(root)
    if not targets:
        raise Fail("this repository has no remotes", hint="tn git remote add <forge>")
    rows = []
    for r in targets:
        out.info("pull %s %s" % (r, branch))
        ok = _git_run(root, "pull", r, branch) == 0
        if not ok:
            out.warn("pull from %s failed: not pushing there" % r)
        rows.append({"remote": r, "branch": branch, "ok": ok, "pushed": False})
    for row in rows:
        if not row["ok"]:
            continue
        out.info("push %s %s" % (row["remote"], branch))
        row["pushed"] = _git_run(root, "push", row["remote"], branch) == 0
        if not row["pushed"]:
            out.warn("push to %s failed" % row["remote"])
    out.result(rows)
    return 0 if all(r["ok"] and r["pushed"] for r in rows) else 1


# == remotes ================================================================================


@plugin.command(name="remote add", help="add the remote of a forge from config (path from the "
                                        "project and repo)")
@arg("forge", complete="forge", help="forge key: gh, work, ... (tn config show)")
@arg("--name", metavar="NAME", help="remote name (default: the forge's remote)")
@arg("--path", metavar="PATH", help="namespace/repo on the forge (default: from the Context)")
@arg("--no-fetch", action="store_true", help="do not fetch the new remote")
def remote_add(ctx, args):
    root = _root(ctx)
    rctx = ctx.for_path(root)
    r = projects.add_remote(rctx, args.forge, repo_dir=root, name=args.name, path=args.path,
                            fetch=not args.no_fetch)
    out.result(r, text=lambda o: o["url"])


def _remote_rows(ctx, root) -> list:
    cfg = ctx.config
    rows = []
    for name in _remotes(root):
        url = _remote_url(root, name)
        f = cfg.forge_for_url(url) if url else None
        _, path = split_url(url or "")
        rows.append({"name": name, "url": url, "forge": f.key if f else None,
                     "path": path if f else None,
                     "web": f.web_url(path) if f and path else None})
    return rows


@plugin.command(name="remote ls", help="remotes with their forge and path")
def remote_ls(ctx, args):
    root = _root(ctx)
    out.records(_remote_rows(ctx, root),
                [("name", "NAME"), ("forge", "FORGE"), ("path", "PATH"), ("url", "URL")],
                empty="No remotes. Add one with: tn git remote add <forge>")


# == open ===================================================================================


def _browse(url: str) -> bool:
    """Open ``url`` in the default browser (patched in tests)."""
    import webbrowser
    try:
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001 - no browser is not an error: the URL is printed anyway
        return False


def _has_display() -> bool:
    env = os.environ
    if env.get("SSH_CONNECTION") or env.get("SSH_CLIENT") or env.get("SSH_TTY"):
        return False
    if sys.platform.startswith("linux") and not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return False
    return True


@plugin.command(name="open", help="open the repo, its PRs/MRs, CI or issues in a browser")
@arg("page", nargs="?", default="repo", choices=PAGES, help="repo (default), pr, ci or issues")
@arg("--remote", metavar="R", help="default: the upstream's remote, else origin, else the first")
@arg("--print", action="store_true", help="print the URL instead of opening it")
def open_(ctx, args):
    root = _root(ctx)
    if args.remote:
        remote = _check_remote(root, args.remote)
    else:
        remote = _primary_remote(root)
        if remote is None:
            raise Fail("this repository has no remotes", hint="tn git remote add <forge>")
    url = _remote_url(root, remote) or ""
    host, path = split_url(url)
    forge = ctx.config.forge_for_url(url) if url else None
    if forge is None:
        raise Fail("no forge in config for host %s" % (host or url or "?"),
                   hint="add a [forges.<key>] table with host = \"%s\" (tn config edit)"
                   % (host or "..."))
    page_url = forge.web_url(path) + PAGE_SUFFIX.get(forge.kind, PAGE_SUFFIX["github"])[args.page]
    obj = {"url": page_url, "remote": remote, "forge": forge.key}
    if ctx.options.json:
        out.result(obj)
        return
    out.line(page_url)
    if args.print:
        return
    if not _has_display():
        out.hint("no display here: open the URL above yourself")
        return
    if ctx.options.dry_run:
        out.would("open %s" % page_url)
        return
    if not _browse(page_url):
        out.hint("could not start a browser: open the URL above yourself")


# == identity ===============================================================================


def _person_keys(p) -> list:
    return [p.key, *p.aliases, p.name, p.email.split("@", 1)[0]]


def match_people(query: str, people: list) -> list:
    """People matching ``query``: an exact key, alias or email wins; else the best tier of
    prefix, substring, subsequence over keys, aliases, names and email local parts."""
    q = query.lower().strip()
    exact = [p for p in people
             if q == p.key.lower() or q in (a.lower() for a in p.aliases) or q == p.email.lower()]
    if exact:
        return exact
    tests = (lambda k: k.startswith(q), lambda k: q in k, lambda k: subsequence(q, k))
    for test in tests:
        hits = [p for p in people if any(test(k.lower()) for k in _person_keys(p) if k)]
        if hits:
            return hits
    return []


def _person_label(p) -> str:
    return "%s  %s <%s>" % (p.key, p.name, p.email)


def _person_json(p) -> dict:
    return {"key": p.key, "name": p.name, "email": p.email}


ME_FIX = "set MY_NAME/MY_EMAIL (dot apply asks for them once; ~/.config/dot/local.env)"


@plugin.command(name="as", help="commit as a person from config in this repo (fuzzy)")
@arg("person", nargs="?", complete="person", help="people key, alias, name or email (me: you)")
@arg("--list", action="store_true", help="list the people instead")
def as_(ctx, args):
    cfg = ctx.config
    people = cfg.people()
    if args.list:
        rows = [p.to_json() for p in people]
        out.records(rows, [("key", "KEY"), ("name", "NAME"), ("email", "EMAIL")],
                    empty="No people. They come from ~/.config/tn/conf.d/git-private.toml "
                          "(write it by hand, see the git bundle's private.toml.example)")
        return
    root = _root(ctx)
    if args.person is not None and args.person.strip().lower() == "me":
        person = cfg.person("me")
        if person is None:
            raise Missing("no identity for me: MY_NAME / MY_EMAIL are not set", ME_FIX)
    else:
        if args.person is None:
            hits = people
        else:
            hits = match_people(args.person, people)
            if not hits:
                close = difflib.get_close_matches(args.person.lower(),
                                                  [p.key for p in people], n=5, cutoff=0.5)
                raise UsageError("no person matches %r" % args.person, choices=close or None,
                                 hint="tn git as --list")
        if len(hits) > 1 and not can_prompt():
            raise UsageError("which person?", choices=[p.key for p in hits])
        person = pick(hits, label=_person_label, prompt="person", what="which person?")
    projects.set_identity(root, person)
    out.result(dict(_person_json(person), repo=str(root)),
               text=lambda o: "committer: %s <%s>" % (o["name"], o["email"]))


def _config_scoped(root, key: str) -> tuple:
    """(value, "local" | "global" | None) of a git config key as git resolves it here."""
    r = git(root, "config", "--show-scope", "--get", key)
    if r.returncode != 0 or not _out(r):
        return None, None
    scope, _, value = _out(r).partition("\t")
    return value, ("local" if scope in ("local", "worktree") else "global")


@plugin.command(help="the identity commits here get, and the project's expected one")
def whoami(ctx, args):
    root = _root(ctx)
    name, name_src = _config_scoped(root, "user.name")
    email, email_src = _config_scoped(root, "user.email")
    source = email_src or name_src or "unset"
    expected = projects.identity_for(ctx.for_path(root))
    matches = None
    if expected is not None:
        matches = bool(email) and email.lower() == expected.email.lower()
    obj = {"name": name, "email": email, "source": source,
           "expected": _person_json(expected) if expected else None, "matches": matches}

    def text(o):
        lines = ["committer: %s <%s> (%s)" % (o["name"] or "-", o["email"] or "-", o["source"])]
        if o["expected"]:
            e = o["expected"]
            lines.append("expected:  %s <%s> (%s)%s" % (
                e["name"], e["email"], e["key"],
                "" if o["matches"] else "  - differs: tn git as %s" % e["key"]))
        return lines
    out.result(obj, text=text)


# == init, ignore ===========================================================================


@plugin.command(help="git init here (idempotent): identity, .gitattributes, optional remote")
@arg("--forge", nargs="?", const="", default=None, metavar="F", complete="forge",
     help="also add the forge's remote (no value: the project's forge)")
def init(ctx, args):
    need("git", GIT_FIX)
    path = ctx.git_root or ctx.cwd
    pctx = ctx.for_path(path)
    forge_key = None
    if args.forge is not None:
        pc = pctx.config.project
        forge_key = args.forge or (pc.forge if pc is not None else None)
        if not forge_key:
            raise UsageError("the project sets no forge: pass --forge <key>",
                             choices=sorted(pctx.config.get("forges") or {}))
        pctx.config.forge(forge_key)                  # unknown key: exit 2 with the choices
    initialized = False
    person = None
    if not (Path(path) / ".git").exists():
        run(["git", "init", "--quiet", str(path)], quiet=True)
        initialized = True
        person = projects.identity_for(pctx)
        projects.set_identity(path, person)
        out.info("Initialized %s" % path)
    attrs = Path(path) / ".gitattributes"
    wrote_attrs = False
    if not attrs.exists():
        fs.write_text(attrs, projects.GITATTRIBUTES)
        wrote_attrs = True
    remote = None
    if forge_key:
        r = projects.add_remote(pctx, forge_key, repo_dir=path)
        remote = {"name": r["name"], "url": r["url"]}
    if not initialized and not wrote_attrs and remote is None:
        out.info("already initialized: %s" % path)
    out.result({"path": str(path), "initialized": initialized, "gitattributes": wrote_attrs,
                "identity": _person_json(person) if person else None, "remote": remote})


def _gh_api(endpoint: str):
    """``gh api <endpoint>`` parsed as JSON; exit 3 when gh is not logged in."""
    r = capture(["gh", "api", endpoint], timeout=60)
    if r.returncode != 0:
        err = (r.stderr or "") + (r.stdout or "")
        if r.returncode == 4 or "401" in err or "Bad credentials" in err \
                or "gh auth login" in err:
            raise Missing("gh is not logged in to github.com", "gh auth login")
        if r.returncode == 127:
            raise Missing("gh is not installed", GH_FIX)
        raise Fail("gh api %s failed" % endpoint, hint=_err_line(r))
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise Fail("gh api %s returned something that is not JSON" % endpoint)


def _template_names() -> list:
    names = _gh_api("gitignore/templates")
    if not isinstance(names, list):
        raise Fail("gh api gitignore/templates: expected a list of names")
    return [str(n) for n in names]


def _match_template(word: str, names: list) -> str:
    by_lower = {n.lower(): n for n in names}
    w = word.lower()
    if w in by_lower:
        return by_lower[w]
    alias = IGNORE_ALIASES.get(w)
    if alias and alias.lower() in by_lower:
        return by_lower[alias.lower()]
    close = difflib.get_close_matches(w, list(by_lower), n=5, cutoff=0.6)
    close += [by_lower[k] for k in by_lower if k.startswith(w) and by_lower[k] not in close][:5]
    raise UsageError("no gitignore template %r" % word,
                     choices=[by_lower.get(c, c) for c in close][:5] or None,
                     hint="tn git ignore --list")


def _header(name: str) -> str:
    return "### %s (github/gitignore)" % name


@plugin.command(help="append GitHub's official .gitignore templates (gh api)")
@arg("templates", nargs="*", metavar="template", help="Python, Node, Go, ... (case-insensitive)")
@arg("--list", action="store_true", help="list every template name")
def ignore(ctx, args):
    need("gh", GH_FIX)
    if args.list:
        names = _template_names()
        if ctx.options.json:
            out.json(names)
        else:
            for n in names:
                out.line(n)
        return
    if not args.templates:
        raise UsageError("which templates? e.g. tn git ignore python node",
                         hint="tn git ignore --list")
    root = _root(ctx)
    names = _template_names()
    wanted = []
    for w in args.templates:
        n = _match_template(w, names)
        if n not in wanted:
            wanted.append(n)
    f = Path(root) / ".gitignore"
    existing = f.read_text(encoding="utf-8") if f.is_file() else ""
    have = {line.strip() for line in existing.splitlines()}
    added, skipped, blocks = [], [], []
    for n in wanted:
        if _header(n) in have:
            out.info("%s: already there" % n)
            skipped.append(n)
            continue
        data = _gh_api("gitignore/templates/%s" % n)
        source = str(data.get("source") or "") if isinstance(data, dict) else ""
        if source and not source.endswith("\n"):
            source += "\n"
        blocks.append("\n%s\n%s" % (_header(n), source))
        added.append(n)
    if blocks:
        text = "".join(blocks)
        if existing and not existing.endswith("\n"):
            text = "\n" + text
        if not existing:
            text = text.lstrip("\n")
        fs.append_text(f, text)
        out.info("added %s to %s" % (", ".join(added), f))
    out.result({"file": str(f), "added": added, "skipped": skipped})


# == log, changed, authors ==================================================================


LOG_FORMAT = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%D%x1f%s%x1e"


def _age_text(v) -> str:
    return clock.fmt_age(clock.age_seconds(clock.parse_iso(v)))


@plugin.command(help="a compact log (default: the last 20 commits)")
@arg("range", nargs="?", metavar="RANGE", help="a revision or range (main..HEAD)")
@arg("--max-count", "--limit", type=int, default=20, metavar="N", dest="max_count",
     help="at most N commits (default 20; -n is tn's --dry-run)")
@arg("--author", metavar="WHO", help="only commits whose author matches (git log --author)")
def log(ctx, args):
    root = _root(ctx)
    if args.max_count < 1:
        raise UsageError("--max-count must be at least 1")
    if args.range is None and not _ref_exists(root, "HEAD"):
        out.records([], [], empty="No commits yet.")
        return
    argv = ["log", "--format=" + LOG_FORMAT, "--max-count=%d" % args.max_count]
    if args.author:
        argv.append("--author=" + args.author)
    if args.range:
        argv.append(args.range)
    argv.append("--")
    r = git(root, *argv)
    if r.returncode != 0:
        raise UsageError("git log failed%s" % (": " + _err_line(r) if _err_line(r) else ""))
    rows = []
    for rec in r.stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        f = rec.split("\x1f")
        if len(f) < 7:
            continue
        ts = clock.parse_iso(f[4])
        rows.append({"hash": f[0], "short": f[1], "author_name": f[2], "author_email": f[3],
                     "date": clock.iso(ts), "age_seconds": clock.age_seconds(ts),
                     "refs": [x.strip() for x in f[5].split(",") if x.strip()],
                     "subject": f[6]})
    out.records(rows, [("short", "COMMIT"), ("date", "DATE", _age_text),
                       ("author_name", "AUTHOR"), ("subject", "SUBJECT")],
                empty="No commits match.")


def parse_status_z(data: str) -> list:
    """Rows from ``git status --porcelain=v2 -z`` (§7.5 ``changed``)."""
    rows = []
    parts = data.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if not entry:
            continue
        kind = entry[0]
        if kind == "?":
            rows.append({"path": entry[2:], "status": "untracked", "staged": False,
                         "unstaged": True, "orig_path": None})
        elif kind in ("1", "2", "u"):
            fields = entry.split(" ", {"1": 8, "2": 9, "u": 10}[kind])
            xy = fields[1]
            path = fields[-1]
            orig = None
            if kind == "2":
                orig = parts[i] if i < len(parts) else None
                i += 1
            if kind == "u":
                rows.append({"path": path, "status": "conflicted", "staged": False,
                             "unstaged": True, "orig_path": None})
                continue
            x, y = xy[0], xy[1]
            code = x if x != "." else y
            rows.append({"path": path, "status": STATUS_NAMES.get(code, "modified"),
                         "staged": x != ".", "unstaged": y != ".", "orig_path": orig})
    return rows


@plugin.command(help="changed and untracked files (staged or not)")
def changed(ctx, args):
    root = _root(ctx)
    r = git(root, "status", "--porcelain=v2", "-z")
    if r.returncode != 0:
        raise Fail("git status failed", hint=_err_line(r))
    rows = parse_status_z(r.stdout)

    def path_text(row):
        if row.get("orig_path") and not ctx.options.json:
            row = dict(row, path="%s -> %s" % (row["orig_path"], row["path"]))
        return row
    if not ctx.options.json:
        rows = [path_text(x) for x in rows]
    out.records(rows, [("status", "STATUS"), ("staged", "STAGED"), ("path", "PATH")],
                empty="Nothing changed.")


@plugin.command(help="commit counts per author, matched to people in config")
def authors(ctx, args):
    root = _root(ctx)
    rows = []
    if _ref_exists(root, "HEAD"):
        r = git(root, "shortlog", "-sne", "HEAD")
        if r.returncode != 0:
            raise Fail("git shortlog failed", hint=_err_line(r))
        by_email = {}
        for p in ctx.config.people():
            by_email.setdefault(p.email.lower(), p.key)
        for line in r.stdout.splitlines():
            m = re.match(r"^\s*(\d+)\s+(.*?)\s*<([^>]*)>\s*$", line)
            if not m:
                continue
            rows.append({"name": m.group(2), "email": m.group(3), "commits": int(m.group(1)),
                         "person": by_email.get(m.group(3).lower())})
    out.records(rows, [("commits", "COMMITS"), ("name", "NAME"), ("email", "EMAIL"),
                       ("person", "PERSON")], empty="No commits yet.")


# == export =================================================================================


@plugin.command(help="zip a ref (default HEAD) into <project>/rel/<project>-<repo>-<date>.zip")
@arg("ref", nargs="?", default="HEAD", metavar="REF", help="default: HEAD")
@arg("-o", "--output", metavar="FILE", complete="file",
     help="the zip file (required outside a project repo)")
def export(ctx, args):
    root = _root(ctx)
    r = git(root, "rev-parse", "--verify", "--quiet", args.ref + "^{commit}")
    commit = _out(r)
    if r.returncode != 0 or not commit:
        raise UsageError("unknown ref %r" % args.ref)
    if args.output:
        f = Path(os.path.expanduser(args.output))
        if not f.is_absolute():
            f = Path(ctx.cwd) / f
    else:
        rctx = ctx.for_path(root)
        if rctx.project_dir is None or rctx.repo is None or rctx.repo_dir != Path(root):
            raise UsageError("not inside a project repository: pass -o <file.zip>")
        date = datetime.fromtimestamp(clock.now()).strftime("%Y%m%d")
        f = Path(rctx.project_dir) / "rel" / ("%s-%s-%s.zip" % (rctx.project, rctx.repo, date))
    f = Path(os.path.normpath(str(f)))
    if f.is_dir():
        raise UsageError("%s is a directory: pass a file name" % f)
    if f.exists() and not ctx.options.dry_run:
        if not confirm("overwrite %s?" % f):
            raise Cancelled()
    fs.mkdir(f.parent)
    run(["git", "-C", str(root), "archive", "--format=zip", "-o", str(f), args.ref], quiet=True)
    size = f.stat().st_size if (not ctx.options.dry_run and f.is_file()) else None
    out.result({"file": str(f), "ref": args.ref, "commit": commit, "bytes": size},
               text=lambda o: o["file"])


# == feature branches =======================================================================


def _base(root) -> str | None:
    """``develop`` (local, else on the primary remote), else the default branch."""
    primary = _primary_remote(root)
    for name in ("develop", projects.default_branch(root)):
        if not name:
            continue
        if _ref_exists(root, "refs/heads/" + name):
            return name
        if primary and _ref_exists(root, "refs/remotes/%s/%s" % (primary, name)):
            return "%s/%s" % (primary, name)
    return None


@plugin.command(name="feature new", help="branch feature/<name> from develop or the default "
                                         "branch (no git-flow)")
@arg("name", help="feature name (the branch is feature/<name>)")
@arg("--from", dest="from_", metavar="BRANCH", help="start from this branch or ref")
def feature_new(ctx, args):
    root = _root(ctx)
    _need_branch(root)
    name = args.name.strip()
    if name.startswith("feature/"):
        name = name[len("feature/"):]
    branch = "feature/" + name
    if not name or git(root, "check-ref-format", "--branch", branch).returncode != 0:
        raise UsageError("invalid feature name %r" % args.name)
    if _ref_exists(root, "refs/heads/" + branch):
        raise Fail("branch %s already exists" % branch, hint="git switch %s" % branch)
    if args.from_:
        if not _ref_exists(root, args.from_):
            raise UsageError("unknown branch or ref %r" % args.from_)
        base = args.from_
    else:
        base = _base(root)
        if base is None:
            raise Fail("no base branch found (no develop, no default branch)",
                       hint="tn git feature new %s --from <branch>" % name)
    run(["git", "-C", str(root), "switch", "--no-track", "-c", branch, base], quiet=True)
    out.result({"branch": branch, "base": base},
               text=lambda o: "%s (from %s)" % (o["branch"], o["base"]))


@plugin.command(name="feature ls", help="local and remote feature/* branches vs their base")
def feature_ls(ctx, args):
    root = _root(ctx)
    remotes = _remotes(root)
    primary = _primary_remote(root)
    r = git(root, "for-each-ref", "--format=%(refname)%1f%(committerdate:iso-strict)",
            "refs/heads/feature/", "refs/remotes/")
    local: dict = {}
    remote: dict = {}
    for line in _out(r).splitlines():
        ref, _, date = line.partition("\x1f")
        if ref.startswith("refs/heads/feature/"):
            local[ref[len("refs/heads/feature/"):]] = (ref, date)
            continue
        if not ref.startswith("refs/remotes/"):
            continue
        rest = ref[len("refs/remotes/"):]
        for rn in sorted(remotes, key=len, reverse=True):
            if rest.startswith(rn + "/feature/"):
                n = rest[len(rn) + len("/feature/"):]
                if n not in remote or rn == primary:
                    remote[n] = (rn, ref, date)
                break
    base = _base(root)
    rows = []
    for n in sorted(set(local) | set(remote)):
        ref, date = local[n] if n in local else remote[n][1:]
        ahead = behind = None
        if base:
            c = git(root, "rev-list", "--left-right", "--count", "%s...%s" % (base, ref))
            m = re.match(r"^(\d+)\s+(\d+)$", _out(c))
            if c.returncode == 0 and m:
                behind, ahead = int(m.group(1)), int(m.group(2))
        ts = clock.parse_iso(date)
        rows.append({"name": n, "branch": "feature/" + n, "local": n in local,
                     "remote": remote[n][0] if n in remote else None, "base": base,
                     "ahead": ahead, "behind": behind, "last_commit_date": clock.iso(ts),
                     "age_seconds": clock.age_seconds(ts)})
    out.records(rows, [("branch", "BRANCH"), ("local", "LOCAL"), ("remote", "REMOTE"),
                       ("ahead", "AHEAD"), ("behind", "BEHIND"),
                       ("last_commit_date", "LAST", _age_text)],
                empty="No feature branches. Start one with: tn git feature new <name>")


# == hooks ==================================================================================


@plugin.status
def _status(ctx):
    root = ctx.git_root
    if root is None:
        return None
    st = projects.repo_state(root, cfg=ctx.config)
    if st.error:
        return "error: %s" % st.error
    parts = [st.branch or ("(detached %s)" % (st.head or "")[:7])]
    parts.append("%d changed" % (st.dirty or 0))
    if st.upstream is None:
        parts.append("no upstream")
    else:
        if st.ahead:
            parts.append("ahead %d" % st.ahead)
        if st.behind:
            parts.append("behind %d" % st.behind)
    return ", ".join(parts)


@plugin.check
def _git_installed(ctx):
    """git installed"""
    need("git", GIT_FIX)
    r = capture(["git", "--version"], timeout=10)
    return _out(r) or None


@plugin.check
def _forge_logins(ctx):
    """forge CLIs logged in"""
    import shutil
    seen, ok, bad = set(), [], []
    for f in ctx.config.forges():
        if f.cli not in ("gh", "glab") or (f.cli, f.host) in seen or not shutil.which(f.cli):
            continue
        seen.add((f.cli, f.host))
        r = capture([f.cli, "auth", "status", "--hostname", f.host], timeout=10)
        (ok if r.returncode == 0 else bad).append(f)
    if bad:
        f = bad[0]
        fix = ("gh auth login --hostname %s" % f.host if f.cli == "gh"
               else "glab auth login --hostname %s --web" % f.host)
        raise Problem("not logged in: %s" % ", ".join("%s %s" % (b.cli, b.host) for b in bad),
                      fix=fix, level="warn")
    if not ok:
        return "no forge CLI installed"
    return ", ".join("%s %s" % (f.cli, f.host) for f in ok)


@plugin.check
def _identities(ctx):
    """repo identities match tn.toml"""
    cfg = ctx.config
    wrong = []
    checked = 0
    for p in projects.iter_projects(cfg):
        person = projects.project_identity(cfg, p.path)
        if person is None:
            continue
        for ref in projects.iter_repos(p.path, "all"):
            checked += 1
            _, email = projects.read_identity(ref.path)
            if not email or email.lower() != person.email.lower():
                wrong.append((ref, email, person))
    if wrong:
        ref, email, person = wrong[0]
        more = " (and %d more)" % (len(wrong) - 1) if len(wrong) > 1 else ""
        raise Problem("identity of %s/%s/%s is %s, tn.toml says %s%s" % (
            ref.project, ref.ws, ref.name, email or "unset", person.email, more),
            fix="tn -C %s git as %s" % (ref.path, person.key), level="warn")
    return "%d repo%s checked" % (checked, "" if checked == 1 else "s") if checked else None


@plugin.completer("person")
def _c_person(ctx, prefix):
    return [(p.key, "%s <%s>" % (p.name, p.email)) for p in ctx.config.people()]


@plugin.completer("forge")
def _c_forge(ctx, prefix):
    return [(f.key, f.host) for f in ctx.config.forges()]
