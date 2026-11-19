"""Bewerbungsvorlagen: Auswahl nach Stichworten und Text mit Platzhaltern."""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .models import Job
from .text import format_date, has_term, normalize, salutation, split_terms

log = logging.getLogger(__name__)

FOLLOW_UP_ID = "nachfassen"
# Fassung der Standardvorlagen. Steht in der Datei eine aeltere Fassung,
# werden die mitgelieferten Vorlagen nachgezogen (Revision je Vorlage).
TEMPLATES_VERSION = 4


@dataclass
class Template:
    id: str
    name: str
    description: str = ""
    keywords: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    follow_up: bool = False
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "keywords": list(self.keywords),
            "subject": self.subject,
            "body": self.body,
            "follow_up": self.follow_up,
            "revision": self.revision,
        }


def data_directory() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def default_templates_path() -> Path:
    return data_directory() / "templates.json"


def load_defaults() -> list[Template]:
    path = default_templates_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - Paketfehler
        log.error("Vorlagen im Programm fehlen: %s", exc)
        return []
    return _parse(payload)


def _parse(payload: Any) -> list[Template]:
    if isinstance(payload, dict):
        entries = payload.get("templates") or []
    else:
        entries = payload or []
    templates: list[Template] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier = str(entry.get("id") or "").strip()
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        keywords = entry.get("keywords") or []
        if isinstance(keywords, str):
            keywords = split_terms(keywords)
        templates.append(
            Template(
                id=identifier,
                name=str(entry.get("name") or identifier),
                description=str(entry.get("description") or ""),
                keywords=[str(item).strip() for item in keywords if str(item).strip()],
                subject=str(entry.get("subject") or ""),
                body=str(entry.get("body") or ""),
                follow_up=bool(entry.get("follow_up")),
                revision=_revision(entry.get("revision")),
            )
        )
    return templates


