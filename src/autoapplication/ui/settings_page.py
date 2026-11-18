"""Einstellungen: Person, Suche, KI, Outlook, Unterlagen, Automatik."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .dialogs import DeviceLoginDialog


class SettingsPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        inner = QVBoxLayout(body)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.setSpacing(12)

        # ------------------------------------------------------------------
        person = QGroupBox("Person")
        person_form = QFormLayout(person)
        self.vorname = QLineEdit()
        self.nachname = QLineEdit()
        self.strasse = QLineEdit()
        self.plz = QLineEdit()
        self.wohnort = QLineEdit()
        self.telefon = QLineEdit()
        self.email = QLineEdit()
        self.erfahrung = QLineEdit()
        self.erfahrung.setPlaceholderText("z. B. acht")
        self.verfuegbar = QLineEdit()
        self.verfuegbar.setPlaceholderText("z. B. sofort oder ab 1. März")
        for label, field in (
            ("Vorname", self.vorname),
            ("Nachname", self.nachname),
            ("Strasse", self.strasse),
            ("PLZ", self.plz),
            ("Ort", self.wohnort),
            ("Telefon", self.telefon),
            ("E-Mail", self.email),
            ("Jahre Erfahrung (Wort)", self.erfahrung),
            ("Verfügbar", self.verfuegbar),
        ):
            person_form.addRow(label, field)
        inner.addWidget(person)

        # ------------------------------------------------------------------
        search = QGroupBox("Suche auf ostjob.ch")
        search_form = QFormLayout(search)
        self.queries = QPlainTextEdit()
        self.queries.setFixedHeight(68)
        self.queries.setPlaceholderText("Ein Suchbegriff pro Zeile, z. B. Spedition")
        self.place = QLineEdit()
        self.place.setPlaceholderText("z. B. Balgach 9436 (SG)")
        self.place_code = QLineEdit()
        self.place_code.setPlaceholderText("z. B. balgach-sg-9436")
        self.place_value = QLineEdit()
        self.place_value.setPlaceholderText("leer lassen = wie Ort")
        self.lat = QLineEdit()
        self.lat.setPlaceholderText("47.4055")
        self.lng = QLineEdit()
        self.lng.setPlaceholderText("9.6087")
        self.radius = QSpinBox()
        self.radius.setRange(0, 200)
        self.radius.setSuffix(" km")
        self.commute = QSpinBox()
        self.commute.setRange(0, 300)
        self.commute.setSuffix(" km")
        self.workload_min = QSpinBox()
        self.workload_min.setRange(0, 100)
        self.workload_min.setSingleStep(10)
        self.workload_min.setSuffix(" %")
        self.workload_max = QSpinBox()
        self.workload_max.setRange(0, 100)
        self.workload_max.setSingleStep(10)
        self.workload_max.setSuffix(" %")
        self.cantons = QLineEdit()
        self.cantons.setPlaceholderText("z. B. St. Gallen, Appenzell Ausserrhoden")
        self.exclude = QLineEdit()
        self.order = QComboBox()
        self.order.setEditable(True)
        for value in ("by_relevance", "by_date", "by_distance"):
            self.order.addItem(value, value)
        self.page_size = QSpinBox()
        self.page_size.setRange(5, 100)
        self.max_pages = QSpinBox()
        self.max_pages.setRange(1, 20)
        self.max_age = QSpinBox()
        self.max_age.setRange(0, 365)
        self.max_age.setSuffix(" Tage")
        for label, field in (
            ("Suchbegriffe", self.queries),
            ("Ort", self.place),
            ("Ortskennung (placeCode)", self.place_code),
            ("Ortswert (placeValue)", self.place_value),
            ("Breitengrad", self.lat),
            ("Längengrad", self.lng),
            ("Umkreis der Suche", self.radius),
            ("Arbeitsweg höchstens", self.commute),
            ("Pensum von", self.workload_min),
            ("Pensum bis", self.workload_max),
            ("Kantone (leer = alle)", self.cantons),
            ("Nicht anzeigen (Komma)", self.exclude),
            ("Sortierung", self.order),
            ("Treffer pro Seite", self.page_size),
            ("Seiten je Suchbegriff", self.max_pages),
            ("Anzeigen höchstens alt", self.max_age),
        ):
            search_form.addRow(label, field)
        hint = QLabel(
            "Ort, Ortskennung und Koordinaten stehen in der Adresszeile von "
            "ostjob.ch, wenn dort eine Umkreissuche läuft. Ohne Koordinaten "
            "entfällt die Entfernungsangabe."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        search_form.addRow("", hint)
        inner.addWidget(search)

        # ------------------------------------------------------------------
        matching = QGroupBox("Bewerbungen")
        matching_form = QFormLayout(matching)
        self.auto_draft = QCheckBox(
            "Passende Stellen automatisch als Outlook-Entwurf vorbereiten"
        )
        self.min_score = QSpinBox()
        self.min_score.setRange(1, 10)
        self.max_drafts = QSpinBox()
        self.max_drafts.setRange(0, 50)
        matching_form.addRow("", self.auto_draft)
        matching_form.addRow("Mindestens passende Stichworte", self.min_score)
        matching_form.addRow("Entwürfe pro Lauf höchstens", self.max_drafts)
        inner.addWidget(matching)

        # ------------------------------------------------------------------
        ai = QGroupBox("KI (optional)")
        ai_form = QFormLayout(ai)
        self.ai_enabled = QCheckBox("KI für Stichworte und Antworten verwenden")
        self.ai_url = QLineEdit()
        self.ai_url.setPlaceholderText("https://api.openai.com/v1")
        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText("gpt-4o-mini")
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key.setPlaceholderText("API-Schlüssel")
        for label, field in (
            ("", self.ai_enabled),
            ("Adresse (OpenAI-kompatibel)", self.ai_url),
            ("Modell", self.ai_model),
            ("Schlüssel", self.ai_key),
        ):
            ai_form.addRow(label, field)
        ai_hint = QLabel(
            "Ohne KI arbeitet AutoApplication mit den Stichworten des Portals "
            "und den Stichworten der Vorlagen weiter. Der Schlüssel lässt sich "
            "auch über die Umgebungsvariable AUTOAPPLICATION_AI_KEY setzen."
        )
        ai_hint.setWordWrap(True)
        ai_hint.setObjectName("Hint")
        ai_form.addRow("", ai_hint)
        inner.addWidget(ai)

        # ------------------------------------------------------------------
        outlook = QGroupBox("Outlook (Microsoft Graph)")
        outlook_form = QFormLayout(outlook)
        self.outlook_enabled = QCheckBox("Bewerbungen in Outlook ablegen")
        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("Client-ID der App-Registrierung")
        self.tenant = QLineEdit()
        self.tenant.setPlaceholderText("common")
        self.account = QLineEdit()
        self.account.setPlaceholderText("Ihre Outlook-Adresse (optional)")
        self.outlook_status = QLabel("")
        self.outlook_status.setObjectName("Hint")
        connect_row = QWidget()
        connect_layout = QHBoxLayout(connect_row)
        connect_layout.setContentsMargins(0, 0, 0, 0)
        self.connect_button = QPushButton("Anmelden")
        self.connect_button.setObjectName("Primary")
        self.connect_button.clicked.connect(self.connect_outlook)
        self.disconnect_button = QPushButton("Trennen")
        self.disconnect_button.clicked.connect(self.disconnect_outlook)
        connect_layout.addWidget(self.connect_button)
        connect_layout.addWidget(self.disconnect_button)
        connect_layout.addWidget(self.outlook_status, 1)
        outlook_form.addRow("", self.outlook_enabled)
        outlook_form.addRow("Client-ID", self.client_id)
        outlook_form.addRow("Mandant", self.tenant)
        outlook_form.addRow("Konto", self.account)
        outlook_form.addRow("", connect_row)
        outlook_hint = QLabel(
            "Anmeldung ohne Passwort im Programm. In der App-Registrierung "
            "(Microsoft Entra) muss „Mobile and desktop applications“ gewählt "
            "sein; Berechtigungen: Mail.ReadWrite, Mail.Send, User.Read. "
            "Der Entwurf landet im Ordner Entwürfe und wird von Hand versendet."
        )
        outlook_hint.setWordWrap(True)
        outlook_hint.setObjectName("Hint")
        outlook_form.addRow("", outlook_hint)
        inner.addWidget(outlook)

        # ------------------------------------------------------------------
        documents = QGroupBox("Unterlagen")
        documents_form = QFormLayout(documents)
        folder_row = QWidget()
        folder_layout = QHBoxLayout(folder_row)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        self.documents_folder = QLineEdit()
        choose = QPushButton("Ordner wählen …")
        choose.clicked.connect(self.choose_folder)
        folder_layout.addWidget(self.documents_folder, 1)
        folder_layout.addWidget(choose)
        self.attach = QCheckBox("Unterlagen an jede Bewerbung anhängen")
        self.max_mb = QSpinBox()
        self.max_mb.setRange(1, 40)
        self.max_mb.setSuffix(" MB")
        documents_form.addRow("Ordner", folder_row)
        documents_form.addRow("", self.attach)
        documents_form.addRow("Anhänge höchstens", self.max_mb)
        documents_hint = QLabel(
            "Alle PDF-, Word- und Bilddateien im Ordner werden angehängt – "
            "Lebenslauf und Zeugnisse zuerst, wenn sie so heissen."
        )
        documents_hint.setWordWrap(True)
        documents_hint.setObjectName("Hint")
        documents_form.addRow("", documents_hint)
        inner.addWidget(documents)

        # ------------------------------------------------------------------
        automation = QGroupBox("Automatik")
        automation_form = QFormLayout(automation)
        self.daily_time = QLineEdit()
        self.daily_time.setPlaceholderText("07:30")
        self.auto_on_start = QCheckBox("Beim Start einen Tageslauf ausführen")
        self.check_replies = QCheckBox("Posteingang regelmässig prüfen")
        self.follow_up_days = QSpinBox()
        self.follow_up_days.setRange(1, 90)
        self.follow_up_days.setSuffix(" Tage")
        self.notify_desktop = QCheckBox("Hinweise als Windows-Benachrichtigung")
        for label, field in (
            ("Täglicher Lauf um", self.daily_time),
            ("", self.auto_on_start),
            ("", self.check_replies),
            ("Nachfrage ohne Antwort nach", self.follow_up_days),
            ("", self.notify_desktop),
        ):
            automation_form.addRow(label, field)
        inner.addWidget(automation)

        save_row = QHBoxLayout()
        self.save_button = QPushButton("Einstellungen speichern")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.save)
        save_row.addWidget(self.save_button)
        save_row.addStretch(1)
        inner.addLayout(save_row)
        inner.addStretch(1)

        self.load()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        """Beim Seitenwechsel nur den Verbindungsstatus nachfuehren.

        Die Eingabefelder bleiben stehen, damit ein halb ausgefuelltes
        Formular nicht verloren geht.
        """
        self._refresh_outlook_status()

    def load(self) -> None:
        settings = self.window.settings
        self.vorname.setText(settings.text("profile.vorname"))
        self.nachname.setText(settings.text("profile.nachname"))
        self.strasse.setText(settings.text("profile.strasse"))
        self.plz.setText(settings.text("profile.plz"))
        self.wohnort.setText(settings.text("profile.wohnort"))
        self.telefon.setText(settings.text("profile.telefon"))
        self.email.setText(settings.text("profile.email"))
        self.erfahrung.setText(settings.text("profile.erfahrung_jahre"))
        self.verfuegbar.setText(settings.text("profile.verfuegbar"))

        self.queries.setPlainText("\n".join(settings.search_terms()))
        self.place.setText(settings.text("search.place"))
        self.place_code.setText(settings.text("search.place_code"))
        self.place_value.setText(settings.text("search.place_value"))
        self.lat.setText(settings.text("search.lat"))
        self.lng.setText(settings.text("search.lng"))
        self.radius.setValue(int(settings.number("search.radius_km", 25)))
        self.commute.setValue(int(settings.number("search.max_commute_km", 45)))
        self.workload_min.setValue(int(settings.number("search.workload_min", 60)))
        self.workload_max.setValue(int(settings.number("search.workload_max", 100)))
        self.cantons.setText(settings.text("search.cantons"))
        self.exclude.setText(settings.text("search.exclude"))
        index = self.order.findData(settings.text("search.order", "by_relevance"))
        self.order.setCurrentIndex(index if index >= 0 else 0)
        self.page_size.setValue(int(settings.number("search.page_size", 25)))
        self.max_pages.setValue(int(settings.number("search.max_pages", 3)))
        self.max_age.setValue(int(settings.number("search.max_age_days", 45)))

        self.auto_draft.setChecked(settings.flag("matching.auto_draft", True))
        self.min_score.setValue(int(settings.number("matching.min_score", 2)))
        self.max_drafts.setValue(int(settings.number("matching.max_drafts_per_run", 5)))

        self.ai_enabled.setChecked(settings.flag("ai.enabled"))
        self.ai_url.setText(settings.text("ai.base_url"))
        self.ai_model.setText(settings.text("ai.model"))
        self.ai_key.setText(settings.text("ai.api_key"))

        self.outlook_enabled.setChecked(settings.flag("outlook.enabled"))
        self.client_id.setText(settings.text("outlook.client_id"))
        self.tenant.setText(settings.text("outlook.tenant", "common"))
        self.account.setText(settings.text("outlook.account"))

        self.documents_folder.setText(settings.text("documents.folder"))
        self.attach.setChecked(settings.flag("documents.attach", True))
        self.max_mb.setValue(int(settings.number("documents.max_mb", 20)))

        self.daily_time.setText(settings.text("automation.daily_time", "07:30"))
        self.auto_on_start.setChecked(settings.flag("automation.auto_on_start", True))
        self.check_replies.setChecked(settings.flag("automation.check_replies", True))
        self.follow_up_days.setValue(int(settings.number("automation.follow_up_days", 14)))
        self.notify_desktop.setChecked(settings.flag("automation.notify_desktop", True))
        self._refresh_outlook_status()

    # ------------------------------------------------------------------
    def save(self) -> None:
        time_text = self.daily_time.text().strip()
        if time_text and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", time_text):
            QMessageBox.warning(
                self, "Uhrzeit", "Bitte die Uhrzeit als HH:MM angeben, z. B. 07:30."
            )
            return
        settings = self.window.settings
        settings.set("profile.vorname", self.vorname.text().strip())
        settings.set("profile.nachname", self.nachname.text().strip())
        settings.set("profile.strasse", self.strasse.text().strip())
        settings.set("profile.plz", self.plz.text().strip())
        settings.set("profile.wohnort", self.wohnort.text().strip())
        settings.set("profile.telefon", self.telefon.text().strip())
        settings.set("profile.email", self.email.text().strip())
        settings.set("profile.erfahrung_jahre", self.erfahrung.text().strip())
        settings.set("profile.verfuegbar", self.verfuegbar.text().strip())

        terms = [
            part.strip()
            for part in re.split(r"[\n,;]", self.queries.toPlainText())
            if part.strip()
        ]
        settings.set("search.queries", terms or [""])
        settings.set("search.place", self.place.text().strip())
        settings.set("search.place_code", self.place_code.text().strip())
        settings.set("search.place_value", self.place_value.text().strip())
        settings.set("search.lat", self.lat.text().strip().replace(",", "."))
        settings.set("search.lng", self.lng.text().strip().replace(",", "."))
        settings.set("search.radius_km", self.radius.value())
        settings.set("search.max_commute_km", self.commute.value())
        settings.set("search.workload_min", self.workload_min.value())
        settings.set("search.workload_max", self.workload_max.value())
        settings.set("search.cantons", self.cantons.text().strip())
        settings.set("search.exclude", self.exclude.text().strip())
        settings.set("search.order", self.order.currentData() or self.order.currentText())
        settings.set("search.page_size", self.page_size.value())
        settings.set("search.max_pages", self.max_pages.value())
        settings.set("search.max_age_days", self.max_age.value())

        settings.set("matching.auto_draft", self.auto_draft.isChecked())
        settings.set("matching.min_score", self.min_score.value())
        settings.set("matching.max_drafts_per_run", self.max_drafts.value())

        settings.set("ai.enabled", self.ai_enabled.isChecked())
        settings.set("ai.base_url", self.ai_url.text().strip())
        settings.set("ai.model", self.ai_model.text().strip())
        settings.set("ai.api_key", self.ai_key.text().strip())

        settings.set("outlook.enabled", self.outlook_enabled.isChecked())
        settings.set("outlook.client_id", self.client_id.text().strip())
        settings.set("outlook.tenant", self.tenant.text().strip() or "common")
        settings.set("outlook.account", self.account.text().strip())

        settings.set("documents.folder", self.documents_folder.text().strip())
        settings.set("documents.attach", self.attach.isChecked())
        settings.set("documents.max_mb", self.max_mb.value())

        settings.set("automation.daily_time", time_text or "07:30")
        settings.set("automation.auto_on_start", self.auto_on_start.isChecked())
        settings.set("automation.check_replies", self.check_replies.isChecked())
        settings.set("automation.follow_up_days", self.follow_up_days.value())
        settings.set("automation.notify_desktop", self.notify_desktop.isChecked())
        settings.save()
        self.window.reload_settings()
        self._refresh_outlook_status()
        self.window.store.log("einstellungen", "Einstellungen gespeichert.")
        self.window.statusBar().showMessage("Einstellungen gespeichert.", 6000)

    # ------------------------------------------------------------------
    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Ordner mit Unterlagen wählen", self.documents_folder.text()
        )
        if folder:
            self.documents_folder.setText(folder)

    def _refresh_outlook_status(self) -> None:
        try:
            connected = self.window.pipeline.auth().connected()
        except Exception:  # noqa: BLE001 - Statusanzeige darf nichts stoppen
            connected = False
        if connected:
            self.outlook_status.setText("● verbunden")
            self.outlook_status.setObjectName("Ok")
        else:
            self.outlook_status.setText("○ nicht verbunden")
            self.outlook_status.setObjectName("Hint")
        self.outlook_status.style().unpolish(self.outlook_status)
        self.outlook_status.style().polish(self.outlook_status)
        self.disconnect_button.setEnabled(connected)

    def connect_outlook(self) -> None:
        if not self.client_id.text().strip():
            QMessageBox.warning(
                self,
                "Client-ID fehlt",
                "Bitte zuerst die Client-ID der App-Registrierung eintragen und "
                "speichern.",
            )
            return
        self.save()
        dialog = DeviceLoginDialog(self.window, self.window.pipeline.auth())
        if dialog.exec():
            self.outlook_enabled.setChecked(True)
            self.save()
            self.window.store.log("outlook", "Outlook verbunden.")
            QMessageBox.information(
                self, "Outlook", "Outlook ist verbunden. Entwürfe werden ab jetzt abgelegt."
            )
        else:
            self._refresh_outlook_status()

    def disconnect_outlook(self) -> None:
        answer = QMessageBox.question(
            self, "Outlook trennen", "Die gespeicherte Anmeldung wirklich entfernen?"
        )
        if answer != QMessageBox.Yes:
            return
        self.window.pipeline.auth().disconnect()
        self.window.store.log("outlook", "Outlook getrennt.")
        self._refresh_outlook_status()
