"""Dialoge: Outlook-Anmeldung (Geraetecode) und fehlende Kontaktdaten."""

from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .workers import Task


class DeviceLoginDialog(QDialog):
    """Zeigt den Code an und fragt im Hintergrund nach der Freigabe."""

    def __init__(self, parent: Any, auth: Any) -> None:
        super().__init__(parent)
        self.auth = auth
        self.login: Any = None
        self._tasks: list[Task] = []
        self._polling = False

        self.setWindowTitle("Mit Outlook verbinden")
        self.resize(520, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        heading = QLabel("Anmeldung bei Microsoft")
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)

        self.info = QLabel(
            "AutoApplication öffnet gleich die Anmeldeseite von Microsoft. "
            "Dort den angezeigten Code eingeben und die Freigabe erteilen."
        )
        self.info.setWordWrap(True)
        self.info.setObjectName("Hint")
        layout.addWidget(self.info)

        self.code = QLabel("…")
        self.code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont()
        font.setPointSizeF(20)
        font.setBold(True)
        self.code.setFont(font)
        self.code.setStyleSheet(
            "background:#10131a; border:1px solid #2b313c; border-radius:8px;"
            "padding:12px; letter-spacing:3px;"
        )
        layout.addWidget(self.code)

        self.status = QLabel("Anmeldung wird vorbereitet …")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("Anmeldeseite öffnen")
        self.open_button.setObjectName("Primary")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_page)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._start()

    # ------------------------------------------------------------------
    def _run(self, function: Callable[[], Any], done: Callable[[Any], None],
             failed: Callable[[str], None]) -> None:
        task = Task(function, self)
        self._tasks.append(task)
        task.done.connect(done)
        task.failed.connect(failed)
        task.finished.connect(lambda: self._tasks.remove(task) if task in self._tasks else None)
        task.start()

    def _start(self) -> None:
        self._run(self.auth.start_device_flow, self._ready, self._failed)

    def _ready(self, login: Any) -> None:
        self.login = login
        self.code.setText(login.user_code)
        self.status.setText(
            "Code eingeben, anmelden und die Freigabe erteilen. "
            "Dieses Fenster schliesst sich, sobald die Anmeldung abgeschlossen ist."
        )
        self.open_button.setEnabled(True)
        self._open_page()
        self._timer.start(max(5, int(login.interval or 5)) * 1000)

    def _open_page(self) -> None:
        if self.login is not None:
            QDesktopServices.openUrl(QUrl(self.login.verification_uri))

    def _poll(self) -> None:
        if self.login is None or self._polling:
            return
        self._polling = True
        self._run(
            lambda: self.auth.poll_device_flow(self.login),
            self._polled,
            self._failed,
        )

    def _polled(self, finished: Any) -> None:
        self._polling = False
        if finished:
            self._timer.stop()
            self.status.setText("Verbunden. Outlook ist bereit.")
            self.status.setObjectName("Ok")
            self.accept()

    def _failed(self, message: str) -> None:
        self._polling = False
        self._timer.stop()
        self.status.setText(message)
        self.status.setObjectName("Danger")

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt-Namensschema
        self._timer.stop()
        super().closeEvent(event)


class ContactDialog(QDialog):
    """Fragt E-Mail-Adresse und Ansprechperson ab, bevor der Entwurf entsteht."""

    def __init__(
        self,
        parent: Any,
        *,
        title: str = "",
        company: str = "",
        email: str = "",
        person: str = "",
        need_email: bool = True,
        need_person: bool = True,
    ) -> None:
        super().__init__(parent)
        self.need_email = need_email
        self.need_person = need_person

        self.setWindowTitle("Kontakt für die Bewerbung")
        self.resize(520, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        heading = QLabel("Kontaktdaten ergänzen")
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)

        info = QLabel(
            "In der Anzeige fehlt, an wen die Bewerbung geht. Bitte die Angaben "
            "ergänzen – sie werden bei der Stelle gespeichert und für die Anrede "
            "im Entwurf verwendet."
        )
        info.setWordWrap(True)
        info.setObjectName("Hint")
        layout.addWidget(info)

        if title or company:
            job = QLabel(" – ".join(part for part in (title, company) if part))
            job.setWordWrap(True)
            layout.addWidget(job)

        layout.addWidget(QLabel("E-Mail-Adresse"))
        self.email = QLineEdit(email)
        self.email.setPlaceholderText("z. B. bewerbung@firma.ch")
        layout.addWidget(self.email)

        layout.addWidget(QLabel("Ansprechperson"))
        self.person = QLineEdit(person)
        self.person.setPlaceholderText("z. B. Frau Meier")
        layout.addWidget(self.person)

        hint = QLabel(
            "Für eine persönliche Anrede «Herr …» oder «Frau …» angeben. Leer "
            "lassen nur, wenn die Anzeige keine Person nennt."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Abbrechen")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("Entwurf erstellen")
        confirm.setObjectName("Primary")
        confirm.setDefault(True)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

    def values(self) -> tuple[str, str]:
        return self.email.text().strip(), self.person.text().strip()

    def accept(self) -> None:
        email, person = self.values()
        if not email or "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            QMessageBox.warning(
                self,
                "E-Mail-Adresse",
                "Bitte eine vollständige E-Mail-Adresse angeben, "
                "z. B. bewerbung@firma.ch.",
            )
            self.email.setFocus()
            return
        if not person:
            answer = QMessageBox.question(
                self,
                "Anrede",
                "Ohne Ansprechperson fortfahren? Die Anrede lautet dann "
                "«Sehr geehrte Damen und Herren».",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.person.setFocus()
                return
        elif not re.match(r"(?i)^(herr|herrn|frau)\s+\S+", person):
            QMessageBox.warning(
                self,
                "Ansprechperson",
                "Bitte mit «Herr …» oder «Frau …» angeben, z. B. «Frau Meier».",
            )
            self.person.setFocus()
            return
        super().accept()
