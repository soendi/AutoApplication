"""Einstellungen: Person, Suche, KI, E-Mail, Unterlagen, Automatik."""

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

from ..core.ai import GROQ_BASE, GROQ_MODEL, OPENAI_BASE, OPENAI_MODEL
from ..core.imap_mail import GmailImapClient
from .dialogs import DeviceLoginDialog
from .workers import Task

MAIL_PROVIDERS = (
    ("Outlook (Microsoft Graph)", "outlook"),
    ("Gmail (IMAP/SMTP, App-Passwort)", "imap"),
    ("Keine – nur im Programm", "none"),
)

AI_PROVIDERS = (
    ("OpenAI oder kompatible Schnittstelle", "openai"),
    ("Groq", "groq"),
)


def _split_terms(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[\n,;]", value)]
    return [part for part in parts if part]


class SettingsPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        self._tasks: list[Task] = []

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
        self.erfahrung.setPlaceholderText("z. B. über zwanzig")
        self.verfuegbar = QLineEdit()
        self.verfuegbar.setPlaceholderText("z. B. sofort oder ab 1. März")
        self.interessen = QPlainTextEdit()
        self.interessen.setFixedHeight(58)
        self.interessen.setPlaceholderText("Stichworte, z. B. Logistik, Nachhaltigkeit, Kundenkontakt")
        self.faehigkeiten = QPlainTextEdit()
        self.faehigkeiten.setFixedHeight(58)
        self.faehigkeiten.setPlaceholderText("Stichworte, z. B. Disposition, SAP, Staplerschein")
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
            ("Interessen (Stichworte)", self.interessen),
            ("Fähigkeiten (Stichworte)", self.faehigkeiten),
        ):
            person_form.addRow(label, field)
        person_hint = QLabel(
            "Interessen und Fähigkeiten werden getrennt gespeichert und müssen "
            "sich nicht decken: Sie können etwas, interessieren sich aber eher "
            "für etwas anderes. Beides fliesst in die KI-Auswertung ein."
        )
        person_hint.setWordWrap(True)
        person_hint.setObjectName("Hint")
        person_form.addRow("", person_hint)
        inner.addWidget(person)

        # ------------------------------------------------------------------
        search = QGroupBox("Suche auf ostjob.ch")
        search_form = QFormLayout(search)
        self.api_enabled = QCheckBox(
            "Stellen über die API von ostjob.ch abrufen (Standard: aus)"
        )
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
        search_form.addRow("", self.api_enabled)
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
            "Ohne Häkchen oben fragt AutoApplication die Stellen-API nicht ab – "
            "weder beim Start noch beim täglichen Lauf noch über „Jetzt Stellen "
            "suchen“. Ort, Ortskennung und Koordinaten stehen in der Adresszeile "
            "von ostjob.ch, wenn dort eine Umkreissuche läuft. Ohne Koordinaten "
            "entfällt die Entfernungsangabe."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        search_form.addRow("", hint)
        inner.addWidget(search)

        # ------------------------------------------------------------------
        matching = QGroupBox("Bewerbungen")
        matching_form = QFormLayout(matching)
        self.min_score = QSpinBox()
        self.min_score.setRange(1, 10)
        matching_form.addRow("Mindestens passende Stichworte", self.min_score)
        matching_hint = QLabel(
            "Gefundene Stellen werden nur vorgemerkt. Den Entwurf bereiten Sie "
            "in der Stellenliste mit einem Klick vor – erst dann entsteht eine "
            "E-Mail. Als passend gilt eine Stelle, wenn ein Stichwort im Titel "
            "steht oder deutlich mehr Stichworte in der Anzeige vorkommen."
        )
        matching_hint.setWordWrap(True)
        matching_hint.setObjectName("Hint")
        matching_form.addRow("", matching_hint)
        inner.addWidget(matching)

        # ------------------------------------------------------------------
        ai = QGroupBox("KI (optional)")
        ai_form = QFormLayout(ai)
        self.ai_enabled = QCheckBox("KI für Stichworte und Antworten verwenden")
        self.ai_provider = QComboBox()
        for label, value in AI_PROVIDERS:
            self.ai_provider.addItem(label, value)
        self.ai_provider.currentIndexChanged.connect(self._ai_provider_changed)
        self.ai_url = QLineEdit()
        self.ai_url.setPlaceholderText(OPENAI_BASE)
        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText(OPENAI_MODEL)
        self.ai_key = QLineEdit()
        self.ai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.ai_key.setPlaceholderText("API-Schlüssel")
        for label, field in (
            ("", self.ai_enabled),
            ("Anbieter", self.ai_provider),
            ("Adresse (OpenAI-kompatibel)", self.ai_url),
            ("Modell", self.ai_model),
            ("Schlüssel", self.ai_key),
        ):
            ai_form.addRow(label, field)
        ai_hint = QLabel(
            "Groq ist OpenAI-kompatibel: Anbieter wählen, Schlüssel von Groq "
            "eintragen, fertig. Ohne KI arbeitet AutoApplication mit den "
            "Stichworten des Portals und den Stichworten der Vorlagen weiter. "
            "Der Schlüssel lässt sich auch über die Umgebungsvariable "
            "AUTOAPPLICATION_AI_KEY oder GROQ_API_KEY setzen."
        )
        ai_hint.setWordWrap(True)
        ai_hint.setObjectName("Hint")
        ai_form.addRow("", ai_hint)
        inner.addWidget(ai)

        # ------------------------------------------------------------------
        mail = QGroupBox("E-Mail-Anbindung")
        mail_form = QFormLayout(mail)
        self.mail_provider = QComboBox()
        for label, value in MAIL_PROVIDERS:
            self.mail_provider.addItem(label, value)
        mail_form.addRow("Bewerbungen ablegen mit", self.mail_provider)
        mail_hint = QLabel(
            "Der Entwurf landet im Ordner Entwürfe des gewählten Kontos und wird "
            "von Hand versendet. Ohne Anbindung bleibt der Text nur im Programm."
        )
        mail_hint.setWordWrap(True)
        mail_hint.setObjectName("Hint")
        mail_form.addRow("", mail_hint)
        inner.addWidget(mail)

        # ------------------------------------------------------------------
        outlook = QGroupBox("Outlook (Microsoft Graph)")
        outlook_form = QFormLayout(outlook)
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
        outlook_form.addRow("Client-ID", self.client_id)
        outlook_form.addRow("Mandant", self.tenant)
        outlook_form.addRow("Konto", self.account)
        outlook_form.addRow("", connect_row)
        outlook_hint = QLabel(
            "Anmeldung ohne Passwort im Programm. In der App-Registrierung "
            "(Microsoft Entra) muss „Mobile and desktop applications“ gewählt "
            "sein; Berechtigungen: Mail.ReadWrite, Mail.Send, User.Read."
        )
        outlook_hint.setWordWrap(True)
        outlook_hint.setObjectName("Hint")
        outlook_form.addRow("", outlook_hint)
        inner.addWidget(outlook)

        # ------------------------------------------------------------------
        imap = QGroupBox("Gmail (IMAP/SMTP)")
        imap_form = QFormLayout(imap)
        self.imap_email = QLineEdit()
        self.imap_email.setPlaceholderText("ihre.adresse@gmail.com")
        self.imap_password = QLineEdit()
        self.imap_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.imap_password.setPlaceholderText("16-stelliges App-Passwort")
        self.imap_status = QLabel("")
        self.imap_status.setObjectName("Hint")
        imap_row = QWidget()
        imap_layout = QHBoxLayout(imap_row)
        imap_layout.setContentsMargins(0, 0, 0, 0)
        self.imap_test_button = QPushButton("Verbindung testen")
        self.imap_test_button.clicked.connect(self.test_imap)
        imap_layout.addWidget(self.imap_test_button)
        imap_layout.addWidget(self.imap_status, 1)
        imap_form.addRow("Gmail-Adresse", self.imap_email)
        imap_form.addRow("App-Passwort", self.imap_password)
        imap_form.addRow("", imap_row)
        imap_hint = QLabel(
            "Im Google-Konto die 2-Faktor-Authentifizierung aktivieren, dann "
            "unter Sicherheit > App-Passwörter eines für AutoApplication "
            "erzeugen und hier eintragen. Entwürfe landen in Gmail unter "
            "Entwürfe, gesendet wird über smtp.gmail.com. Das App-Passwort "
            "bleibt lokal in den Einstellungen."
        )
        imap_hint.setWordWrap(True)
        imap_hint.setObjectName("Hint")
        imap_form.addRow("", imap_hint)
        inner.addWidget(imap)

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
        self.cover_letter = QCheckBox(
            "Anschreiben als PDF anhängen (von der KI geschrieben)"
        )
        self.max_mb = QSpinBox()
        self.max_mb.setRange(1, 40)
        self.max_mb.setSuffix(" MB")
        documents_form.addRow("Ordner", folder_row)
        documents_form.addRow("", self.attach)
        documents_form.addRow("", self.cover_letter)
        documents_form.addRow("Anhänge höchstens", self.max_mb)
        documents_hint = QLabel(
            "Alle PDF-, Word- und Bilddateien im Ordner werden angehängt – "
            "Lebenslauf und Zeugnisse zuerst, wenn sie so heissen. Das "
            "Anschreiben entsteht aus der KI und wird als PDF vorangestellt; "
            "ohne KI wird der Vorlagentext verwendet."
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
        self._refresh_imap_status()

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
        self.interessen.setPlainText(", ".join(settings.interests()))
        self.faehigkeiten.setPlainText(", ".join(settings.skills()))

        self.api_enabled.setChecked(settings.flag("search.api_enabled", False))
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

        self.min_score.setValue(int(settings.number("matching.min_score", 2)))

        self.ai_enabled.setChecked(settings.flag("ai.enabled"))
        provider = settings.text("ai.provider", "openai").strip().lower()
        ai_index = self.ai_provider.findData(provider)
        self.ai_provider.blockSignals(True)
        self.ai_provider.setCurrentIndex(ai_index if ai_index >= 0 else 0)
        self.ai_provider.blockSignals(False)
        self.ai_url.setText(settings.text("ai.base_url"))
        self.ai_model.setText(settings.text("ai.model"))
        self.ai_key.setText(settings.text("ai.api_key"))

        provider = settings.mail_provider()
        mail_index = self.mail_provider.findData(provider)
        self.mail_provider.setCurrentIndex(mail_index if mail_index >= 0 else 0)
        self.client_id.setText(settings.text("outlook.client_id"))
        self.tenant.setText(settings.text("outlook.tenant", "common"))
        self.account.setText(settings.text("outlook.account"))
        self.imap_email.setText(settings.text("imap.email"))
        self.imap_password.setText(settings.text("imap.password"))

        self.documents_folder.setText(settings.text("documents.folder"))
        self.attach.setChecked(settings.flag("documents.attach", True))
        self.cover_letter.setChecked(settings.flag("documents.cover_letter", True))
        self.max_mb.setValue(int(settings.number("documents.max_mb", 20)))

        self.daily_time.setText(settings.text("automation.daily_time", "07:30"))
        self.auto_on_start.setChecked(settings.flag("automation.auto_on_start", True))
        self.check_replies.setChecked(settings.flag("automation.check_replies", True))
        self.follow_up_days.setValue(int(settings.number("automation.follow_up_days", 14)))
        self.notify_desktop.setChecked(settings.flag("automation.notify_desktop", True))
        self._refresh_outlook_status()
        self._refresh_imap_status()

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
        settings.set("profile.interessen", _split_terms(self.interessen.toPlainText()))
        settings.set("profile.faehigkeiten", _split_terms(self.faehigkeiten.toPlainText()))

        terms = [
            part.strip()
            for part in re.split(r"[\n,;]", self.queries.toPlainText())
            if part.strip()
        ]
        settings.set("search.api_enabled", self.api_enabled.isChecked())
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

        settings.set("matching.min_score", self.min_score.value())

        settings.set("ai.enabled", self.ai_enabled.isChecked())
        settings.set("ai.provider", self.ai_provider.currentData() or "openai")
        settings.set("ai.base_url", self.ai_url.text().strip())
        settings.set("ai.model", self.ai_model.text().strip())
        settings.set("ai.api_key", self.ai_key.text().strip())

        provider = self.mail_provider.currentData() or "outlook"
        settings.set("mail.provider", provider)
        settings.set("outlook.enabled", provider == "outlook")
        settings.set("outlook.client_id", self.client_id.text().strip())
        settings.set("outlook.tenant", self.tenant.text().strip() or "common")
        settings.set("outlook.account", self.account.text().strip())
        settings.set("imap.email", self.imap_email.text().strip())
        settings.set("imap.password", self.imap_password.text())

        settings.set("documents.folder", self.documents_folder.text().strip())
        settings.set("documents.attach", self.attach.isChecked())
        settings.set("documents.cover_letter", self.cover_letter.isChecked())
        settings.set("documents.max_mb", self.max_mb.value())

        settings.set("automation.daily_time", time_text or "07:30")
        settings.set("automation.auto_on_start", self.auto_on_start.isChecked())
        settings.set("automation.check_replies", self.check_replies.isChecked())
        settings.set("automation.follow_up_days", self.follow_up_days.value())
        settings.set("automation.notify_desktop", self.notify_desktop.isChecked())
        settings.save()
        self.window.reload_settings()
        self._refresh_outlook_status()
        self._refresh_imap_status()
        self.window.store.log("einstellungen", "Einstellungen gespeichert.")
        self.window.statusBar().showMessage("Einstellungen gespeichert.", 6000)

    # ------------------------------------------------------------------
    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Ordner mit Unterlagen wählen", self.documents_folder.text()
        )
        if folder:
            self.documents_folder.setText(folder)

    def _ai_provider_changed(self) -> None:
        provider = self.ai_provider.currentData() or "openai"
        base, model = (
            (GROQ_BASE, GROQ_MODEL) if provider == "groq" else (OPENAI_BASE, OPENAI_MODEL)
        )
        current = self.ai_url.text().strip().rstrip("/")
        if not current or current in {GROQ_BASE, OPENAI_BASE}:
            self.ai_url.setText(base)
        current_model = self.ai_model.text().strip()
        if not current_model or current_model in {GROQ_MODEL, OPENAI_MODEL}:
            self.ai_model.setText(model)

    def _refresh_outlook_status(self) -> None:
        try:
            connected = self.window.pipeline.auth().connected()
        except Exception:  # noqa: BLE001 - Statusanzeige darf nichts stoppen
            connected = False
        self._set_status(self.outlook_status, connected)
        self.disconnect_button.setEnabled(connected)

    def _refresh_imap_status(self) -> None:
        ready = bool(self.imap_email.text().strip() and self.imap_password.text())
        self.imap_status.setText(
            "● App-Passwort gespeichert" if ready else "○ nicht eingerichtet"
        )
        self.imap_status.setObjectName("Ok" if ready else "Hint")
        self.imap_status.style().unpolish(self.imap_status)
        self.imap_status.style().polish(self.imap_status)

    def test_imap(self) -> None:
        email = self.imap_email.text().strip()
        password = self.imap_password.text()
        if not email or not password:
            QMessageBox.warning(
                self,
                "Gmail",
                "Bitte Gmail-Adresse und App-Passwort eintragen.",
            )
            return
        client = GmailImapClient(email, password)
        self.imap_test_button.setEnabled(False)
        self.imap_status.setText("Prüfe Verbindung …")
        task = Task(client.test_connection, self)
        self._tasks.append(task)
        task.done.connect(self._imap_ok)
        task.failed.connect(self._imap_failed)
        task.finished.connect(
            lambda: self._tasks.remove(task) if task in self._tasks else None
        )
        task.start()

    def _imap_ok(self, message: Any) -> None:
        self.imap_test_button.setEnabled(True)
        self.imap_status.setText("● verbunden")
        self.imap_status.setObjectName("Ok")
        self.imap_status.style().unpolish(self.imap_status)
        self.imap_status.style().polish(self.imap_status)
        QMessageBox.information(self, "Gmail", str(message))

    def _imap_failed(self, message: str) -> None:
        self.imap_test_button.setEnabled(True)
        self.imap_status.setText("○ nicht verbunden")
        self.imap_status.setObjectName("Hint")
        self.imap_status.style().unpolish(self.imap_status)
        self.imap_status.style().polish(self.imap_status)
        QMessageBox.warning(self, "Gmail", message)

    @staticmethod
    def _set_status(label: QLabel, connected: bool) -> None:
        label.setText("● verbunden" if connected else "○ nicht verbunden")
        label.setObjectName("Ok" if connected else "Hint")
        label.style().unpolish(label)
        label.style().polish(label)

    def connect_outlook(self) -> None:
        if not self.client_id.text().strip():
            QMessageBox.warning(
                self,
                "Client-ID fehlt",
                "Bitte zuerst die Client-ID der App-Registrierung eintragen und "
                "speichern.",
            )
            return
        self.mail_provider.setCurrentIndex(
            max(0, self.mail_provider.findData("outlook"))
        )
        self.save()
        dialog = DeviceLoginDialog(self.window, self.window.pipeline.auth())
        if dialog.exec():
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
