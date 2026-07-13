"""Pytest configuration for ATO core tests."""

import sys
from pathlib import Path

# Ensure the standard src-layout package directory is importable in source tests.
_this_dir = Path(__file__).resolve()
_src_dir = _this_dir.parent.parent / "src"

for p in [_src_dir]:
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)
