"""
Put the project root on sys.path for tests.

The package directory is hyphenated (`xray-regression-planner`), so it cannot
be imported as a Python package name. The application solves this by running
`python main.py` from this directory with flat imports (`from engine.X import
Y`); this file gives pytest the same import root so tests and application code
agree on how modules are addressed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
