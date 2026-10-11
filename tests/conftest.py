import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIX = ROOT / "tests" / "fixtures"


@pytest.fixture
def fixture_text():
    return lambda name: (FIX / name).read_text(encoding="utf-8")
