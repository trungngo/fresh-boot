"""``python3 -m tn`` / ``py -3 -m tn``: the same as bin/tn (PYTHONPATH must hold the lib dir)."""

import sys

if sys.version_info < (3, 11):
    sys.stderr.write("tn: needs Python 3.11 or later (this is %d.%d)\n  run: dot apply common\n"
                     % sys.version_info[:2])
    sys.exit(3)

from tn.cli import main  # noqa: E402

sys.exit(main())
