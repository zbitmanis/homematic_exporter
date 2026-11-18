import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "source" / "fixtures"


@pytest.fixture
def mini_state() -> dict[str, Any]:
    """Hand-written, scrubbed Homematic IP state (3 rooms, 8 devices). Never the real capture."""
    data: dict[str, Any] = json.loads((FIXTURES / "mini_state.json").read_text())
    return data
