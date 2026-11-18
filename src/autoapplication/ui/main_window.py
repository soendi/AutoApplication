"""Hauptfenster von AutoApplication."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_TAGLINE, APP_VERSION
from ..core import updater
from ..core.config import Settings, database_path
from ..core.pipeline import Pipeline
from ..core.store import Store
from ..core.text import now_iso
from .applications import ApplicationsPage
from .branding import app_icon, logo_pixmap
from .jobs import JobsPage
from .log_page import LogPage
from .overview import OverviewPage
from .settings_page import SettingsPage
from .templates_page import TemplatesPage
from .workers import Task

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings | None = None,
        store: Store | None = None,
        pipeline: Pipeline | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings or Settings().load()
        self.store = store or Store(database_path())
        self.pipeline = pipeline or Pipeline(
            self.settings, self.store, notifier=self.notify
        )
        self._tasks: set[Task] = set()
        self._daily_running = False
        self._update_running = False

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self._build_header()
        self._build_tabs()
        self._build_menu()
        self.statusBar().showMessage("Bereit.")
        self._setup_tray()
        self._start_timer()
        self.refresh_all()

    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("Header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        header_layout.setSpacing(12)

        logo = QLabel()
        logo.setPixmap(logo_pixmap(38))
        header_layout.addWidget(logo)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        subtitle = QLabel(APP_TAGLINE)
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header_layout.addLayout(titles)
        header_layout.addStretch(1)

        version = QLabel(f"Version {APP_VERSION}")
        version.setObjectName("VersionChip")
        header_layout.addWidget(version)

        self.update_button = QPushButton("Nach Updates suchen")
        self.update_button.setObjectName("Ghost")
        self.update_button.clicked.connect(lambda: self.check_updates(manual=True))
        header_layout.addWidget(self.update_button)

        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(container)

    def _build_tabs(self) -> None:
        self.overview = OverviewPage(self)
        self.jobs = JobsPage(self)
        self.applications = ApplicationsPage(self)
        self.templates = TemplatesPage(self)
        self.settings_page = SettingsPage(self)
        self.log_page = LogPage(self)
        self.pages = [
            self.overview,
            self.jobs,
            self.applications,
            self.templates,
            self.settings_page,
            self.log_page,
        ]
        for page, name in zip(
            self.pages,
            ("Übersicht", "Stellen", "Bewerbungen", "Vorlagen", "Einstellungen", "Protokoll"),
        ):
            self.tabs.addTab(page, name)

    def _build_menu(self) -> None:
        datei = self.menuBar().addMenu("Datei")
        daily = QAction("Tageslauf jetzt starten", self)
        daily.triggered.connect(self.run_daily)
        datei.addAction(daily)
        settings_action = QAction("Einstellungen", self)
        settings_action.triggered.connect(lambda: self.tabs.setCurrentWidget(self.settings_page))
        datei.addAction(settings_action)
        datei.addSeparator()
        quit_action = QAction("Beenden", self)
        quit_action.triggered.connect(self.close)
        datei.addAction(quit_action)

        hilfe = self.menuBar().addMenu("Hilfe")
        update = QAction("Nach Updates suchen …", self)
        update.triggered.connect(lambda: self.check_updates(manual=True))
        hilfe.addAction(update)
        release = QAction("Release-Seite öffnen", self)
        release.triggered.connect(lambda: self.open_url(updater.release_page()))
        hilfe.addAction(release)
        about = QAction(f"Über {APP_NAME}", self)
        about.triggered.connect(self.show_about)
        hilfe.addAction(about)

    def _setup_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if not self.settings.flag("automation.notify_desktop", True):
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} {APP_VERSION}")
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason: Any) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.showNormal()
            self.raise_()

    def _start_timer(self) -> None:
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(60_000)

    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        for page in getattr(self, "pages", []):
            try:
                page.refresh()
            except Exception as exc:  # noqa: BLE001 - eine Seite darf nicht alles stoppen
                log.warning("Seite konnte nicht aktualisiert werden: %s", exc)

    def _tab_changed(self, _index: int) -> None:
        page = self.tabs.currentWidget()
        if hasattr(page, "refresh"):
            page.refresh()

    def reload_settings(self) -> None:
        self.settings_page.load()
        self._setup_tray_visibility()
        self.refresh_all()

    def _setup_tray_visibility(self) -> None:
        if self.tray is None:
            self._setup_tray()
            return
        if self.settings.flag("automation.notify_desktop", True):
            self.tray.show()
        else:
            self.tray.hide()

    # ------------------------------------------------------------------
    def run_task(
        self,
        function: Callable[[], Any],
        done: Callable[[Any], None] | None = None,
        busy: str = "",
        refresh: bool = True,
    ) -> None:
        if busy:
            self.statusBar().showMessage(busy)
        task = Task(function, self)
        self._tasks.add(task)

        def finished(result: Any) -> None:
            self._tasks.discard(task)
            if done is not None:
                done(result)
            if refresh:
                self.refresh_all()
            self.statusBar().showMessage("Fertig.", 4000)

        def failed(message: str) -> None:
            self._tasks.discard(task)
            self.statusBar().showMessage(f"Fehler: {message}", 10_000)
            QMessageBox.warning(self, "Fehler", message)

        task.done.connect(finished)
        task.failed.connect(failed)
        task.start()

    def notify(self, title: str, message: str) -> None:
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, 8000
            )
        else:
            self.statusBar().showMessage(f"{title}: {message}", 12_000)

    # ------------------------------------------------------------------
    def run_search(self) -> None:
        self.run_task(
            self.pipeline.run_search,
            done=lambda summary: self.statusBar().showMessage(summary.as_text(), 20_000),
            busy="Stellen werden gesucht …",
        )

    def check_mail(self) -> None:
        if not self.pipeline.outlook_ready():
            QMessageBox.information(
                self,
                "Outlook",
                "Outlook ist noch nicht verbunden. Unter Einstellungen > Outlook "
                "anmelden – danach werden Entwürfe, Versand und Antworten "
                "automatisch verfolgt.",
            )
            return

        def work() -> tuple[int, int]:
            sent = self.pipeline.sync_sent()
            replies = self.pipeline.check_replies()
            return sent, len(replies)

        def done(result: tuple[int, int]) -> None:
            sent, replies = result
            self.statusBar().showMessage(
                f"{sent} gesendete Bewerbungen erkannt, {replies} Antworten ausgewertet.",
                15_000,
            )

        self.run_task(work, done=done, busy="Postfach wird geprüft …")

    def prepare_follow_ups(self) -> None:
        self.run_task(
            self.pipeline.prepare_follow_ups,
            done=lambda count: self.statusBar().showMessage(
                f"{count} Nachfragen vorbereitet.", 12_000
            ),
            busy="Nachfragen werden vorbereitet …",
        )

    def prepare_application(self, job_id: str) -> None:
        self.run_task(
            lambda: self.pipeline.prepare_application(job_id),
            done=lambda _result: self.statusBar().showMessage(
                "Bewerbung als Entwurf vorbereitet.", 12_000
            ),
            busy="Bewerbung wird vorbereitet …",
        )

    def prepare_follow_up(self, application_id: int) -> None:
        self.run_task(
            lambda: self.pipeline.prepare_follow_up(application_id),
            done=lambda _result: self.statusBar().showMessage(
                "Nachfrage vorbereitet.", 12_000
            ),
            busy="Nachfrage wird vorbereitet …",
        )

    def run_daily(self) -> None:
        if self._daily_running:
            self.statusBar().showMessage("Der Tageslauf läuft bereits.", 6000)
            return
        self._daily_running = True

        def done(summary: Any) -> None:
            self._daily_running = False
            self.statusBar().showMessage(f"Tageslauf: {summary.as_text()}", 20_000)

        def failed(message: str) -> None:
            self._daily_running = False
            QMessageBox.warning(self, "Tageslauf", message)

        task = Task(self.pipeline.run_daily, self)
        self._tasks.add(task)
        task.done.connect(lambda result: (done(result), self._tasks.discard(task)))
        task.failed.connect(lambda message: (failed(message), self._tasks.discard(task)))
        self.statusBar().showMessage("Tageslauf läuft …")
        task.start()

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self._daily_running:
            return
        daily = self.settings.text("automation.daily_time", "07:30")
        try:
            hour, minute = (int(part) for part in daily.split(":", 1))
        except ValueError:
            return
        now = datetime.now()
        if (now.hour, now.minute) < (hour, minute):
            return
        last = self.store.meta_get("letzter_tageslauf", "")
        if last[:10] == now.date().isoformat():
            return
        self.run_daily()

    def maybe_start_daily(self) -> None:
        """Beim Start einmal am Tag suchen, wenn die Automatik das will."""
        if not self.settings.flag("automation.auto_on_start", True):
            return
        last = self.store.meta_get("letzter_tageslauf", "")
        if last[:10] == datetime.now().date().isoformat():
            return
        self.run_daily()

    # ------------------------------------------------------------------
    def open_url(self, url: str) -> None:
        text = (url or "").strip()
        if text.startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(text))

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            f"Über {APP_NAME}",
            f"<b>{APP_NAME}</b> {APP_VERSION}<br>{APP_TAGLINE}<br><br>"
            "Stellen von ostjob.ch, Bewerbungen als Outlook-Entwurf, "
            "Antworten und Nachfragen an einem Ort.<br><br>"
            "Alle Angaben liegen unter "
            f"<code>{Path.home() / 'AutoApplication'}</code>.",
        )

    # ------------------------------------------------------------------
    def check_updates(self, manual: bool = False) -> None:
        if self._update_running:
            return
        self._update_running = True

        def work() -> tuple[Any, bool, Any]:
            release = updater.fetch_latest()
            if release is None:
                return None, False, None
            if not updater.is_newer(APP_VERSION, release.version):
                return release, False, None
            if not updater.can_install():
                return release, False, None
            asset = updater.asset_for(release)
            if asset is None:
                return release, False, None
            name, url = asset
            target = Path(tempfile.gettempdir()) / name
            updater.download(url, target)
            return release, True, updater.install(target)

        def done(result: tuple[Any, bool, Any]) -> None:
            self._update_running = False
            release, installing, outcome = result
            if release is None:
                if manual:
                    QMessageBox.information(
                        self,
                        "Update",
                        "Die Update-Abfrage hat keine Antwort geliefert. Bitte "
                        f"später erneut versuchen oder {updater.release_page()} öffnen.",
                    )
                return
            if not installing:
                if manual:
                    if updater.is_newer(APP_VERSION, release.version):
                        QMessageBox.information(
                            self,
                            "Update",
                            f"Version {release.version} ist verfügbar. Die "
                            "automatische Installation gibt es nur für die "
                            "Windows-Fassung; bitte von der Release-Seite "
                            "installieren.",
                        )
                    else:
                        QMessageBox.information(
                            self,
                            "Update",
                            f"Sie verwenden die neueste Fassung ({APP_VERSION}).",
                        )
                return
            if outcome is not None and outcome.ok:
                QMessageBox.information(self, "Update", outcome.message)
                QApplication.quit()
            elif manual:
                QMessageBox.warning(
                    self,
                    "Update",
                    outcome.message if outcome else "Das Update liess sich nicht starten.",
                )

        def failed(message: str) -> None:
            self._update_running = False
            if manual:
                QMessageBox.warning(self, "Update", message)

        task = Task(work, self)
        self._tasks.add(task)
        task.done.connect(lambda result: (done(result), self._tasks.discard(task)))
        task.failed.connect(lambda message: (failed(message), self._tasks.discard(task)))
        task.start()

    def start_auto_update(self) -> None:
        if os.environ.get("AUTOAPPLICATION_NO_UPDATE") == "1":
            return
        if "--no-update" in sys.argv:
            return
        if not updater.can_install():
            return
        self.check_updates(manual=False)
