from pathlib import Path

from tn.lint import bundle_requires, lint
from tn.testing import TnTestCase

GOOD_YML = """name: {b}
requires: [common, tn, projects]
steps:
  - label: Copy the tn plugin
    copy:
      ~/.local/share/tn/plugins/{n}.py: plugin.py
"""


class Lint(TnTestCase):
    def bundle(self, name, plugin, yml=None):
        d = self.tmp / "repo" / "bundles" / name
        d.mkdir(parents=True)
        (d / "plugin.py").write_text(plugin)
        (d / "bundle.yml").write_text(
            yml if yml is not None else GOOD_YML.format(b=name, n=name.replace("-", "_")))
        return d

    def test_clean(self):
        self.bundle("claude", 'from tn import Plugin\nplugin = Plugin("claude", requires=["projects"])\n')
        self.bundle("my-tool", 'from tn import Plugin\nplugin = Plugin("my_tool", groups=["mt"])\n')
        self.assertEqual(lint(self.tmp / "repo"), [])

    def test_problems(self):
        self.bundle("a", 'from tn import Plugin\nplugin = Plugin("a", groups=["g"], requires=["zz"])\n')
        self.bundle("b", 'from tn import Plugin, arg\nplugin = Plugin("b", groups=["g", "status"])\n'
                         '@plugin.command()\n@arg("-n")\ndef x(ctx, a):\n    pass\n',
                    yml="name: b\nrequires:\n  - common\n  - tn\nsteps: []\n")
        self.bundle("c", 'from tn import Plugin\nN = "c"\nplugin = Plugin(N)\n')
        self.bundle("d", 'from tn import Plugin\nplugin = Plugin("d")\ntype X = int\n')
        probs = "\n".join(lint(self.tmp / "repo"))
        self.assertIn("plugin requires zz", probs)
        self.assertIn('group "g" is claimed by a, b', probs)
        self.assertIn("shadows a built-in", probs)
        self.assertIn("no copy step to ~/.local/share/tn/plugins/b.py", probs)
        self.assertIn("reserved global flag -n", probs)
        self.assertIn("bundles/c: plugin does not index", probs.replace("\\", "/"))
        self.assertIn("3.11 grammar", probs)

    def test_bundle_requires(self):
        f = self.tmp / "b.yml"
        f.write_text("name: x\nrequires: [common, tn]   # why\n")
        self.assertEqual(bundle_requires(f), ["common", "tn"])
        f.write_text("name: x\nrequires:\n  - common\n  - 'tn'\nafter: [git]\n")
        self.assertEqual(bundle_requires(f), ["common", "tn"])
        f.write_text("name: x\n")
        self.assertEqual(bundle_requires(f), [])
