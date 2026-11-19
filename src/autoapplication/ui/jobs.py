"""Stellen: gefundene Anzeigen mit Passung und Aktionen."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.matching import personal_match, priority_key
from ..core.text import format_date
from .theme import FIT_COLORS, FIT_LABELS, fit_level

STATUS_LABELS = {
    "neu": "Neu",
    "ohne_passung": "Ohne Passung",
    "passend": "Passend",
    "beworben": "Beworben",
    "ignoriert": "Ignoriert",
    "archiviert": "Archiviert",
    "zusage": "Zusage (Stelle)",
}

COLUMNS = (
    "Datum",
    "Titel",
    "Firma",
    "Ort",
    "Pensum",
    "Weg",
    "Interesse",
    "Fähigkeit",
    "Status",
)


class JobsPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("In Titel, Firma, Ort oder Stichworten suchen …")
        self.search.textChanged.connect(self.refresh)
        self.status = QComboBox()
        self.status.addItem("Alle Status", "")
        for key, label in STATUS_LABELS.items():
            self.status.addItem(label, key)
        self.status.currentIndexChanged.connect(self.refresh)
        # Zuerst die passenden Stellen zeigen; fremde Branchen stehen unter
        # "Ohne Passung" und lassen sich bewusst einblenden.
        # Noch keine Aktualisierung ausloesen: die Tabelle entsteht erst unten.
        self.status.blockSignals(True)
        index = self.status.findData("passend")
        if index >= 0:
            self.status.setCurrentIndex(index)
        self.status.blockSignals(False)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.status)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_job())
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.prepare_button = QPushButton("E-Mail vorbereiten")
        self.prepare_button.setObjectName("Primary")
        self.prepare_button.clicked.connect(self.prepare)
        self.open_button = QPushButton("Stelle öffnen")
        self.open_button.clicked.connect(self.open_job)
        self.ignore_button = QPushButton("Ignorieren")
        self.ignore_button.clicked.connect(self.ignore)
        for button in (self.prepare_button, self.open_button, self.ignore_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setToolTip(
            "Farbe der Zeile nach Passung:\n"
            "Grün: deutlich über der Schwelle der Vorlage\n"
            "Gelb: Schwelle erreicht\n"
            "Orange: knapp darunter\n"
            "Rot: kein Stichwort passt"
        )
        buttons.addWidget(self.hint)
        layout.addLayout(buttons)

        self._rows: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        status = self.status.currentData() or None
        jobs = self.window.store.list_jobs(
            status=status or None, search=self.search.text()
        )
        interests = self.window.settings.interests()
        skills = self.window.settings.skills()
        decorated = []
        for job in jobs:
            hits = personal_match(job, interests, skills)
            decorated.append((job, hits[0], hits[1]))
        # Interessen zuerst, dann Faehigkeiten, dann die Passung der Vorlage.
        decorated.sort(
            key=lambda item: priority_key(
                item[1],
                item[2],
                int(item[0].get("score") or 0),
                str(item[0].get("published") or ""),
            ),
            reverse=True,
        )
        self._rows = [item[0] for item in decorated]
        min_score = int(self.window.settings.number("matching.min_score", 2) or 2)
        self.table.setRowCount(len(decorated))
        for row, (job, found_interests, found_skills) in enumerate(decorated):
            level = fit_level(int(job.get("score") or 0), min_score)
            tint = QColor(FIT_COLORS[level])
            values = (
                format_date(job.get("published") or job.get("first_seen")),
                job.get("title") or "",
                job.get("company") or "",
                job.get("city") or "",
                job.get("workload") or "",
                (
                    f"{job.get('distance_km'):.0f} km"
                    if job.get("distance_km") is not None
                    else ""
                ),
                str(len(found_interests)) if found_interests else "–",
                str(len(found_skills)) if found_skills else "–",
                STATUS_LABELS.get(str(job.get("status") or ""), str(job.get("status") or "")),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setBackground(tint)
                if column == 6:
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setToolTip(
                        (
                            "Interessen in der Anzeige: "
                            + ", ".join(found_interests)
                            if found_interests
                            else "Kein Interesse aus dem Profil in der Anzeige"
                        )
                        + f"\n\nVorlage: {job.get('template_id') or '—'} "
                        f"({FIT_LABELS[level]}, Schwelle {min_score})\n"
                        f"Stichworte: {job.get('keywords') or ''}"
                    )
                elif column == 7:
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setToolTip(
                        "Fähigkeiten in der Anzeige: " + ", ".join(found_skills)
                        if found_skills
                        else "Keine Fähigkeit aus dem Profil in der Anzeige"
                    )
                if column == 0:
                    item.setData(Qt.UserRole, job.get("id"))
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 28)
        self.hint.setText(f"{len(self._rows)} Stellen")
        self._update_buttons()

    def _selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _update_buttons(self) -> None:
        job = self._selected()
        exists = (
            job is not None
            and self.window.store.application_by_job(str(job.get("id")))
        )
        self.prepare_button.setEnabled(job is not None and not exists)
        self.open_button.setEnabled(bool(job and job.get("url")))
        self.ignore_button.setEnabled(
            job is not None and job.get("status") not in {"ignoriert", "beworben"}
        )

    # ------------------------------------------------------------------
    def prepare(self) -> None:
        job = self._selected()
        if job is None:
            return
        self.window.prepare_application(str(job.get("id")))

    def open_job(self) -> None:
        job = self._selected()
        if job is None:
            return
        apply_url = str(job.get("url") or "")
        if not apply_url:
            return
        self.window.open_url(apply_url)

    def ignore(self) -> None:
        job = self._selected()
        if job is None:
            return
        answer = QMessageBox.question(
            self,
            "Stelle ignorieren",
            f"„{job.get('title')}“ ausblenden? Es wird keine Bewerbung vorbereitet.",
        )
        if answer != QMessageBox.Yes:
            return
        self.window.store.update_job(str(job.get("id")), status="ignoriert")
        self.window.store.log(
            "stelle", f"Ignoriert: {job.get('title')} bei {job.get('company')}"
        )
        self.refresh()
        self.window.refresh_all()
