"""TortureTest -- a desktop app stuffed with every Qt control, for pyguitest.

TortureTest exists to give pyguitest (and any accessibility-driven automation
tool) a worst case: one window containing every widget family Qt ships, each
named and role-tagged the way the accessibility tree reports them, so a test
can find a control by name and drive it instead of clicking a coordinate.

It is a test target, not a product. It is deliberately boring -- plain labels,
stable names, no state-dependent renaming -- so a lookup written once keeps
resolving across themes, resizes and platform changes. It is also deliberately
not packaged with pyguitest (see ``pyguitest-torture-test/README.md``).
"""

from __future__ import annotations

__version__ = "0.1.0"
