"""Protokoll: was die Anwendung getan hat."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.text import format_date


class LogPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Zeit", "Art", "Meldung"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        refresh = QPushButton("Aktualisieren")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def refresh(self) -> None:
        events = self.window.store.events(400)
        self.table.setRowCount(len(events))
        for row, event in enumerate(events):
            stamp = str(event.get("at") or "")
            time_text = f"{format_date(stamp)} {stamp[11:16]}".strip()
            values = (time_text, str(event.get("kind") or ""), str(event.get("message") or ""))
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.setRowHeight(row, 26)
