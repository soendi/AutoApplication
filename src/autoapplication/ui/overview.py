"""Uebersicht: Kennzahlen, naechster Lauf und letzte Ereignisse."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
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

# Kennzahl, Beschriftung und Zielansicht
CARDS = (
    ("neu", "Neue Stellen", "jobs"),
    ("passend", "Passende Stellen", "jobs"),
    ("entwurf", "Entwürfe", "applications"),
    ("wartet", "Wartet auf Antwort", "applications"),
    ("antwort", "Ungelesene Antworten", "applications"),
)


class ClickableCard(QFrame):
    """Kennzahl-Kachel, die per Klick in die passende Ansicht wechselt."""

    clicked = Signal()

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Zur Ansicht „{title}“ wechseln")

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802 - Qt-Namensschema
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


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
        for key, label, page in CARDS:
            frame = ClickableCard(label)
            frame.clicked.connect(lambda target=page: self.window.show_page(target))
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

        # Grosse Knoepfe; die Zahl der ungelesenen Antworten steht im Knopf.
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.answers_button = QPushButton("Ungelesene Antworten: 0")
        self.answers_button.setObjectName("BigPrimary")
        self.answers_button.clicked.connect(
            lambda: self.window.show_page("applications")
        )
        self.search_button = QPushButton("Jetzt Stellen suchen")
        self.search_button.setObjectName("BigButton")
        self.search_button.clicked.connect(self.window.run_search)
        self.mail_button = QPushButton("Postfach prüfen")
        self.mail_button.setObjectName("BigButton")
        self.mail_button.clicked.connect(self.window.check_mail)
        self.follow_button = QPushButton("Nachfragen vorbereiten")
        self.follow_button.setObjectName("BigButton")
        self.follow_button.clicked.connect(self.window.prepare_follow_ups)
        for button in (
            self.answers_button,
            self.search_button,
            self.mail_button,
            self.follow_button,
        ):
            buttons.addWidget(button, 1)
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
        # Nur ungelesene Antworten zaehlen - gelesene fallen aus der Zahl.
        unread = store.unseen_total()
        self.values["neu"].setText(str(jobs.get("neu", 0)))
        self.values["passend"].setText(str(jobs.get("passend", 0)))
        self.values["entwurf"].setText(str(applications.get("entwurf", 0)))
        self.values["wartet"].setText(str(waiting))
        self.values["antwort"].setText(str(unread))
        self.answers_button.setText(f"Ungelesene Antworten: {unread}")

        daily = self.window.settings.text("automation.daily_time", "07:30")
        upcoming = next_run_at(daily)
        last = self.window.store.meta_get("letzter_lauf", "")
        parts = []
        if not self.window.settings.flag("search.api_enabled", False):
            parts.append("Stellen-API ausgeschaltet (Einstellungen > Suche)")
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
