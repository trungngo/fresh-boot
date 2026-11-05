"""tn tunnel (bundles/vscode/plugin.py) against a fake devtunnel on PATH.

The fake's ``host`` prints the three URLs devtunnel prints and then sleeps, so a real detached
process stands in for the host; every one still running is killed in cleanup. Its behaviour is
switched by files in the shared fake state directory: ``devtunnel-logged-out`` and
``host-mode`` (``ok`` | ``die`` | ``silent`` | ``stubborn``, which ignores SIGTERM).
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from tn.plugins import vscode  # noqa: E402 - tn/plugins/__init__.py maps TN_PLUGIN_PATH
from tn.testing import TnTestCase

DEVTUNNEL = r'''
import time
mode_file = state_dir / "host-mode"
if argv[:2] == ["user", "show"]:
    if (state_dir / "devtunnel-logged-out").exists():
        print("Not logged in.")
    else:
        print("Logged in as alex using GitHub.")
    sys.exit(0)
if argv[:1] == ["host"]:
    port = argv[argv.index("-p") + 1]
    mode = mode_file.read_text().strip() if mode_file.exists() else "ok"
    if mode == "die":
        print("Error: tunnel service unavailable", flush=True)
        sys.exit(1)
    if mode == "stubborn":          # ignores SIGTERM: only SIGKILL stops it
        import signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("Hosting port: " + port, flush=True)
    if mode in ("ok", "stubborn"):
        print("Connect via browser: https://k7m2xq04.asse.devtunnels.ms:%s, "
              "https://k7m2xq04-%s.asse.devtunnels.ms" % (port, port), flush=True)
        print("Inspect network activity: https://k7m2xq04-%s-inspect.asse.devtunnels.ms" % port,
              flush=True)
    time.sleep(120)
    sys.exit(0)
if argv[:1] == ["delete"]:
    print("Deleted: " + argv[1])
    sys.exit(0)
print("unexpected: %r" % argv, file=sys.stderr)
sys.exit(2)
'''

T0 = 1790000000.0   # 2026-09-21T...Z


def url(port: int) -> str:
    return "https://k7m2xq04-%d.asse.devtunnels.ms" % port


class TunnelCase(TnTestCase):
    def setUp(self):
        super().setUp()
        self.fake("devtunnel", script=DEVTUNNEL)
        self.tunnels = Path(os.environ["TN_STATE_DIR"]) / "tunnels"
        for name, value in (("POLL_SECONDS", 0.05), ("STOP_SECONDS", 3)):
            p = mock.patch.object(vscode, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.watchers = []
        # --for starts a real detached watcher; record instead (the watcher has its own test).
        self._watcher_patch = mock.patch.object(vscode, "start_watcher",
                                                side_effect=self._fake_watcher)
        self._watcher_patch.start()
        self.addCleanup(self._watcher_patch.stop)
        self.addCleanup(self._kill_all)

    def _fake_watcher(self, st):
        self.watchers.append(dict(st))
        return 0

    def _kill_all(self):
        for f in self.tunnels.glob("*.json") if self.tunnels.is_dir() else []:
            try:
                st = json.loads(f.read_text())
            except ValueError:
                continue
            for key in ("pid", "watcher_pid"):
                pid = st.get(key)
                if pid:
                    try:
                        os.kill(pid, signal.SIGKILL if hasattr(signal, "SIGKILL")
                                else signal.SIGTERM)
                    except OSError:
                        pass
                    vscode._alive(pid)

    def mode(self, mode: str):
        (self.state_dir / "host-mode").write_text(mode)

    def logged_out(self):
        (self.state_dir / "devtunnel-logged-out").write_text("")

    def state(self, port: int) -> dict | None:
        f = self.tunnels / ("%d.json" % port)
        return json.loads(f.read_text()) if f.exists() else None

    def hosts(self):
        return [c for c in self.calls("devtunnel") if c[:1] == ["host"]]

    def open_ok(self, *argv, **kw):
        r = self.tn("tunnel", "open", *argv, **kw)
        self.assertExit(r, 0)
        return r


class Open(TunnelCase):
    def test_happy_path_json(self):
        r = self.open_ok("3000", "--json")
        [rec] = r.json
        self.assertEqual(rec["url"], url(3000))
        self.assertEqual((rec["port"], rec["access"], rec["reused"]), (3000, "private", False))
        self.assertIsNone(rec["expires"])
        self.assertEqual(self.hosts(), [["host", "-p", "3000"]])
        st = self.state(3000)
        self.assertEqual(st["url"], url(3000))
        self.assertTrue(vscode._alive(st["pid"]))
        self.assertTrue((self.tunnels / "3000.log").exists())

    def test_text_prints_the_link_only_on_stdout(self):
        r = self.open_ok("3000")
        self.assertEqual(r.stdout, url(3000) + "\n")
        self.assertIn("private: opening it asks for the account that started it", r.stderr)

    def test_inspect_url_is_not_the_link(self):
        r = self.open_ok("8080", "--json")
        self.assertNotIn("inspect", r.json[0]["url"])

    def test_public(self):
        r = self.open_ok("3000", "--public")
        self.assertEqual(self.hosts(), [["host", "-p", "3000", "--allow-anonymous"]])
        self.assertIn("public: anyone with this link reaches port 3000", r.stderr)
        self.assertEqual(self.state(3000)["access"], "public")

    def test_second_open_reuses(self):
        self.open_ok("3000")
        r = self.open_ok("3000", "--json")
        self.assertTrue(r.json[0]["reused"])
        self.assertEqual(r.json[0]["url"], url(3000))
        self.assertEqual(len(self.hosts()), 1)

    def test_reuse_with_public_warns(self):
        self.open_ok("3000")
        r = self.open_ok("3000", "--public")
        self.assertIn("stays private", r.stderr)

    def test_label_and_context_from_the_project(self):
        self.require_git()
        p = self.make_project("acme", repos=["acme-shop-app"], workspaces=["src-02"])
        r = self.open_ok("3000", "--json", cwd=p.repo("acme-shop-app", "src-02"))
        self.assertEqual(r.json[0]["label"], "acme-shop-app-02-3000")
        self.assertEqual(r.json[0]["context"], "acme/acme-shop-app@02")
        self.assertEqual(self.state(3000)["dir"], str(p.repo("acme-shop-app", "src-02")))

    def test_ports_from_tn_toml(self):
        pdir = self.root_dir() / "acme"
        (pdir / "src").mkdir(parents=True)
        self.project_toml("acme", "[tunnel]\nports = [3000, 8080]\n")
        r = self.open_ok("--json", cwd=pdir)
        self.assertEqual([x["port"] for x in r.json], [3000, 8080])
        self.assertEqual(self.hosts(), [["host", "-p", "3000"], ["host", "-p", "8080"]])

    def test_several_ports(self):
        r = self.open_ok("3000", "8080", "3000")
        self.assertEqual(r.stdout.splitlines(), [url(3000), url(8080)])

    def test_warns_when_nothing_listens(self):
        with mock.patch.object(vscode, "listening", return_value=False):
            r = self.open_ok("3000")
        self.assertIn("nothing is listening on 3000 yet", r.stderr)

    def test_no_warning_when_something_listens(self):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        self.addCleanup(srv.close)
        port = srv.getsockname()[1]
        r = self.open_ok(str(port))
        self.assertNotIn("nothing is listening", r.stderr)

    def test_for_records_expiry_and_starts_watcher(self):
        self.freeze_time(T0)
        r = self.open_ok("3000", "--for", "1h30m", "--json")
        self.assertEqual(r.json[0]["expires"], vscode.clock.iso(T0 + 5400))
        self.assertEqual(self.state(3000)["expires"], vscode.clock.iso(T0 + 5400))
        self.assertEqual([w["port"] for w in self.watchers], [3000])

    def test_for_on_a_live_tunnel_sets_a_new_expiry(self):
        self.freeze_time(T0)
        self.open_ok("3000", "--for", "1h")
        r = self.open_ok("3000", "--for", "2h", "--json")
        self.assertTrue(r.json[0]["reused"])
        self.assertEqual(self.state(3000)["expires"], vscode.clock.iso(T0 + 7200))
        self.assertEqual(len(self.watchers), 2)
        self.assertEqual(len(self.hosts()), 1)

    def test_host_dies(self):
        self.mode("die")
        r = self.tn("tunnel", "open", "3000")
        self.assertExit(r, 1)
        self.assertIn("devtunnel exited before it published a link", r.stderr)
        self.assertIn("  Error: tunnel service unavailable", r.stderr)
        self.assertIsNone(self.state(3000))
        self.assertTrue((self.tunnels / "3000.log").exists())

    def test_timeout(self):
        self.mode("silent")
        with mock.patch.object(vscode, "TIMEOUT_SECONDS", 0.3):
            r = self.tn("tunnel", "open", "3000")
        self.assertExit(r, 1)
        self.assertIn("gave up after", r.stderr)
        self.assertIn("tn tunnel close 3000", r.stderr)
        self.assertIsNotNone(self.state(3000))     # still running; cleanup kills it

    def test_one_port_failing_still_opens_the_others(self):
        self.open_ok("3000")
        self.mode("die")
        r = self.tn("tunnel", "open", "3000", "8080", "--json")
        self.assertExit(r, 1)
        by_port = {x["port"]: x for x in r.json}
        self.assertEqual(by_port[3000]["url"], url(3000))
        self.assertIsNone(by_port[8080]["url"])
        self.assertIn("devtunnel exited", by_port[8080]["error"])

    def test_dry_run_changes_nothing(self):
        r = self.tn("tunnel", "open", "3000", "--for", "2h", "-n", "--json")
        self.assertExit(r, 0)
        self.assertEqual(self.hosts(), [])
        self.assertIn("would: run devtunnel host -p 3000", r.stderr)
        self.assertFalse(self.tunnels.exists() and any(self.tunnels.iterdir()))
        self.assertEqual(self.watchers, [])
        self.assertEqual(r.json[0]["port"], 3000)

    # -- errors ---------------------------------------------------------------------------
    def test_not_a_port(self):
        for bad in ("0", "70000", "http"):
            r = self.tn("tunnel", "open", bad)
            self.assertExit(r, 2)
            self.assertIn("not a port number", r.stderr)

    def test_bad_duration(self):
        for bad in ("2 hours", "0s", "h", "-1h"):
            r = self.tn("tunnel", "open", "3000", "--for", bad)
            self.assertExit(r, 2)
        self.assertEqual(self.hosts(), [])

    def test_no_port_outside_a_project(self):
        r = self.tn("tunnel", "open", "--json")
        self.assertExit(r, 2)
        self.assertIn("no port given", r.error["message"])

    def test_no_port_and_no_tunnel_ports(self):
        pdir = self.root_dir() / "acme"
        (pdir / "src").mkdir(parents=True)
        r = self.tn("tunnel", "open", cwd=pdir)
        self.assertExit(r, 2)
        self.assertIn("no [tunnel] ports in ~/myprojects/acme/tn.toml", r.stderr)

    def test_devtunnel_missing(self):
        self.unfake("devtunnel")
        r = self.tn("tunnel", "open", "3000")
        self.assertExit(r, 3)
        self.assertIn("run: dot apply vscode", r.stderr)

    def test_not_logged_in(self):
        self.logged_out()
        r = self.tn("tunnel", "open", "3000", "--json")
        self.assertExit(r, 3)
        self.assertTrue(r.error["fix"].startswith("devtunnel user login -g"))
        self.assertEqual(self.hosts(), [])


class Durations(TunnelCase):
    def test_parse(self):
        self.assertEqual(vscode.parse_duration("90s"), 90)
        self.assertEqual(vscode.parse_duration("30m"), 1800)
        self.assertEqual(vscode.parse_duration("2h"), 7200)
        self.assertEqual(vscode.parse_duration("1d"), 86400)
        self.assertEqual(vscode.parse_duration("1h30m"), 5400)
        self.assertEqual(vscode.parse_duration("1D2H"), 93600)


class Ls(TunnelCase):
    def test_empty(self):
        r = self.tn("tunnel", "ls")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("No tunnels. Open one with: tn tunnel open <port>", r.stderr)
        self.assertEqual(self.tn("tunnel", "ls", "--json").json, [])

    def test_lists_open_tunnels(self):
        self.freeze_time(T0)
        self.open_ok("3000", "--for", "2h")
        self.open_ok("8080", "--public")
        self.freeze_time(T0 + 720)
        r = self.tn("tunnel", "ls", "--json")
        self.assertExit(r, 0)
        a, b = r.json
        self.assertEqual((a["port"], a["access"], a["age_seconds"], a["url"]),
                         (3000, "private", 720, url(3000)))
        self.assertEqual(a["expires"], vscode.clock.iso(T0 + 7200))
        self.assertEqual((b["port"], b["access"], b["expires"]), (8080, "public", None))
        for key in ("pid", "started", "dir", "label", "context"):
            self.assertIn(key, a)
        text = self.tn("tunnel", "ls").stdout.splitlines()
        self.assertEqual(text[0].split(), ["PORT", "ACCESS", "AGE", "EXPIRES", "LABEL",
                                           "CONTEXT", "LINK"])
        self.assertIn("in 1h48m", text[1])
        self.assertIn("12m", text[1])

    def test_prunes_dead_entries_and_keeps_the_log(self):
        self.open_ok("3000")
        pid = self.state(3000)["pid"]
        os.kill(pid, signal.SIGTERM)
        for _ in range(100):
            if not vscode._alive(pid):
                break
            time.sleep(0.05)
        r = self.tn("tunnel", "ls", "--json")
        self.assertEqual(r.json, [])
        self.assertIsNone(self.state(3000))
        self.assertTrue((self.tunnels / "3000.log").exists())

    def test_closes_expired(self):
        self.freeze_time(T0)
        self.open_ok("3000", "--for", "30m")
        pid = self.state(3000)["pid"]
        self.freeze_time(T0 + 1801)
        r = self.tn("tunnel", "ls", "--json")
        self.assertEqual(r.json, [])
        self.assertIsNone(self.state(3000))
        self.assertFalse(vscode._alive(pid))


class Close(TunnelCase):
    def test_close_one_json(self):
        self.open_ok("3000")
        pid = self.state(3000)["pid"]
        r = self.tn("tunnel", "close", "3000", "--json")
        self.assertExit(r, 0)
        self.assertEqual(r.json, [{"port": 3000, "url": url(3000), "closed": True}])
        self.assertIsNone(self.state(3000))
        self.assertFalse(vscode._alive(pid))
        self.assertTrue((self.tunnels / "3000.log").exists())

    def test_not_forwarded(self):
        r = self.tn("tunnel", "close", "3000")
        self.assertExit(r, 1)
        self.assertIn("port 3000 is not forwarded", r.stderr)

    def test_all(self):
        self.open_ok("3000", "8080")
        r = self.tn("tunnel", "close", "--all", "--json")
        self.assertExit(r, 0)
        self.assertEqual([x["port"] for x in r.json], [3000, 8080])
        self.assertIn("the link is gone for good", r.stderr)
        self.assertEqual(list(self.tunnels.glob("*.json")), [])

    def test_all_with_nothing_open(self):
        r = self.tn("tunnel", "close", "--all")
        self.assertExit(r, 0)
        self.assertIn("No tunnels to close", r.stderr)

    def test_all_and_ports_is_usage(self):
        self.assertExit(self.tn("tunnel", "close", "--all", "3000"), 2)

    def test_pick_needs_a_tty(self):
        self.open_ok("3000", "8080")
        r = self.tn("tunnel", "close", "--json")
        self.assertExit(r, 2)
        self.assertEqual(r.error["message"], "which tunnel?")
        self.assertEqual(len(r.error["choices"]), 2)
        self.assertIsNotNone(self.state(3000))

    def test_pick_on_a_tty(self):
        self.open_ok("3000", "8080")
        r = self.tn("tunnel", "close", tty=True, stdin="2\n")
        self.assertExit(r, 0)
        self.assertIsNotNone(self.state(3000))
        self.assertIsNone(self.state(8080))

    def test_single_tunnel_needs_no_pick(self):
        self.open_ok("3000")
        r = self.tn("tunnel", "close")
        self.assertExit(r, 0)
        self.assertIsNone(self.state(3000))

    def test_dry_run(self):
        self.open_ok("3000")
        pid = self.state(3000)["pid"]
        r = self.tn("tunnel", "close", "3000", "-n")
        self.assertExit(r, 0)
        self.assertIn("would: stop devtunnel host for port 3000", r.stderr)
        self.assertIsNotNone(self.state(3000))
        self.assertTrue(vscode._alive(pid))

    def test_when_expired_is_hidden(self):
        r = self.tn("tunnel", "close", "--help")
        self.assertNotIn("when-expired", r.stdout)


class Watcher(TunnelCase):
    def test_when_expired_closes_at_expiry(self):
        self.freeze_time(T0)
        self.open_ok("3000", "--for", "10m")
        pid = self.state(3000)["pid"]
        slept = []

        def sleep(s):
            slept.append(s)
            self.freeze_time(T0 + 601)
        with mock.patch.object(vscode, "_watch_sleep", side_effect=sleep):
            r = self.tn("tunnel", "close", "3000", "--when-expired")
        self.assertExit(r, 0)
        self.assertEqual(slept, [60])      # capped, re-checked
        self.assertIsNone(self.state(3000))
        self.assertFalse(vscode._alive(pid))

    def test_stands_down_when_the_expiry_changed(self):
        self.freeze_time(T0)
        self.open_ok("3000", "--for", "10m")

        def sleep(s):
            st = self.state(3000)
            st["expires"] = vscode.clock.iso(T0 + 7200)
            (self.tunnels / "3000.json").write_text(json.dumps(st))
            self.freeze_time(T0 + 601)
        with mock.patch.object(vscode, "_watch_sleep", side_effect=sleep):
            r = self.tn("tunnel", "close", "3000", "--when-expired")
        self.assertExit(r, 0)
        self.assertIsNotNone(self.state(3000))

    def test_real_detached_watcher(self):
        """--for 1s through the real watcher process: the tunnel is gone shortly after."""
        self._watcher_patch.stop()
        r = self.open_ok("3000", "--for", "1s")
        st = self.state(3000)
        self.assertTrue(st["watcher_pid"])
        host, watcher = st["pid"], st["watcher_pid"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and self.state(3000) is not None:
            vscode._alive(host)          # reap our own zombie, as init would on a machine
            time.sleep(0.1)
        self.assertIsNone(self.state(3000), r.stderr + (self.tunnels / "3000.log").read_text())
        self.assertFalse(vscode._alive(host))
        for _ in range(50):
            if not vscode._alive(watcher):
                break
            time.sleep(0.1)
        self.assertIn("expired", (self.tunnels / "3000.log").read_text())


class Identity(TunnelCase):
    """A recorded pid is only the host (or watcher) while its command line says so: the state
    files survive a reboot and the pid may since belong to anything."""

    def bystander(self) -> int:
        """An unrelated long-running process, standing in for a reused pid."""
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.addCleanup(lambda: (p.kill(), p.wait()))
        return p.pid

    def forge(self, port: int, **fields):
        st = self.state(port)
        st.update(fields)
        (self.tunnels / ("%d.json" % port)).write_text(json.dumps(st))

    def kill_host(self, port: int):
        pid = self.state(port)["pid"]
        os.kill(pid, signal.SIGKILL)
        for _ in range(100):
            if not vscode._alive(pid):
                break
            time.sleep(0.05)

    def test_reused_pid_after_expiry_is_pruned_not_signalled(self):
        self.freeze_time(T0)
        self.open_ok("3000", "--for", "1h")
        self.kill_host(3000)
        other, other2 = self.bystander(), self.bystander()
        self.forge(3000, pid=other, watcher_pid=other2)
        self.freeze_time(T0 + 7200)
        for argv in (("status",), ("tunnel", "ls", "--json"), ("tunnel", "close", "--all")):
            r = self.tn(*argv)
            self.assertNotIn("expired, closing", r.stderr)
        self.assertIsNone(self.state(3000))
        self.assertTrue(vscode._alive(other))
        self.assertTrue(vscode._alive(other2))

    def test_reused_pid_is_not_reused_or_closed(self):
        self.open_ok("3000")
        self.kill_host(3000)
        other = self.bystander()
        self.forge(3000, pid=other)
        r = self.tn("tunnel", "close", "3000")
        self.assertExit(r, 1)
        self.assertIn("port 3000 is not forwarded", r.stderr)
        self.assertTrue(vscode._alive(other))
        r = self.open_ok("3000", "--json")      # a fresh host, not the stale entry's link
        self.assertFalse(r.json[0]["reused"])
        self.kill_host(3000)
        self.forge(3000, pid=other)
        r = self.open_ok("3000", "--json")
        self.assertFalse(r.json[0]["reused"])
        self.assertEqual(len(self.hosts()), 3)
        self.assertTrue(vscode._alive(other))

    def test_reused_watcher_pid_is_not_signalled(self):
        self.open_ok("3000")
        host = self.state(3000)["pid"]
        other = self.bystander()
        self.forge(3000, watcher_pid=other)
        self.assertExit(self.tn("tunnel", "close", "3000"), 0)
        self.assertFalse(vscode._alive(host))
        self.assertTrue(vscode._alive(other))

    def test_command_line_match(self):
        self.assertTrue(vscode._is_host_cmd("/usr/local/bin/devtunnel host -p 3000", 3000))
        self.assertTrue(vscode._is_host_cmd(
            "devtunnel host -p 3000 --allow-anonymous", 3000))
        self.assertFalse(vscode._is_host_cmd("/usr/local/bin/devtunnel host -p 30000", 3000))
        self.assertFalse(vscode._is_host_cmd("nvim notes/devtunnel host -p 8080", 3000))
        self.assertFalse(vscode._is_host_cmd("nvim", 3000))
        self.assertTrue(vscode._is_watcher_cmd(
            "/usr/bin/python3 -P -m tn tunnel close 3000 --when-expired", 3000))
        self.assertFalse(vscode._is_watcher_cmd(
            "/usr/bin/python3 -P -m tn tunnel close 3001 --when-expired", 3000))

    def test_windows_image_name(self):
        rows = '"devtunnel.exe","4242","Console","1","12,345 K"\r\n'
        done = subprocess.CompletedProcess([], 0, rows, "")
        with mock.patch.object(vscode, "IS_WINDOWS", True), \
                mock.patch.object(vscode, "capture", return_value=done):
            self.assertEqual(vscode._cmdline(4242), "devtunnel.exe")
            self.assertIsNone(vscode._cmdline(4243))
            self.assertTrue(vscode._is_host_cmd("devtunnel.exe", 3000))
            self.assertFalse(vscode._is_host_cmd("Code.exe", 3000))
            self.assertFalse(vscode._is_watcher_cmd("devtunnel.exe", 3000))


class Detached(TunnelCase):
    def test_host_runs_in_the_state_dir(self):
        cwd = self.root_dir()
        cwd.mkdir(parents=True, exist_ok=True)
        self.open_ok("3000", cwd=cwd)
        [call] = [c for c in self.call_records("devtunnel") if c["argv"][:1] == ["host"]]
        self.assertEqual(Path(call["cwd"]).resolve(), self.tunnels.resolve())

    def test_watcher_runs_in_the_state_dir_without_cwd_on_sys_path(self):
        self._watcher_patch.stop()
        with mock.patch.object(vscode, "spawn_detached", return_value=0) as spawn:
            vscode.start_watcher({"port": 3000})
        argv = spawn.call_args.args[0]
        self.assertEqual(argv[1:4], ["-P", "-m", "tn"])
        self.assertEqual(Path(spawn.call_args.kwargs["cwd"]), vscode.tunnels_dir())


class ServiceCleanup(TunnelCase):
    def deletes(self):
        return [c for c in self.calls("devtunnel") if c[:1] == ["delete"]]

    def test_tunnel_id(self):
        self.assertEqual(vscode.tunnel_id(url(3000)), "k7m2xq04.asse")
        self.assertIsNone(vscode.tunnel_id(None))

    def test_graceful_stop_leaves_the_delete_to_devtunnel(self):
        self.open_ok("3000")
        self.assertExit(self.tn("tunnel", "close", "3000"), 0)
        self.assertEqual(self.deletes(), [])

    def test_killed_host_is_deleted_at_the_service(self):
        self.mode("stubborn")
        with mock.patch.object(vscode, "STOP_SECONDS", 0.5):
            self.open_ok("3000")
            pid = self.state(3000)["pid"]
            self.assertExit(self.tn("tunnel", "close", "3000"), 0)
        self.assertFalse(vscode._alive(pid))
        self.assertEqual(self.deletes(), [["delete", "k7m2xq04.asse"]])

    def test_windows_always_deletes(self):
        """TerminateProcess skips devtunnel's shutdown, so tn deletes the tunnel itself."""
        self.open_ok("3000")
        with mock.patch.object(vscode, "IS_WINDOWS", True), \
                mock.patch.object(vscode, "_ours", return_value=True), \
                mock.patch.object(vscode, "_terminate", return_value=True):
            self.assertExit(self.tn("tunnel", "close", "3000"), 0)
        self.assertEqual(self.deletes(), [["delete", "k7m2xq04.asse"]])
        self.assertIsNone(self.state(3000))