def _revision(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _version(payload: Any) -> int:
    if isinstance(payload, dict):
        return _revision(payload.get("version") or 1) or 1
    return 1


def save_templates(path: Path, templates: list[Template]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": TEMPLATES_VERSION,
        "templates": [item.to_dict() for item in templates],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


def load_templates(path: Path) -> list[Template]:
    """Vorlagen des Benutzers; beim ersten Start aus dem Programm kopiert."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        source = default_templates_path()
        try:
            shutil.copyfile(source, path)
        except OSError:
            templates = load_defaults()
            save_templates(path, templates)
            return templates
    version = TEMPLATES_VERSION
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        templates = _parse(payload)
        version = _version(payload)
    except (OSError, ValueError) as exc:
        log.warning("Vorlagen nicht lesbar (%s) - Standardvorlagen", exc)
        templates = load_defaults()
    templates = templates or load_defaults()
    changed = _upgrade(templates)
    if version < TEMPLATES_VERSION:
        changed = _refresh_defaults(templates) or changed
    if changed:
        try:
            save_templates(path, templates)
        except OSError as exc:
            log.warning("Vorlagen nicht speicherbar: %s", exc)
    return templates


def _refresh_defaults(templates: list[Template]) -> bool:
    """Veraltete Standardvorlagen ersetzen und neue dazunehmen.

    Eigene Vorlagen bleiben unangetastet; bearbeitete Standardvorlagen tragen
    die Revision mit und werden deshalb nicht ueberschrieben.
    """
    defaults = load_defaults()
    by_id = {template.id: template for template in defaults}
    changed = False
    for index, template in enumerate(templates):
        shipped = by_id.get(template.id)
        if shipped is not None and template.revision < shipped.revision:
            templates[index] = shipped
            changed = True
    known = {template.id for template in templates}
    for shipped in defaults:
        if shipped.id not in known:
            templates.append(shipped)
            changed = True
    return changed


def _upgrade(templates: list[Template]) -> bool:
    """Bestehende Vorlagen nachziehen (Anrede-Platzhalter, Branchen-Strenge)."""
    broad = {"Produktion", "Montage", "Maschinenbedienung"}
    changed = False
    for template in templates:
        if (
            "{anrede}" not in template.body
            and template.body.lstrip().startswith("Sehr geehrte Damen und Herren")
        ):
            template.body = template.body.replace(
                "Sehr geehrte Damen und Herren", "{anrede}", 1
            )
            changed = True
        if template.id == "lager":
            kept = [keyword for keyword in template.keywords if keyword not in broad]
            if kept != template.keywords:
                template.keywords = kept
                changed = True
    return changed


def vocabulary(templates: list[Template]) -> list[str]:
    """Alle Stichworte der Vorlagen (ohne Nachfrage-Vorlage)."""
    terms: list[str] = []
    seen: set[str] = set()
    for template in templates:
        if template.follow_up:
            continue
        for keyword in template.keywords:
            key = normalize(keyword)
            if key and key not in seen:
                seen.add(key)
                terms.append(keyword)
    return terms


def score_template(template: Template, job: Job, keywords: list[str]) -> tuple[int, list[str]]:
    """Wie viele Stichworte der Vorlage passen zu dieser Stelle?"""
    haystack = f"{job.title} {job.description} {job.keyword_text()} {job.company} {' '.join(keywords)}"
    matched: list[str] = []
    for keyword in template.keywords:
        if has_term(haystack, keyword):
            matched.append(keyword)
    return len(matched), matched


def choose_template(
    templates: list[Template],
    job: Job,
    keywords: list[str],
    min_score: int = 2,
) -> tuple[Template | None, int, list[str]]:
    """Beste Vorlage waehlen; ohne ausreichende Passung (None, ...).

    Verlangt mindestens ``min_score`` passende Stichworte - so entsteht keine
    Bewerbung fuer eine Stelle, die nur zufaellig ein Wort enthaelt.
    """
    best: Template | None = None
    best_rank = 0
    best_score = 0
    best_matches: list[str] = []
    best_title_hits: list[str] = []
    for template in templates:
        if template.follow_up:
            continue
        score, matched = score_template(template, job, keywords)
        title_hits = [item for item in matched if has_term(job.title, item)]
        rank = score + len(title_hits)  # Treffer im Titel wiegen doppelt
        if rank > best_rank:
            best, best_rank, best_score, best_matches = (
                template,
                rank,
                score,
                matched,
            )
            best_title_hits = title_hits
    needed = max(1, int(min_score))
    if best is None or best_score < needed:
        return None, best_score, best_matches
    # Ohne Treffer im Titel nur bei deutlich mehr Stichworten im Text: so
    # entstehen keine Bewerbungen fuer fremde Branchen.
    if not best_title_hits and best_score < needed + 1:
        return None, best_score, best_matches
    return best, best_score, best_matches


def follow_up_template(templates: list[Template]) -> Template | None:
    for template in templates:
        if template.follow_up:
            return template
    return None


class _SafeDict(dict[str, str]):
    def __missing__(self, key: str) -> str:  # pragma: no cover - Platzhalter
        return ""


def render(text: str, values: dict[str, Any]) -> str:
    """Platzhalter wie {firma} einsetzen; unbekannte bleiben leer."""
    safe = _SafeDict({key: str(value or "") for key, value in values.items()})
    try:
        return text.format_map(safe)
    except (ValueError, IndexError, KeyError):
        return text


def context_for(
    profile: dict[str, Any],
    job: Job | None = None,
    *,
    day: date | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Werte fuer die Platzhalter in Betreff und Text."""
    day = day or date.today()
    values: dict[str, Any] = {
        "vorname": profile.get("vorname", ""),
        "nachname": profile.get("nachname", ""),
        "strasse": profile.get("strasse", ""),
        "plz": profile.get("plz", ""),
        "wohnort": profile.get("wohnort", ""),
        "telefon": profile.get("telefon", ""),
        "email": profile.get("email", ""),
        "erfahrung": profile.get("erfahrung_jahre", ""),
        # Jahre in Spedition und Export - nicht die Gesamterfahrung.
        "erfahrung_spedition": (
            profile.get("erfahrung_spedition")
            or profile.get("erfahrung_jahre", "")
        ),
        "verfuegbar": profile.get("verfuegbar", ""),
        "interessen": profile.get("interessen", ""),
        "faehigkeiten": profile.get("faehigkeiten", ""),
        "datum": day.strftime("%d.%m.%Y"),
        "anrede": "Sehr geehrte Damen und Herren",
        "ansprechperson": "",
        "firma": "",
        "titel": "",
        "ort": "",
        "pensum": "",
        "stellen_id": "",
        "quelle": "ostjob.ch",
        "bewerbungsdatum": "",
        "tage": "",
    }
    if job is not None:
        values.update(
            {
                "firma": job.company,
                "titel": job.title,
                "ort": job.city,
                "pensum": job.workload,
                "stellen_id": job.source_id,
                "quelle": "ostjob.ch" if job.source == "ostjob" else job.source,
                "anrede": salutation(job.contact_name),
                "ansprechperson": job.contact_name,
            }
        )
    if extra:
        values.update({key: str(value) for key, value in extra.items()})
    return values


def render_mail(
    template: Template,
    profile: dict[str, Any],
    job: Job | None,
    *,
    day: date | None = None,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str]:
    values = context_for(profile, job, day=day, extra=extra)
    subject = re.sub(r"\s+", " ", render(template.subject, values)).strip()
    # Ohne Namen im Profil bleibt sonst ein Strich am Ende des Betreffs stehen.
    subject = re.sub(r"[\s\u2013-]+$", "", subject).strip()
    body = render(template.body, values).strip()
    return subject, body


def describe(template: Template | None, matches: list[str] | None = None) -> str:
    if template is None:
        return "keine passende Vorlage"
    if matches:
        return f"{template.name} ({', '.join(matches[:4])})"
    return template.name


def application_date_label(value: str | None) -> str:
    return format_date(value)
