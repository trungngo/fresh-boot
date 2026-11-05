"""The python plugin: its uv doctor check (docs/tn.md §7.7). tn dj and tn py were removed."""

from __future__ import annotations

import json
import unittest

from tn.testing import TnTestCase


class Doctor(TnTestCase):
    def rows(self):
        r = self.tn("doctor", "--json")
        data = r.json
        rows = data["checks"] if isinstance(data, dict) and "checks" in data else data
        return [row for row in rows if "uv" in json.dumps(row)]

    def test_uv_missing_warns(self):
        rows = self.rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("warn", json.dumps(rows[0]))
        self.assertIn("dot apply python", json.dumps(rows[0]))

    def test_uv_present(self):
        self.fake("uv", stdout="uv 0.9.0\n")
        rows = self.rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertIn("ok", json.dumps(rows[0]))


class Plugin(TnTestCase):
    def test_check_only(self):
        p = self.load_plugin("python")
        self.assertEqual(p.groups, ["python"])
        self.assertEqual(p.commands, [])
        self.assertEqual([h.__name__ for h in p.check_hooks], ["uv_installed"])

    def test_dj_and_py_are_gone(self):
        for group in ("dj", "py"):
            self.assertExit(self.tn(group, "--help"), 2)


if __name__ == "__main__":
    unittest.main()
