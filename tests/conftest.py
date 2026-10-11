"""Makes the repository root (and its top-level `api` package) importable."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
