"""Hintergrundaufgaben: Netz und Datenbank ohne blockierende Oberflaeche."""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

log = logging.getLogger(__name__)


class Task(QThread):
    """Fuehrt eine Funktion aus und meldet Ergebnis oder Fehler."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, function: Callable[[], Any], parent: Any = None) -> None:
        super().__init__(parent)
        self.function = function

    def run(self) -> None:  # pragma: no cover - laeuft im Thread
        try:
            result = self.function()
        except Exception as exc:  # noqa: BLE001 - Fehler an die Oberflaeche
            log.error("Hintergrundaufgabe fehlgeschlagen: %s\n%s", exc, traceback.format_exc())
            self.failed.emit(str(exc) or exc.__class__.__name__)
            return
        self.done.emit(result)
