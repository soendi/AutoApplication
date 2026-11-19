"""Stellen: gefundene Anzeigen mit Passung und Aktionen."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
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

from ..core.matching import personal_fit, personal_match, priority_key
from ..core.templates import fallback_template, load_templates
from ..core.text import format_date, normalize
from .theme import FIT_COLORS, FIT_LABELS, fit_level

STATUS_LABELS = {
    "neu": "Neu",
    "ohne_passung": "Ohne Passung",
    "passend": "Passend",
    "allgemein": "Allgemein",
    "beworben": "Beworben",
    "ignoriert": "Ignoriert",
    "archiviert": "Archiviert",
    "zusage": "Zusage (Stelle)",
}

COLUMNS = (
    "",  # Haekchen: mehrere Stellen zusammen ignorieren
    "F",  # Bewerbungsformular
    "Vorlage",  # allgemein: nur die Auffangvorlage passt
    "Datum",
    "Titel",
    "Ansprechperson",
    "E-Mail",
    "Firma",
    "Ort",
    "Adresse",
    "PLZ",
    "Pensum",
    "Weg",
    "Interesse",
    "Fähigkeit",
    "Treffer",
    "Briefvorlage",
)

CHECK_COLUMN = 0

# Startbreiten; ab dem ersten Ziehen gilt, was der Benutzer eingestellt hat.
DEFAULT_WIDTHS = (
    34, 26, 95, 85, 210, 120, 175, 160, 100, 160, 55, 70, 55, 70, 75, 70, 170
)


def _sort_value(
    item: tuple[Any, list[str], list[str], int | None],
    column: int,
    general_id: str = "",
    names: dict[str, str] | None = None,
) -> Any:
    """Sortierwert einer Zeile passend zur sichtbaren Spalte."""
    job, interests, skills, percent = item
    if column == CHECK_COLUMN:
        return ""
    if column == 1:
        return 1 if job.get("has_form") else 0
    if column == 2:
        general = bool(general_id) and str(job.get("template_id") or "") == general_id
        return 1 if general else 0
    if column == 3:
        # ISO-Datum aus der Ablage sortiert richtig, auch wenn dd.mm. steht.
        return str(job.get("published") or job.get("first_seen") or "")
    if column == 4:
        return str(job.get("title") or "").casefold()
    if column == 5:
        return str(job.get("contact_name") or "").casefold()
    if column == 6:
        return str(job.get("contact_email") or "").casefold()
    if column == 7:
        return str(job.get("company") or "").casefold()
    if column == 8:
        return str(job.get("city") or "").casefold()
    if column == 9:
        return str(job.get("street") or "").casefold()
    if column == 10:
        zone = str(job.get("zip") or "")
        return int(zone) if zone.isdigit() else 0
    if column == 11:
        return str(job.get("workload") or "").casefold()
    if column == 12:
        distance = job.get("distance_km")
        # Ohne Angabe steht die Zeile vorne (aufsteigend) bzw. hinten.
        return float(distance) if distance is not None else -1.0
    if column == 13:
        return len(interests)
    if column == 14:
        return len(skills)
    if column == 15:
        return percent if percent is not None else -1
    template_name = (names or {}).get(str(job.get("template_id") or ""), "")
    if template_name:
        return template_name.casefold()
    status = str(job.get("status") or "")
    return STATUS_LABELS.get(status, status).casefold()


class SearchButton(QPushButton):
    """Knopf der Stellensuche; ein Doppelklick prueft alle Datensaetze."""

    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt-Name
        self.double_clicked.emit()
        event.accept()


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
        self.search.setPlaceholderText(
            "In Titel, Firma, Ort, Adresse, PLZ oder Stichworten suchen …"
        )
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
        # Stellen mit Bewerbungsformular (F) ausblenden. Der Zustand wird beim
        # Umschalten gespeichert und gilt beim naechsten Start wieder.
        self.hide_forms = QCheckBox("ohne Bewerbungsformulare")
        self.hide_forms.setToolTip(
            "Stellen mit einem Bewerbungsformular (F in der Spalte F) "
            "in der Tabelle ausblenden."
        )
        self.hide_forms.setChecked(
            self.window.settings.flag("search.hide_forms", False)
        )
        self.hide_forms.toggled.connect(self._hide_forms_changed)
        # Firmen aus der Jobvermittler-Liste ausblenden. Der Zustand wird
        # beim Umschalten gespeichert und gilt beim naechsten Start wieder.
        self.hide_brokers = QCheckBox("ohne Jobvermittler")
        self.hide_brokers.setToolTip(
            "Firmen aus der Liste «Jobvermittler» in der Tabelle ausblenden "
            "(Einstellungen → Ostjob)."
        )
        self.hide_brokers.setChecked(
            self.window.settings.flag("search.hide_job_brokers", False)
        )
        self.hide_brokers.toggled.connect(self._hide_brokers_changed)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.hide_forms)
        filters.addWidget(self.hide_brokers)
        filters.addWidget(self.status)
        self.search_button = SearchButton("Jetzt Stellen neu suchen")
        self.search_button.setToolTip(
            "Neue Anzeigen von ostjob.ch holen; bekannte Stellen bleiben stehen. "
            "Doppelklick: alle gespeicherten Stellen ohne Begrenzung prüfen."
        )
        # Ein einzelner Klick startet die Suche erst nach der Doppelklick-Zeit,
        # damit ein Doppelklick nicht zwei Laeufe ausloest.
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(QApplication.doubleClickInterval())
        self._search_timer.timeout.connect(self.window.run_search)
        self.search_button.clicked.connect(self._search_timer.start)
        self.search_button.double_clicked.connect(self._full_search)
        filters.addWidget(self.search_button)
        layout.addLayout(filters)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(list(COLUMNS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self._rows: list[dict[str, Any]] = []
        self._filling = False
        self._sort_column = -1
        self._sort_ascending = True
        # Breiten von Hand ziehbar. Sortiert wird in refresh(): die eingebaute
        # Tabellensortierung wuerde die Zeilen unter self._rows verdrehen.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSortIndicatorShown(True)
        header.setToolTip("Spaltenbreite ziehen · Klick auf den Kopf sortiert")
        header.sectionClicked.connect(self._sort_by_column)
        header.sectionResized.connect(self._queue_view_save)
        self._view_timer = QTimer(self)
        self._view_timer.setSingleShot(True)
        self._view_timer.setInterval(400)
        self._view_timer.timeout.connect(self._save_view_state)
        self._restore_view_state()
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.itemChanged.connect(self._item_changed)
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
        self.broker_button = QPushButton("Als Jobvermittler eintragen")
        self.broker_button.setToolTip(
            "Firma der markierten Zeile - oder aller angehakten Zeilen - in die "
            "Liste der Jobvermittler aufnehmen. Doppelte Eintraege werden "
            "uebersprungen."
        )
        self.broker_button.clicked.connect(self.mark_broker)
        for button in (
            self.prepare_button,
            self.open_button,
            self.ignore_button,
            self.broker_button,
        ):
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

    # ------------------------------------------------------------------
    # Spaltenbreiten und Sortierung: beim naechsten Start wieder so.
    # ------------------------------------------------------------------
    def _restore_view_state(self) -> None:
        widths = self.window.settings.get("ansicht.stellen_spalten", [])
        saved = widths if isinstance(widths, list) else []
        if len(saved) != len(COLUMNS):
            # Andere Spaltenzahl (z. B. vor dem Haekchen): Startbreiten.
            saved = []
        for column, default in enumerate(DEFAULT_WIDTHS):
            width = saved[column] if column < len(saved) else 0
            if not isinstance(width, int) or width < 30:
                width = default
            self.table.setColumnWidth(column, width)
        state = self.window.settings.get("ansicht.stellen_sortierung", {})
        if not isinstance(state, dict):
            return
        column = state.get("column", -1)
        if isinstance(column, int) and 0 <= column < len(COLUMNS):
            self._sort_column = column
            self._sort_ascending = bool(state.get("ascending", True))
            self.table.horizontalHeader().setSortIndicator(
                column, self._sort_order()
            )

    def _sort_order(self) -> Qt.SortOrder:
        return (
            Qt.SortOrder.AscendingOrder
            if self._sort_ascending
            else Qt.SortOrder.DescendingOrder
        )

    def _queue_view_save(self, *_args: Any) -> None:
        """Beim Ziehen nicht bei jedem Pixel schreiben, sondern kurz danach."""
        self._view_timer.start()

    def _save_view_state(self) -> None:
        widths = [
            self.table.columnWidth(column) for column in range(len(COLUMNS))
        ]
        self.window.settings.set("ansicht.stellen_spalten", widths)
        self.window.settings.set(
            "ansicht.stellen_sortierung",
            {"column": self._sort_column, "ascending": self._sort_ascending},
        )
        try:
            self.window.settings.save()
        except OSError:
            # Eine nicht schreibbare Einstellungsdatei darf die Ansicht nicht
            # blockieren; beim naechsten Start gelten dann die Startbreiten.
            pass

    def _sort_by_column(self, column: int) -> None:
        """Klick auf den Spaltenkopf: nach dieser Spalte sortieren."""
        if column == CHECK_COLUMN:
            return
        if column == self._sort_column:
            self._sort_ascending = not self._sort_ascending
        else:
            self._sort_column = column
            self._sort_ascending = True
        self.table.horizontalHeader().setSortIndicator(
            column, self._sort_order()
        )
        self._save_view_state()
        self.refresh()

    # ------------------------------------------------------------------
    def _hide_forms_changed(self, checked: bool) -> None:
        """Haekchen sofort merken - auch ohne «Speichern» in den Einstellungen."""
        self.window.settings.set("search.hide_forms", checked)
        try:
            self.window.settings.save()
        except OSError:
            # Eine nicht schreibbare Einstellungsdatei darf die Ansicht nicht
            # blockieren; dann gilt beim naechsten Start wieder der alte Wert.
            pass
        self.refresh()

    def _hide_brokers_changed(self, checked: bool) -> None:
        """Haekchen sofort merken - auch ohne «Speichern» in den Einstellungen."""
        self.window.settings.set("search.hide_job_brokers", checked)
        try:
            self.window.settings.save()
        except OSError:
            # Eine nicht schreibbare Einstellungsdatei darf die Ansicht nicht
            # blockieren; dann gilt beim naechsten Start wieder der alte Wert.
            pass
        self.refresh()

    def refresh(self) -> None:
        status = self.status.currentData() or None
        jobs = self.window.store.list_jobs(
            status=status or None, search=self.search.text()
        )
        if self.hide_forms.isChecked():
            jobs = [job for job in jobs if not job.get("has_form")]
        if self.hide_brokers.isChecked():
            brokers = {
                normalize(name) for name in self.window.settings.job_brokers()
            }
            if brokers:
                jobs = [
                    job
                    for job in jobs
                    if normalize(str(job.get("company") or "")) not in brokers
                ]
        interests = self.window.settings.interests()
        skills = self.window.settings.skills()
        # Welche Vorlage ist die Auffangvorlage? Nur sie wird als «allgemein»
        # gekennzeichnet - der Name bleibt frei waehlbar.
        templates = load_templates(self.window.pipeline.templates_file)
        general = fallback_template(templates)
        general_id = general.id if general is not None else ""
        names = {template.id: template.name for template in templates}
        decorated = []
        for job in jobs:
            hits = personal_match(job, interests, skills)
            decorated.append(
                (job, hits[0], hits[1], personal_fit(job, interests, skills))
            )
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
        if self._sort_column >= 0:
            # Nach der geklickten Spalte; der Titel bleibt als ruhiger
            # zweiter Wert, damit gleiche Werte nicht springen.
            decorated.sort(
                key=lambda item: (
                    _sort_value(item, self._sort_column, general_id, names),
                    str(item[0].get("title") or "").casefold(),
                ),
                reverse=not self._sort_ascending,
            )
        self._rows = [item[0] for item in decorated]
        min_score = int(self.window.settings.number("matching.min_score", 2) or 2)
        # Waehrend des Fuellens keine Rueckmeldung je Zelle auswerten.
        self._filling = True
        self.table.setRowCount(len(decorated))
        for row, (job, found_interests, found_skills, percent) in enumerate(decorated):
            level = fit_level(int(job.get("score") or 0), min_score)
            tint = QColor(FIT_COLORS[level])
            check = QTableWidgetItem("")
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsSelectable
            )
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setBackground(tint)
            check.setToolTip(
                "Anhaken, um diese Stelle zusammen mit anderen zu ignorieren."
            )
            check.setData(Qt.UserRole, job.get("id"))
            self.table.setItem(row, CHECK_COLUMN, check)
            uses_general = (
                bool(general_id)
                and str(job.get("template_id") or "") == general_id
            )
            values = (
                "F" if job.get("has_form") else "",
                "allgemein" if uses_general else "",
                format_date(job.get("published") or job.get("first_seen")),
                job.get("title") or "",
                job.get("contact_name") or "–",
                job.get("contact_email") or "–",
                job.get("company") or "",
                job.get("city") or "",
                job.get("street") or "–",
                job.get("zip") or "–",
                job.get("workload") or "",
                (
                    f"{job.get('distance_km'):.0f} km"
                    if job.get("distance_km") is not None
                    else ""
                ),
                str(len(found_interests)) if found_interests else "–",
                str(len(found_skills)) if found_skills else "–",
                "–" if percent is None else f"{percent} %",
                names.get(str(job.get("template_id") or ""), "")
                or STATUS_LABELS.get(
                    str(job.get("status") or ""), str(job.get("status") or "")
                ),
            )
            for column, value in enumerate(values, start=CHECK_COLUMN + 1):
                item = QTableWidgetItem(str(value))
                item.setBackground(tint)
                if column == 1:
                    if value:
                        item.setToolTip("Bewerbungsformular")
                elif column == 2:
                    if value:
                        item.setToolTip(
                            "Für diese Stelle passen keine oder zu wenige "
                            "Stichworte einer besonderen Vorlage. Das "
                            "Anschreiben entsteht deshalb mit der Allgemeinen "
                            "Vorlage."
                        )
                elif column == 5:
                    item.setToolTip(
                        "Ansprechperson aus der Anzeige"
                        if value != "–"
                        else "Die Anzeige nennt keine Ansprechperson"
                    )
                elif column == 6:
                    item.setToolTip(
                        "Bewerbungsadresse aus der Anzeige"
                        if value != "–"
                        else "Die Anzeige nennt keine E-Mail-Adresse"
                    )
                elif column in {9, 10}:
                    item.setToolTip(
                        "Adresse der Firma – aus dem Portal oder von der "
                        "Firmenwebsite"
                        if value != "–"
                        else "Adresse noch nicht gefunden"
                    )
                elif column == 13:
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
                elif column == 14:
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setToolTip(
                        "Fähigkeiten in der Anzeige: " + ", ".join(found_skills)
                        if found_skills
                        else "Keine Fähigkeit aus dem Profil in der Anzeige"
                    )
                elif column == 15:
                    item.setTextAlignment(Qt.AlignCenter)
                    if percent is None:
                        item.setToolTip(
                            "Im Profil sind keine Interessen oder Fähigkeiten "
                            "hinterlegt."
                        )
                    else:
                        item.setToolTip(
                            f"{percent} % der Stichworte aus Interessen und "
                            "Fähigkeiten stehen in der Anzeige.\n"
                            "Interessen: "
                            + (", ".join(found_interests) or "keine")
                            + "\nFähigkeiten: "
                            + (", ".join(found_skills) or "keine")
                        )
                elif column == 16:
                    item.setToolTip(
                        "Briefvorlage: "
                        + (
                            names.get(str(job.get("template_id") or ""), "")
                            or "noch keine bestimmt"
                        )
                        + "\nStatus: "
                        + STATUS_LABELS.get(
                            str(job.get("status") or ""),
                            str(job.get("status") or ""),
                        )
                    )
                if column in {1, 2, 3, 10, 11, 12, 13, 14, 15}:
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 2 and value:
                    item.setForeground(QColor("#e6a23c"))
                if column == 3:
                    item.setData(Qt.UserRole, job.get("id"))
                self.table.setItem(row, column, item)
            self.table.setRowHeight(row, 28)
        self._filling = False
        self.hint.setText(f"{len(self._rows)} Stellen")
        self._update_buttons()

    def _selected(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def _checked_jobs(self) -> list[dict[str, Any]]:
        """Alle angehakten Stellen, in der Reihenfolge der Tabelle."""
        checked: list[dict[str, Any]] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, CHECK_COLUMN)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            if row < len(self._rows):
                checked.append(self._rows[row])
        return checked

    def _item_changed(self, _item: QTableWidgetItem) -> None:
        if not self._filling:
            self._update_buttons()

    def _update_buttons(self) -> None:
        job = self._selected()
        checked = bool(self._checked_jobs())
        exists = (
            job is not None
            and self.window.store.application_by_job(str(job.get("id")))
        )
        self.prepare_button.setEnabled(job is not None and not exists)
        self.open_button.setEnabled(bool(job and job.get("url")))
        self.broker_button.setEnabled(job is not None or checked)
        self.ignore_button.setEnabled(checked or (job is not None and job.get("status") not in {"ignoriert", "beworben"}))

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
        # Gleich nachsehen, ob die Anzeige noch existiert; abgelaufene
        # Stellen verschwinden damit ohne naechsten Suchlauf.
        self.window.check_expired(str(job.get("id") or ""))

    def _full_search(self) -> None:
        """Doppelklick: alle gespeicherten Stellen ohne Begrenzung pruefen."""
        self._search_timer.stop()
        self.window.run_full_search()

    def mark_broker(self) -> None:
        """Firmen der markierten oder angehakten Stellen als Vermittler merken."""
        jobs = self._checked_jobs()
        if not jobs:
            job = self._selected()
            if job is None:
                return
            jobs = [job]
        names = self.window.settings.job_brokers()
        known = {normalize(name) for name in names}
        added: list[str] = []
        skipped = 0
        for job in jobs:
            company = " ".join(str(job.get("company") or "").split())
            if not company:
                continue
            key = normalize(company)
            if key in known:
                skipped += 1
                continue
            known.add(key)
            names.append(company)
            added.append(company)
        if not added:
            self.window.statusBar().showMessage(
                "Bereits als Jobvermittler eingetragen – nichts geändert.", 6000
            )
            return
        self.window.settings.set("search.job_brokers", names)
        try:
            self.window.settings.save()
        except OSError as exc:
            QMessageBox.warning(
                self, "Jobvermittler", f"Einstellungen nicht schreibbar: {exc}"
            )
            return
        page = getattr(self.window, "settings_page", None)
        if page is not None:
            page.reload_brokers()
        self.refresh()
        message = f"{len(added)} als Jobvermittler eingetragen: {', '.join(added)}"
        if skipped:
            message += f" ({skipped} bereits vorhanden)"
        self.window.statusBar().showMessage(message, 8000)

    def ignore(self) -> None:
        # Angehakte Stellen zuerst; ohne Haekchen gilt die ausgewaehlte Zeile.
        jobs = self._checked_jobs()
        if not jobs:
            job = self._selected()
            if job is None:
                return
            jobs = [job]
        if len(jobs) == 1:
            question = (
                f"„{jobs[0].get('title')}“ ausblenden? Es wird keine Bewerbung "
                "vorbereitet."
            )
        else:
            question = (
                f"{len(jobs)} Stellen ausblenden? Es wird keine Bewerbung "
                "vorbereitet."
            )
        answer = QMessageBox.question(self, "Stellen ignorieren", question)
        if answer != QMessageBox.Yes:
            return
        for job in jobs:
            self.window.store.update_job(str(job.get("id")), status="ignoriert")
            self.window.store.log(
                "stelle",
                f"Ignoriert: {job.get('title')} bei {job.get('company')}",
            )
        self.refresh()
        self.window.refresh_all()
