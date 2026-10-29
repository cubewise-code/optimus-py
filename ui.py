"""Backward-compatible script entry point for OptimusPy UI.

Prefer: python -m optimuspy.ui (after pip install)
"""
import sys
from pathlib import Path

# Add src/ to path and ensure it takes priority over the script directory
_src = str(Path(__file__).parent / "src")
_script_dir = str(Path(__file__).parent)

if _src not in sys.path:
    sys.path.insert(0, _src)

_removed = []
for _entry in ('', '.', _script_dir):
    while _entry in sys.path:
        sys.path.remove(_entry)
        _removed.append(_entry)

from optimuspy.ui import main  # noqa: E402 — must run after sys.path manipulation above

for _entry in _removed:
    sys.path.append(_entry)

if __name__ == "__main__":
    main()
