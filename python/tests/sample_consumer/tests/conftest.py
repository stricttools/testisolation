"""An ordinary consumer conftest -- nothing testisolation-aware in it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Read at IMPORT time. Under the isolation this is already the throwaway home, which
# is the property test_home_isolation.py asserts.
HOME_SEEN_BY_CONFTEST = os.environ["HOME"]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    directory = tmp_path / "repo"
    directory.mkdir()
    return directory
