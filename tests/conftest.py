from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Keine Dateien im echten Benutzerordner anlegen (Anschreiben, Tokens)."""
    monkeypatch.setenv("AUTOAPPLICATION_HOME", str(tmp_path / "zuhause"))
