#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""``kaleta-admin`` from a checkout: ``uv run python scripts/tenant_admin.py --help``.

The commands live in :mod:`kaleta.cli.tenant_admin`, which the package installs
as ``kaleta-admin`` — the way to run them in a container.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from kaleta.cli.tenant_admin import main

if __name__ == "__main__":
    raise SystemExit(main())
