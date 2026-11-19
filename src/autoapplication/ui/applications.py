"""Bewerbungen: drei Tabellen für Entwürfe/Versand, Antworten und Absagen."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPointF, QPropertyAnimation
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QGraphicsOpacityEffect,
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
from ..core.text import format_date, format_datetime, now_iso
from .flow_layout import FlowLayout
from .theme import APPLICATION_COLOR_NAMES, APPLICATION_COLORS

STATUS_LABELS = {
    "entwurf": "Entwurf",
    "gesendet": "Gesendet",
    "nachgefasst": "Nachgefragt",
    "einladung": "Einladung (Gespräch)",
    "zusage": "Zusage (Stelle)",
    "absage": "Absage",
    "archiviert": "Archiviert",
    "info": "Antwort",
}

# Eine Tabelle je Gruppe: was noch läuft, was geantwortet hat, was erledigt ist.
GROUPS = (
    ("Entwurf, Gesendet, Nachgefragt", ("entwurf", "gesendet", "nachgefasst")),
    ("Antworten", ("info", "einladung", "zusage")),
    ("Absagen und Archiv", ("absage", "archiviert")),
)

COLUMNS = ("", "Datum", "Firma", "Stelle", "Vorlage", "Status", "Gesendet", "Nachfrage")
MAIL_COLUMN = 0
TITLE_COLUMN = 3

NEW_MAIL_COLOR = "#ffa53d"
SEEN_MAIL_COLOR = "#8a919c"


def envelope_pixmap(opened: bool, color: str, size: int = 18) -> QPixmap:
    """Kleiner Briefumschlag: offen oder geschlossen."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    painter.setPen(pen)
    width = float(size)
    top = 7.0 if opened else 4.0
    body = QRectF(2.0, top, width - 4.0, width - top - 3.0)
    painter.drawRoundedRect(body, 2.0, 2.0)
    centre = QPointF(width / 2.0, body.center().y())
    if opened:
        # Geöffnete Klappe: zwei Linien nach oben, Brief liegt sichtbar darin.
        painter.drawLine(QPointF(body.left(), body.top()), QPointF(width / 2.0, body.top() - 4.0))
        painter.drawLine(
            QPointF(body.right(), body.top()), QPointF(width / 2.0, body.top() - 4.0)
        )
        painter.drawLine(QPointF(body.left(), body.top()), QPointF(width / 2.0, centre.y()))
        painter.drawLine(
            QPointF(body.right(), body.top()), QPointF(width / 2.0, centre.y())
        )
    else:
        painter.drawLine(QPointF(body.left(), body.top()), centre)
        painter.drawLine(QPointF(body.right(), body.top()), centre)
    painter.end()
    return pixmap