class Hooks(TunnelCase):
    def test_status(self):
        self.freeze_time(T0)
        self.assertNotIn("tunnel", self.tn("status").stdout)
        self.open_ok("3000")
        self.freeze_time(T0 + 720)
        r = self.tn("status")
        self.assertExit(r, 0)
        line = [x for x in r.stdout.splitlines() if x.startswith("tunnel")][0]
        self.assertIn("1 open: 3000 %s (private, 12m)" % url(3000), line)
        j = self.tn("status", "--json").json
        self.assertEqual(j["plugins"]["vscode"], ["1 open: 3000 %s (private, 12m)" % url(3000)])

    def test_doctor_ok(self):
        r = self.tn("doctor", "--json")
        rows = [x for x in r.json if x["plugin"] == "tunnel"]
        self.assertEqual([(x["check"], x["status"]) for x in rows],
                         [("devtunnel installed", "ok"), ("devtunnel logged in", "ok")])
        self.assertIn("separate from `code tunnel user login`", rows[1]["detail"])

    def test_doctor_logged_out(self):
        self.logged_out()
        rows = [x for x in self.tn("doctor", "--json").json if x["plugin"] == "tunnel"]
        self.assertEqual(rows[1]["status"], "fail")
        self.assertEqual(rows[1]["fix"], "devtunnel user login -g")

    def test_doctor_missing(self):
        self.unfake("devtunnel")
        rows = [x for x in self.tn("doctor", "--json").json if x["plugin"] == "tunnel"]
        self.assertEqual((rows[0]["status"], rows[0]["fix"]), ("fail", "dot apply vscode"))
        self.assertEqual(rows[1]["status"], "warn")

    def test_completer(self):
        self.open_ok("3000", "8080")
        r = self.tn("__complete", "3", "--", "tn", "tunnel", "close", "30")
        self.assertExit(r, 0)
        self.assertEqual(r.stdout.split("\t")[0], "3000")
