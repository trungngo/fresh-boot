"""Plugin sources the core tests install with ``TnTestCase.write_plugin``."""

DEMO = '''
"""A demo plugin for core tests."""
import os
from tn import Plugin, arg, out, run, need, pick, confirm, handoff, Session, Problem, Missing, Fail

plugin = Plugin("demo", help="demo commands", groups=["demo", "dd"])

@plugin.command(help="list things")
def ls(ctx, args):
    out.records([{"name": "a", "n": 1}, {"name": "b", "n": None}],
                [("name", "NAME"), ("n", "N")], empty="No things.")

@plugin.command(help="an empty list")
def empty(ctx, args):
    out.records([], [("name", "NAME")], empty="Nothing here. Make one with: tn demo new")

@plugin.command(name="show")
@arg("target", nargs="?", complete="thing", help="what to show")
@arg("--loud", action="store_true")
@arg("--level", metavar="N", complete=lambda ctx, prefix: ["low", "high"])
def show_(ctx, args):
    """show one thing"""
    out.result({"target": args.target, "loud": args.loud, "level": args.level,
                "context": ctx.name}, lambda o: "target=%s" % o["target"])

@plugin.command(name="remote add")
@arg("forge", complete="forge")
def remote_add(ctx, args):
    out.line("add " + args.forge)

@plugin.command(name="remote ls")
def remote_ls(ctx, args):
    out.line("remote list")

@plugin.command(help="run echo")
@arg("words", nargs="*")
def say(ctx, args):
    return run(["echo", *args.words])

@plugin.command(help="fail with each exit code")
@arg("kind", choices=["fail", "usage", "missing", "boom", "code", "interrupt"])
def err(ctx, args):
    if args.kind == "fail":
        raise Fail("it broke", hint="try again")
    if args.kind == "usage":
        from tn import UsageError
        raise UsageError("which one?", choices=["x", "y"])
    if args.kind == "missing":
        raise Missing("widget is not installed", "dot apply widget")
    if args.kind == "code":
        return 7
    if args.kind == "interrupt":
        raise KeyboardInterrupt()
    raise RuntimeError("kaboom")

@plugin.command(help="pick one")
def choose(ctx, args):
    item = pick(["alpha", "beta", "gamma"], prompt="thing", what="which thing?")
    out.line(item)

ROWS = {"alpha": "the first letter", "beta": "the second letter"}

@plugin.command(help="pick one by a described label; the choices are the values")
@arg("name", nargs="?")
def labelled(ctx, args):
    if args.name is not None:
        if args.name not in ROWS:
            from tn import UsageError
            raise UsageError("no %s" % args.name)
        out.line(args.name)
        return
    item = pick(sorted(ROWS), label=lambda k: "%s  %s" % (k, ROWS[k]), prompt="thing",
                what="which thing?")
    out.line(item)

@plugin.command(help="pick one with an explicit value")
@arg("num", nargs="?")
def valued(ctx, args):
    if args.num is not None:
        out.line(args.num)
        return
    item = pick([1, 2], label=lambda n: "number %d (odd)" % n if n % 2 else "number %d" % n,
                value=lambda n: str(n), prompt="num", what="which number?")
    out.line(item)

@plugin.command(help="confirm")
def sure(ctx, args):
    out.line("yes" if confirm("really do it?") else "no")

@plugin.command(help="hand off")
@arg("prog")
def go(ctx, args):
    handoff([args.prog, "--flag"], cwd=str(ctx.path))

@plugin.command(help="cd somewhere")
@arg("where")
def jump(ctx, args):
    ctx.request_cd(args.where)

@plugin.command(help="show the context")
def where(ctx, args):
    out.result(ctx.to_json(), lambda o: o["name"] or "-")

@plugin.command(name="", group="dd", passthrough=True, help="default command")
@arg("--opt")
def dd_default(ctx, args):
    out.result({"opt": args.opt, "rest": args.rest})

@plugin.command(group="dd", help="a real verb of dd")
def verb(ctx, args):
    out.line("dd verb")

@plugin.status
def status_here(ctx):
    return "demo here: %s" % (ctx.name or "-")

@plugin.status
def status_none(ctx):
    return None

@plugin.status
def status_boom(ctx):
    raise RuntimeError("status exploded")

@plugin.check
def check_ok(ctx):
    """demo ok"""
    return "all fine"

@plugin.check
def check_missing(ctx):
    """widget installed"""
    raise Missing("widget is not installed", "dot apply widget")

@plugin.check
def check_warn(ctx):
    """demo warn"""
    raise Problem("something is odd", fix="tn demo fix", level="warn")

@plugin.sessions
def sessions(ctx):
    return [Session(kind="demo", id="demo-one", name="Demo One", context="p/r", dir="/x",
                    started=1000.0, attached=True, status="idle",
                    attach=["tmux", "attach-session", "-t", "=demo-one"], extra={"uuid": "abcd-1234"}),
            Session(kind="demo", id="demo-two", name="Demo Two", started=None,
                    attach=["tmux", "attach-session", "-t", "=demo-two"])]

@plugin.completer("thing")
def complete_thing(ctx, prefix):
    return [("apple", "a fruit"), "apricot", "banana"]
'''

CHECK_ONLY = '''
from tn import Plugin
plugin = Plugin("quiet", help="only a check")

@plugin.check
def fine(ctx):
    """quiet fine"""
'''

NEEDS_BASE = '''
from tn import Plugin, out
from tn.plugins import base
plugin = Plugin("child", help="needs base", requires=["base"])

@plugin.command()
def hi(ctx, args):
    out.line(base.greeting())
'''

BASE = '''
from tn import Plugin
plugin = Plugin("base", help="the base")

def greeting():
    return "hello from base"
'''

BROKEN_IMPORT = '''
from tn import Plugin
plugin = Plugin("bad", help="breaks on import")
raise ImportError("no such thing")
'''

NOT_LITERAL = '''
from tn import Plugin
NAME = "nl"
plugin = Plugin(NAME, help="not literal")
'''
