from __future__ import annotations

import pytest

try:  # Qt braucht je nach Rechner zusätzliche Systembibliotheken
    import PySide6.QtWidgets  # noqa: F401
    from autoapplication.ui import main_window as module
except ImportError as exc:  # pragma: no cover - nur ohne Qt-Laufzeit
    pytest.skip(f"Qt nicht lauffähig: {exc}", allow_module_level=True)


class _Signal:
    def __init__(self) -> None:
        self.slots: list = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def emit(self, value) -> None:
        for slot in self.slots:
            slot(value)


class _FakeTask:
    """Ersetzt den QThread: führt den Auftrag sofort und im selben Thread aus."""

    started: list["_FakeTask"] = []

    def __init__(self, function, parent=None) -> None:
        self.function = function
        self.done = _Signal()
        self.failed = _Signal()
        _FakeTask.started.append(self)

    def start(self) -> None:
        self.done.emit(self.function())

    def track(self, task) -> None:  # pragma: no cover - nicht benutzt
        pass


class _Dialog:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status = ""
        self.corrected = ""
        self.tracked: list = []

    def body(self) -> str:
        return self.text

    def set_status(self, message: str) -> None:
        self.status = message

    def apply_correction(self, text: str) -> None:
        self.corrected = text

    def track(self, task) -> None:
        self.tracked.append(task)


class _Pipeline:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def proofread_available(self) -> bool:
        return True

    def proofread(self, text: str) -> str:
        self.texts.append(text)
        return text.replace("wenig", "wenige")


class _Window:
    def __init__(self) -> None:
        self.pipeline = _Pipeline()


def test_proofreading_reads_the_text_before_the_task_starts(monkeypatch) -> None:
    monkeypatch.setattr(module, "Task", _FakeTask)
    _FakeTask.started.clear()
    window = _Window()
    dialog = _Dialog("Ich habe wenig Zeit.")
    module.MainWindow._start_proofreading(window, dialog)

    assert window.pipeline.texts == ["Ich habe wenig Zeit."]
    assert dialog.corrected == "Ich habe wenige Zeit."
    assert dialog.tracked == _FakeTask.started

    # Der Auftrag bekommt den Text, nicht das Eingabefeld.
    task = _FakeTask.started[0]
    cells = [cell.cell_contents for cell in (task.function.__closure__ or ())]
    assert dialog not in cells
    assert "Ich habe wenig Zeit." in cells
