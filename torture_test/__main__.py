"""Run TortureTest from the command line.

From a checkout::

    python -m torture_test
    python -m torture_test --lang ja
"""

from __future__ import annotations

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