class MailBadge(QLabel):
    """Umschlag je Zeile: orange pulsierend für neue, grau offen für gelesene."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(24, 20)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)
        self._animation = QPropertyAnimation(self._effect, b"opacity", self)
        self._animation.setDuration(1400)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._animation.setKeyValueAt(0.0, 1.0)
        self._animation.setKeyValueAt(0.5, 0.25)
        self._animation.setKeyValueAt(1.0, 1.0)
        self._animation.setDirection(QAbstractAnimation.Direction.Forward)
        self.set_state(new=False, unseen=0, total=0)

    def set_state(self, *, new: bool, unseen: int, total: int) -> None:
        if new:
            self.setPixmap(envelope_pixmap(False, NEW_MAIL_COLOR))
            self.setToolTip(
                f"{unseen} neue Antwort{'en' if unseen != 1 else ''} – "
                "Doppelklick zeigt sie an."
            )
            self._effect.setOpacity(1.0)
            self._animation.start()
            return
        self._animation.stop()
        self._effect.setOpacity(1.0)
        if total:
            self.setPixmap(envelope_pixmap(True, SEEN_MAIL_COLOR))
            self.setToolTip("Antwort gelesen – Doppelklick zeigt sie erneut an.")
        else:
            self.clear()
            self.setToolTip("Noch keine Antwort.")

    def stop(self) -> None:
        self._animation.stop()


class ApplicationSection(QWidget):
    """Eine Tabelle mit eigenen Status-Häkchen darüber."""

    def __init__(self, page: "ApplicationsPage", title: str, statuses: tuple[str, ...]) -> None:
        super().__init__(page)
        self.page = page
        self.title = title
        self.statuses = statuses
        self._rows: list[dict[str, Any]] = []
        self._badges: list[MailBadge] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.caption = QLabel(title)
        self.caption.setStyleSheet("font-weight: 600;")
        header.addWidget(self.caption)
        self.boxes: dict[str, QCheckBox] = {}
        for key in statuses:
            box = QCheckBox(STATUS_LABELS.get(key, key))
            box.setChecked(True)
            box.setToolTip(
                "Nur Bewerbungen mit diesem Status zeigen; ohne Häkchen ist "
                "diese Statusgruppe ausgeblendet."
            )
            box.toggled.connect(page.refresh)
            self.boxes[key] = box
        flow_host = QWidget()
        flow = FlowLayout(flow_host, spacing=10)
        for box in self.boxes.values():
            flow.addWidget(box)
        header.addWidget(flow_host, 1)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            TITLE_COLUMN, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(MAIL_COLUMN, 26)
        self.table.itemSelectionChanged.connect(lambda: page.set_current(self))
        self.table.cellDoubleClicked.connect(
            lambda row, _column: page.open_row(self, row)
        )
        layout.addWidget(self.table, 1)

    # ------------------------------------------------------------------
    def selected_statuses(self) -> list[str]:
        return [key for key, box in self.boxes.items() if box.isChecked()]

    def rows(self) -> list[dict[str, Any]]:
        return self._rows

    def fill(
        self,
        rows: list[dict[str, Any]],
        unseen: dict[int, int],
        totals: dict[int, int],
        days: int,
    ) -> None:
        for badge in self._badges:
            badge.stop()
        self._badges = []
        self._rows = rows
        self.caption.setText(f"{self.title} ({len(rows)})")
        # Auf 0 setzen entfernt auch die alten Umschlag-Symbole der Zeilen.
        self.table.setRowCount(0)
        self.table.setRowCount(len(rows))
        for row, application in enumerate(rows):
            status = str(application.get("status") or "")
            due = due_label(application, days)
            if application.get("follow_up_sent_at"):
                due = (
                    "Nachfrage "
                    f"{format_datetime(application.get('follow_up_sent_at'))}"
                )
            elif application.get("follow_up_at"):
                due = "vorbereitet"
            elif reply_summary(application):
                due = reply_summary(application)
            values = (
                format_date(application.get("created_at")),
                application.get("company") or "",
                application.get("title") or "",
                application.get("template_id") or "",
                STATUS_LABELS.get(status, status),
                format_datetime(application.get("sent_at")),
                due,
            )
            tint = QColor(APPLICATION_COLORS[status]) if status in APPLICATION_COLORS else None
            for column, value in enumerate(values, start=MAIL_COLUMN + 1):
                item = QTableWidgetItem(str(value))
                if tint is not None:
                    item.setBackground(tint)
                if column == 5:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if status in APPLICATION_COLOR_NAMES:
                        item.setToolTip(f"Status: {APPLICATION_COLOR_NAMES[status]}")
                self.table.setItem(row, column, item)
            application_id = int(application["id"])
            unseen_count = unseen.get(application_id, 0)
            total_count = totals.get(application_id, 0)
            mail_item = QTableWidgetItem("")
            if tint is not None:
                mail_item.setBackground(tint)
            self.table.setItem(row, MAIL_COLUMN, mail_item)
            if unseen_count or total_count:
                badge = MailBadge()
                badge.set_state(
                    new=unseen_count > 0,
                    unseen=unseen_count,
                    total=total_count,
                )
                if tint is not None:
                    badge.setStyleSheet(
                        f"background: {tint.name()}; border-radius: 4px;"
                    )
                self.table.setCellWidget(row, MAIL_COLUMN, badge)
                self._badges.append(badge)
            self.table.setRowHeight(row, 28)


class ApplicationsPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        self.sections: list[ApplicationSection] = []
        self._current: ApplicationSection | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setToolTip(
            "Farbe der Zeile nach Status:\n"
            "Weiss: Entwurf\n"
            "Grün: Gesendet, Einladung, Zusage\n"
            "Orange: Nachgefragt, Antwort\n"
            "Rot: Absage\n"
            "Grau: Archiviert"
        )
        layout.addWidget(self.hint)

        for title, statuses in GROUPS:
            section = ApplicationSection(self, title, statuses)
            self.sections.append(section)
            layout.addWidget(section, 1)

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

        self._set_current(self.sections[0])

    # ------------------------------------------------------------------
    def set_current(self, section: ApplicationSection) -> None:
        self._set_current(section)

    def _set_current(self, section: ApplicationSection | None) -> None:
        self._current = section
        self._update_buttons()

    def selected_statuses(self) -> list[str]:
        """Alle angehakten Status über alle drei Tabellen."""
        statuses: list[str] = []
        for section in self.sections:
            statuses.extend(section.selected_statuses())
        return statuses

    def refresh(self) -> None:
        applications = self.window.store.list_applications()
        days = int(self.window.settings.number("automation.follow_up_days", 14) or 14)
        try:
            unseen = self.window.store.unseen_by_application()
            totals = self.window.store.reply_counts()
        except Exception:  # noqa: BLE001 - Anzeige darf nicht scheitern
            unseen, totals = {}, {}
        shown = 0
        for section in self.sections:
            wanted = set(section.selected_statuses())
            rows = [
                application
                for application in applications
                if str(application.get("status") or "") in wanted
            ]
            section.fill(rows, unseen, totals, days)
            shown += len(rows)
        self.hint.setText(f"{shown} Bewerbungen")
        self._update_buttons()

    def _selected(self) -> dict[str, Any] | None:
        section = self._current
        if section is None:
            return None
        row = section.table.currentRow()
        rows = section.rows()
        if 0 <= row < len(rows):
            return rows[row]
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
    def open_row(self, section: ApplicationSection, row: int) -> None:
        """Doppelklick je Tabelle: eigene Mail, Antworten oder Absage."""
        section.table.setCurrentCell(row, TITLE_COLUMN)
        self._set_current(section)
        if section is self.sections[0]:
            self.show_letter()
        elif section is self.sections[1]:
            self.show_replies()
        else:
            self.show_replies(only_absage=True)

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
            text += "\n\n— Nachfrage —\n"
            if application.get("follow_up_sent_at"):
                text += (
                    "Verschickt am "
                    f"{format_date(application.get('follow_up_sent_at'))}\n"
                )
            text += (
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

    def show_replies(self, *, only_absage: bool = False) -> None:
        """Alle Antworten einer Bewerbung in einem Fenster zeigen."""
        application = self._selected()
        if application is None:
            return
        application_id = int(application["id"])
        replies = self.window.store.replies_for(application_id)
        if only_absage:
            rejections = [r for r in replies if str(r.get("kind") or "") == "absage"]
            replies = rejections or replies
        if not replies:
            QMessageBox.information(
                self,
                "Absage" if only_absage else "Antworten",
                "Für diese Bewerbung ist noch keine Antwort gespeichert.",
            )
            return
        blocks: list[tuple[str, str]] = []
        for reply in replies:
            header = " · ".join(
                part
                for part in (
                    format_date(reply.get("received_at")),
                    str(reply.get("sender") or ""),
                    str(reply.get("subject") or ""),
                    STATUS_LABELS.get(str(reply.get("kind") or ""), ""),
                )
                if part
            )
            body = str(reply.get("body") or reply.get("snippet") or "")
            blocks.append((header, body))
        title = f"{'Absage' if only_absage else 'Antworten'} – {application.get('company') or 'Firma'}"
        MailDialog(self, title, blocks).exec()
        self.window.store.mark_replies_seen(application_id)
        self.refresh()

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
        if answer != QMessageBox.StandardButton.Yes:
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


class MailDialog(QDialog):
    """Antworten einer Bewerbung – alle in einem Fenster."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        blocks: list[tuple[str, str]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 600)
        layout = QVBoxLayout(self)
        parts: list[str] = []
        for index, (header, body) in enumerate(blocks):
            if index:
                parts.append("─" * 60)
            parts.append(header)
            parts.append("")
            parts.append(body.strip() or "(kein Text gespeichert)")
            parts.append("")
        text = "\n".join(parts).strip()
        view = QPlainTextEdit()
        view.setPlainText(text)
        view.setReadOnly(True)
        view.setToolTip("Antwort der Firma; mit „Kopieren“ in die Zwischenablage.")
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
