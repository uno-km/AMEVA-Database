"""
run.py
------
AMEVA Global DB Inspector — single entry point.

Usage
-----
    python run.py

No command-line arguments required. The workspace is auto-resolved
from this file's location (parent of the project directory).
"""
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `tools.*` imports work.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.app import AMEVAInspectorApp


def main() -> None:
    app = AMEVAInspectorApp(run_py_path=Path(__file__))
    app.run()


if __name__ == "__main__":
    main()
