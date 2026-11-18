"""Bewerbungen: Entwürfe, Versand, Antworten und Nachfragen."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.pipeline import due_label, reply_summary
from ..core.text import format_date, now_iso
from .flow_layout import FlowLayout

STATUS_LABELS = {
    "entwurf": "Entwurf",
    "gesendet": "Gesendet",
    "nachgefasst": "Nachgefragt",
    "einladung": "Einladung",
    "zusage": "Zusage",
    "absage": "Absage",
    "archiviert": "Archiviert",
    "info": "Antwort",
}

COLUMNS = ("Datum", "Firma", "Stelle", "Vorlage", "Status", "Gesendet", "Nachfrage")


class ApplicationsPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Umbrechende Zeile: schmales Fenster oder grössere Schrift schiebt
        # Häkchen und Zähler in die nächste Zeile, statt sie abzuschneiden.
        filters = FlowLayout(spacing=12)
        label = QLabel("Status")
        label.setObjectName("Hint")
        filters.addWidget(label)
        self.status_boxes: dict[str, QCheckBox] = {}
        for key, text in STATUS_LABELS.items():
            box = QCheckBox(text)
            box.setToolTip(
                "Nur Bewerbungen mit diesem Status. Mehrere Häkchen zeigen "
                "die Bewerbungen aller gewählten Status; ohne Häkchen alle."
            )
            box.toggled.connect(self.refresh)
            self.status_boxes[key] = box
            filters.addWidget(box)
        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        filters.addWidget(self.hint)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.cellDoubleClicked.connect(lambda *_: self.show_letter())
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.letter_button = QPushButton("Anschreiben anzeigen")
        self.letter_button.clicked.connect(self.show_letter)
        self.draft_button = QPushButton("Entwurf im Mailkonto öffnen")
        self.draft_button.clicked.connect(self.open_draft)
        self.sent_button = QPushButton("Als gesendet markieren")
        self.sent_button.clicked.connect(self.mark_sent)
        self.follow_button = QPushButton("Nachfrage vorbereiten")
        self.follow_button.clicked.connect(self.follow_up)
        self.archive_button = QPushButton("Archivieren")
        self.archive_button.clicked.connect(self.archive)
        self.mail_button = QPushButton("E-Mail-Eingang jetzt prüfen")
        self.mail_button.setToolTip(
            "Gesendete Bewerbungen und eingegangene Antworten sofort abgleichen."
        )
        self.mail_button.clicked.connect(self.window.check_mail)
        for button in (
            self.letter_button,
            self.draft_button,
            self.sent_button,
            self.follow_button,
            self.archive_button,
            self.mail_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._rows: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    def selected_statuses(self) -> list[str]:
        """Angehakte Status; ohne Häkchen werden alle Bewerbungen gezeigt."""
        return [key for key, box in self.status_boxes.items() if box.isChecked()]

    def refresh(self) -> None:
        statuses = self.selected_statuses()
        self._rows = self.window.store.list_applications(statuses=statuses)
        days = int(self.window.settings.number("automation.follow_up_days", 14) or 14)
        self.table.setRowCount(len(self._rows))
        for row, application in enumerate(self._rows):
            due = due_label(application, days)
            if application.get("follow_up_at"):
                due = "vorbereitet"
            elif reply_summary(application):
                due = reply_summary(application)
            values = (
                format_date(application.get("created_at")),
                application.get("company") or "",
                application.get("title") or "",
                application.get("template_id") or "",
                STATUS_LABELS.get(
                    str(application.get("status") or ""),
                    str(application.get("status") or ""),
                ),
                format_date(application.get("sent_at")),
                due,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 4:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 28)
        hint = f"{len(self._rows)} Bewerbungen"
        if statuses:
            hint += " (gefiltert)"
        self.hint.setText(hint)
        self._update_buttons()

    def _selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _update_buttons(self) -> None:
        application = self._selected()
        advanced = application is not None
        self.letter_button.setEnabled(advanced)
        self.draft_button.setEnabled(
            bool(advanced and (application.get("web_link") or application.get("draft_id")))
        )
        self.sent_button.setEnabled(
            bool(advanced and application.get("status") == "entwurf")
        )
        self.follow_button.setEnabled(
            bool(
                advanced
                and application.get("status") in {"gesendet", "info"}
                and not application.get("follow_up_at")
            )
        )
        self.archive_button.setEnabled(
            bool(advanced and application.get("status") not in {"archiviert", "absage"})
        )

    # ------------------------------------------------------------------
    def show_letter(self) -> None:
        application = self._selected()
        if application is None:
            return
        text = (
            f"An: {application.get('company') or 'Firma'}\n"
            f"Betreff: {application.get('subject') or ''}\n\n"
            f"{application.get('body') or ''}"
        )
        if application.get("follow_up_subject"):
            text += (
                "\n\n— Nachfrage —\n"
                f"Betreff: {application.get('follow_up_subject')}\n\n"
                f"{application.get('follow_up_body') or ''}"
            )
        dialog = LetterDialog(
            self,
            str(application.get("subject") or "Anschreiben"),
            text,
            tracking=str(application.get("tracking") or ""),
        )
        dialog.exec()

    def open_draft(self) -> None:
        application = self._selected()
        if application is None:
            return
        link = str(application.get("web_link") or application.get("follow_up_web_link") or "")
        if link:
            self.window.open_url(link)
            return
        QMessageBox.information(
            self,
            "Entwurf",
            "Für diesen Entwurf gibt es keinen Link. Der Text steht unter "
            "„Anschreiben anzeigen“ und lässt sich von dort kopieren.",
        )

    def mark_sent(self) -> None:
        application = self._selected()
        if application is None:
            return
        self.window.store.update_application(
            int(application["id"]), status="gesendet", sent_at=now_iso()
        )
        self.window.store.update_job(
            str(application.get("job_id") or ""), status="beworben"
        )
        self.window.store.log(
            "versand",
            f"Von Hand als gesendet markiert: {application.get('company') or ''}",
        )
        self.refresh()
        self.window.refresh_all()

    def follow_up(self) -> None:
        application = self._selected()
        if application is None:
            return
        self.window.prepare_follow_up(int(application["id"]))

    def archive(self) -> None:
        application = self._selected()
        if application is None:
            return
        answer = QMessageBox.question(
            self,
            "Bewerbung archivieren",
            "Diese Bewerbung aus der aktiven Liste nehmen?",
        )
        if answer != QMessageBox.Yes:
            return
        self.window.store.update_application(
            int(application["id"]), status="archiviert", archived_at=now_iso()
        )
        self.window.store.update_job(
            str(application.get("job_id") or ""), status="archiviert"
        )
        self.window.store.log(
            "archiv", f"Archiviert: {application.get('company') or ''}"
        )
        self.refresh()
        self.window.refresh_all()


class LetterDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        text: str,
        *,
        tracking: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(680, 560)
        layout = QVBoxLayout(self)
        if tracking:
            # Zum Nachschauen: mit dieser Kennung wird eine Antwort zugeordnet.
            code = QLabel(f"Kennung dieser Bewerbung: {tracking}")
            code.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            code.setStyleSheet(
                "background:#10131a; border:1px solid #2b313c; border-radius:6px;"
                "padding:6px; letter-spacing:1px;"
            )
            code.setToolTip(
                "Diese Kennung reist unsichtbar in der Mail mit; Antworten werden "
                "darüber zugeordnet. Text markieren und kopieren genügt."
            )
            layout.addWidget(code)
        view = QPlainTextEdit()
        view.setPlainText(text)
        view.setReadOnly(True)
        layout.addWidget(view, 1)
        buttons = QHBoxLayout()
        copy = QPushButton("Kopieren")
        copy.setObjectName("Primary")
        copy.clicked.connect(lambda: self._copy(text))
        close = QPushButton("Schließen")
        close.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(copy)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _copy(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
