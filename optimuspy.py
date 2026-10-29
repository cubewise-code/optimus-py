"""Backward-compatible script entry point.

Prefer: optimuspy <cmd> (after pip install) or python -m optimuspy <cmd>
"""
import sys
from pathlib import Path

# Add src/ to path and ensure it takes priority over the script directory
# (prevents this file from shadowing the optimuspy package)
_src = str(Path(__file__).parent / "src")
_script_dir = str(Path(__file__).parent)

if _src not in sys.path:
    sys.path.insert(0, _src)

# Remove script directory entries that would cause this file to shadow the package
_removed = []
for _entry in ('', '.', _script_dir):
    while _entry in sys.path:
        sys.path.remove(_entry)
        _removed.append(_entry)

from optimuspy.cli import main  # noqa: E402 — must run after sys.path manipulation above

# Restore path entries
for _entry in _removed:
    sys.path.append(_entry)

if __name__ == "__main__":
    sys.exit(main())
