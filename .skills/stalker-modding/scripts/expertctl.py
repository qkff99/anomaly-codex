#!/usr/bin/env python3
"""Run the bundled Expertise Compiler without a global installation."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "plugins" / "expertise-compiler" / "src"

if not PACKAGE_ROOT.is_dir():
    raise SystemExit(f"bundled Expertise Compiler is missing: {PACKAGE_ROOT}")

sys.path.insert(0, str(PACKAGE_ROOT))

from expertctl.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
