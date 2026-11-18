"""Uebersicht: Kennzahlen, naechster Lauf und letzte Ereignisse."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.pipeline import next_run_at
from ..core.text import format_date

CARDS = (
    ("neu", "Neue Stellen"),
    ("passend", "Passende Stellen"),
    ("entwurf", "Entwürfe"),
    ("wartet", "Wartet auf Antwort"),
    ("antwort", "Antworten"),
)


class OverviewPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        self.values: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        title = QLabel("Übersicht")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        for key, label in CARDS:
            frame = QFrame()
            frame.setObjectName("Card")
            inner = QVBoxLayout(frame)
            inner.setContentsMargins(14, 12, 14, 12)
            inner.setSpacing(2)
            number = QLabel("0")
            number.setObjectName("CardNumber")
            caption = QLabel(label)
            caption.setObjectName("Hint")
            inner.addWidget(number)
            inner.addWidget(caption)
            self.values[key] = number
            cards.addWidget(frame, 1)
        layout.addLayout(cards)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.search_button = QPushButton("Jetzt Stellen suchen")
        self.search_button.setObjectName("Primary")
        self.search_button.clicked.connect(self.window.run_search)
        self.mail_button = QPushButton("Postfach prüfen")
        self.mail_button.clicked.connect(self.window.check_mail)
        self.follow_button = QPushButton("Nachfragen vorbereiten")
        self.follow_button.clicked.connect(self.window.prepare_follow_ups)
        for button in (self.search_button, self.mail_button, self.follow_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.next_label = QLabel("")
        self.next_label.setObjectName("Hint")
        layout.addWidget(self.next_label)

        events_title = QLabel("Letzte Ereignisse")
        events_title.setObjectName("SectionLabel")
        layout.addWidget(events_title)

        self.events = QListWidget()
        self.events.setAlternatingRowColors(False)
        layout.addWidget(self.events, 1)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        store = self.window.store
        jobs = store.job_counts()
        applications = store.application_counts()
        waiting = (
            applications.get("gesendet", 0)
            + applications.get("nachgefasst", 0)
            + applications.get("info", 0)
        )
        answers = (
            applications.get("zusage", 0)
            + applications.get("einladung", 0)
            + applications.get("absage", 0)
        )
        self.values["neu"].setText(str(jobs.get("neu", 0)))
        self.values["passend"].setText(str(jobs.get("passend", 0)))
        self.values["entwurf"].setText(str(applications.get("entwurf", 0)))
        self.values["wartet"].setText(str(waiting))
        self.values["antwort"].setText(str(answers))

        daily = self.window.settings.text("automation.daily_time", "07:30")
        upcoming = next_run_at(daily)
        last = self.window.store.meta_get("letzter_lauf", "")
        parts = []
        if upcoming:
            parts.append(
                f"Nächster automatischer Lauf: {upcoming.strftime('%d.%m.%Y %H:%M')}"
            )
        if last:
            parts.append(f"Letzte Suche: {format_date(last)}")
        self.next_label.setText(" · ".join(parts))

        self.events.clear()
        for event in store.events(20):
            kind = str(event.get("kind") or "").strip()
            message = str(event.get("message") or "").strip()
            stamp = str(event.get("at") or "")[11:16]
            prefix = f"{format_date(str(event.get('at') or ''))} {stamp}".strip()
            item = f"{prefix}  {message}"
            if kind in {"fehler", "hinweis"}:
                item = f"⚠ {item}"
            self.events.addItem(item)
