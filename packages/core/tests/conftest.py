"""Pytest configuration for ATO core tests."""

import sys
from pathlib import Path

# Ensure the src directory is on sys.path
# When pytest runs from project root, we need the path relative to project root
_this_dir = Path(__file__).resolve()
_src_dir = _this_dir.parent / "src"
_project_root = _src_dir.parent.parent  # goes up from packages/core/src to project root

for p in [_src_dir, _project_root]:
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)
