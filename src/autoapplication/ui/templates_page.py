"""Vorlagen: Anschreiben und Nachfragen bearbeiten."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ..core.templates import (
    Template,
    load_defaults,
    load_templates,
    save_templates,
)


class TemplatesPage(QWidget):
    def __init__(self, window: Any) -> None:
        super().__init__()
        self.window = window
        self.templates: list[Template] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        heading = QLabel("Vorlagen")
        heading.setObjectName("CardTitle")
        layout.addWidget(heading)
        hint = QLabel(
            "Eine Stelle gilt als passend, wenn ein Stichwort der Vorlage im "
            "Titel steht oder deutlich mehr Stichworte in der Anzeige "
            "vorkommen. Platzhalter: {anrede} (Herr/Frau mit Nachname, sonst "
            "allgemein), {ansprechperson}, {titel}, {firma}, {ort}, {pensum}, "
            "{stellen_id}, {vorname}, {nachname}, {erfahrung}, {verfuegbar}."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Hint")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        self.listing = QListWidget()
        self.listing.currentRowChanged.connect(self._load_selected)
        splitter.addWidget(self.listing)

        editor = QWidget()
        form = QFormLayout(editor)
        form.setContentsMargins(12, 0, 0, 0)
        self.name = QLineEdit()
        self.description = QLineEdit()
        self.keywords = QPlainTextEdit()
        self.keywords.setFixedHeight(80)
        self.keywords.setPlaceholderText("Ein Stichwort pro Zeile oder mit Komma getrennt")
        self.subject = QLineEdit()
        self.body = QPlainTextEdit()
        self.follow_up = QCheckBox("Diese Vorlage ist für Nachfragen")
        form.addRow("Name", self.name)
        form.addRow("Beschreibung", self.description)
        form.addRow("Stichworte", self.keywords)
        form.addRow("Betreff", self.subject)
        form.addRow("Text", self.body)
        form.addRow("", self.follow_up)
        splitter.addWidget(editor)
        splitter.setSizes([240, 640])
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("Speichern")
        self.save_button.setObjectName("Primary")
        self.save_button.clicked.connect(self.save_current)
        self.new_button = QPushButton("Neue Vorlage")
        self.new_button.clicked.connect(self.new_template)
        self.delete_button = QPushButton("Löschen")
        self.delete_button.clicked.connect(self.delete_current)
        self.restore_button = QPushButton("Standard wiederherstellen")
        self.restore_button.clicked.connect(self.restore_defaults)
        for button in (
            self.save_button,
            self.new_button,
            self.delete_button,
            self.restore_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        current = self._current_id()
        self.templates = load_templates(self.window.pipeline.templates_file)
        self.listing.clear()
        for template in self.templates:
            label = template.name + (" (Nachfrage)" if template.follow_up else "")
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, template.id)
            self.listing.addItem(item)
        index = 0
        for row, template in enumerate(self.templates):
            if template.id == current:
                index = row
        if self.templates:
            self.listing.setCurrentRow(index)
        else:
            self._clear()

    def _current_id(self) -> str:
        item = self.listing.currentItem()
        return str(item.data(Qt.UserRole)) if item else ""

    def _current(self) -> Template | None:
        identifier = self._current_id()
        for template in self.templates:
            if template.id == identifier:
                return template
        return None

    def _clear(self) -> None:
        self.name.clear()
        self.description.clear()
        self.keywords.clear()
        self.subject.clear()
        self.body.clear()
        self.follow_up.setChecked(False)

    def _load_selected(self, row: int) -> None:
        if not self.templates:
            self._clear()
            return
        template = self.templates[row] if 0 <= row < len(self.templates) else None
        if template is None:
            self._clear()
            return
        self.name.setText(template.name)
        self.description.setText(template.description)
        self.keywords.setPlainText("\n".join(template.keywords))
        self.subject.setText(template.subject)
        self.body.setPlainText(template.body)
        self.follow_up.setChecked(template.follow_up)

    # ------------------------------------------------------------------
    def _from_fields(self, identifier: str, revision: int = 0) -> Template:
        terms = [
            part.strip()
            for part in re.split(r"[\n,;]", self.keywords.toPlainText())
            if part.strip()
        ]
        return Template(
            id=identifier,
            name=self.name.text().strip() or identifier,
            description=self.description.text().strip(),
            keywords=terms,
            subject=self.subject.text().strip(),
            body=self.body.toPlainText().strip(),
            follow_up=self.follow_up.isChecked(),
            revision=revision,
        )

    def save_current(self) -> None:
        template = self._current()
        if template is None:
            self.new_template()
            return
        updated = self._from_fields(template.id, template.revision)
        for index, existing in enumerate(self.templates):
            if existing.id == template.id:
                self.templates[index] = updated
                break
        self._store()

    def new_template(self) -> None:
        base = "vorlage"
        existing = {template.id for template in self.templates}
        counter = 1
        identifier = base
        while identifier in existing:
            counter += 1
            identifier = f"{base}-{counter}"
        self._clear()
        self.name.setText("Neue Vorlage")
        self.body.setPlainText(
            "Sehr geehrte Damen und Herren\n\n"
            "…\n\nFreundliche Grüsse\n{vorname} {nachname}"
        )
        self.templates.append(Template(id=identifier, name="Neue Vorlage"))
        self._store()
        self.refresh()
        for row, template in enumerate(self.templates):
            if template.id == identifier:
                self.listing.setCurrentRow(row)

    def delete_current(self) -> None:
        template = self._current()
        if template is None:
            return
        answer = QMessageBox.question(
            self, "Vorlage löschen", f"Vorlage „{template.name}“ wirklich löschen?"
        )
        if answer != QMessageBox.Yes:
            return
        self.templates = [item for item in self.templates if item.id != template.id]
        self._store()
        self.refresh()

    def restore_defaults(self) -> None:
        answer = QMessageBox.question(
            self,
            "Standardvorlagen",
            "Alle eigenen Änderungen verwerfen und die Standardvorlagen laden?",
        )
        if answer != QMessageBox.Yes:
            return
        self.templates = load_defaults()
        self._store()
        self.refresh()

    def _store(self) -> None:
        save_templates(self.window.pipeline.templates_file, self.templates)
        self.window.store.log("vorlagen", "Vorlagen gespeichert.")
        self.window.statusBar().showMessage("Vorlagen gespeichert.", 5000)
