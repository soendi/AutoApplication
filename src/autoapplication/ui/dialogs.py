"""Dialog fuer die Anmeldung per Geraetecode (Outlook oder Google)."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from .workers import Task


class DeviceLoginDialog(QDialog):
    """Zeigt den Code an und fragt im Hintergrund nach der Freigabe."""

    def __init__(self, parent: Any, auth: Any, provider: str = "outlook") -> None:
        super().__init__(parent)
        self.auth = auth
        self.login: Any = None
        self._tasks: list[Task] = []
        self._polling = False
        google = provider == "google"
        service = "Google" if google else "Microsoft"
        self.service = "Google" if google else "Outlook"
        self.setWindowTitle(
            "Mit Google verbinden" if google else "Mit Outlook verbinden"
        )
        self.resize(520, 300)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        heading = QLabel(f"Anmeldung bei {service}")
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)

        self.info = QLabel(
            "AutoApplication öffnet gleich die Google-Anmeldung im Browser. "
            "Dort mit dem Google-Konto anmelden und die Freigabe erteilen – "
            "danach kehrt die Anmeldung automatisch zurück."
            if google
            else f"AutoApplication öffnet gleich die Anmeldeseite von {service}. "
            "Dort den angezeigten Code eingeben und die Freigabe erteilen."
        )
        self.info.setWordWrap(True)
        self.info.setObjectName("Hint")
        layout.addWidget(self.info)

        self.code = QLabel("…")
        self.code.setVisible(not google)
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
        self.code.setText(login.user_code or "")
        if login.user_code:
            self.status.setText(
                "Code eingeben, anmelden und die Freigabe erteilen. "
                "Dieses Fenster schliesst sich, sobald die Anmeldung abgeschlossen ist."
            )
        else:
            self.status.setText(
                "Im Browser mit dem Google-Konto anmelden und die Freigabe "
                "erteilen. Dieses Fenster schliesst sich, sobald die Anmeldung "
                "abgeschlossen ist."
            )
        self.open_button.setEnabled(True)
        self._open_page()
        self._timer.start(max(2, int(login.interval or 2)) * 1000)

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
            self.status.setText(f"Verbunden. {self.service} ist bereit.")
            self.status.setObjectName("Ok")
            self.accept()

    def _failed(self, message: str) -> None:
        self._polling = False
        self._timer.stop()
        self._cancel_login()
        self.status.setText(message)
        self.status.setObjectName("Danger")

    def _cancel_login(self) -> None:
        cancel = getattr(self.auth, "cancel_login", None)
        if callable(cancel):
            cancel(self.login)

    def reject(self) -> None:  # noqa: D102 - Qt-Namensschema
        self._timer.stop()
        self._cancel_login()
        super().reject()

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt-Namensschema
        self._timer.stop()
        self._cancel_login()
        super().closeEvent(event)
