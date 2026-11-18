"""Stichworte und Antwortauswertung - mit KI oder lokal.

Die KI ist optional. Ohne Schluessel arbeitet die Anwendung mit den Stichworten
des Stellenportals und einem Stichwortverzeichnis aus den Vorlagen weiter.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from .config import Settings
from .models import Job
from .templates import Template
from .text import (
    clean_job_text,
    clean_job_title,
    has_term,
    normalize,
    strip_html,
    words,
)

log = logging.getLogger(__name__)

OPENAI_BASE = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.3-70b-versatile"

ABSAGE = "absage"
ZUSAGE = "zusage"
EINLADUNG = "einladung"
INFO = "info"
UNBEKANNT = "unbekannt"

STOPWORDS = {
    "und",
    "oder",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "des",
    "ein",
    "eine",
    "einer",
    "eines",
    "fuer",
    "für",
    "mit",
    "von",
    "vom",
    "bei",
    "als",
    "auch",
    "sowie",
    "ihre",
    "ihrer",
    "unser",
    "unsere",
    "sie",
    "wir",
    "ist",
    "sind",
    "wird",
    "werden",
    "zum",
    "zur",
    "aus",
    "auf",
    "im",
    "in",
    "am",
    "an",
    "zu",
    "nach",
    "ueber",
    "über",
    "durch",
    "fuer",
    "pro",
    "plus",
    "alle",
    "mehr",
    "sehr",
    "gern",
    "gerne",
    "stellen",
    "stelle",
    "jobs",
    "job",
    "arbeit",
    "arbeiten",
}

# Lokale Auswertung: typische Formulierungen einer Absage, Zusage oder Einladung.
ABSAGE_PHRASES = (
    "absage",
    "sagen wir ihnen ab",
    "leider nicht beruecksichtigen",
    "leider nicht berücksichtigen",
    "nicht beruecksichtigen",
    "nicht berücksichtigen",
    "leider eine absage",
    "andere bewerber",
    "anderen bewerber",
    "andere bewerberin",
    "einen anderen",
    "entschieden, einen anderen",
    "entschieden haben, einen anderen",
    "bevorzugen",
    "nicht weiter beruecksichtigen",
    "nicht weiter berücksichtigen",
    "kein interesse an ihrer bewerbung",
    "koennen ihnen leider",
    "können ihnen leider",
    "leider mitteilen",
    "leider mit, dass",
    "leider muessen wir ihnen mitteilen",
    "leider müssen wir ihnen mitteilen",
    "leider absagen",
    "leider ab",
    "nicht in frage",
    "abgelehnt",
    "absagen",
    "verzichten",
    "absehen",
)

ZUSAGE_PHRASES = (
    "zusage",
    "herzlichen glueckwunsch",
    "herzlichen glückwunsch",
    "freuen uns, ihnen mitzuteilen",
    "stellen wir sie ein",
    "arbeitsvertrag",
    "vertragsentwurf",
    "willkommen im team",
    "sind sie unsere neue",
    "ihnen eine stelle anbieten",
    "ihre zusage",
    "wir moechten sie einstellen",
    "wir möchten sie einstellen",
)

EINLADUNG_PHRASES = (
    "vorstellungsgespraech",
    "vorstellungsgespräch",
    "einladung zum gespraech",
    "einladung zum gespräch",
    "kennenzulernen",
    "kennenlernen",
    "gespraechstermin",
    "gesprächstermin",
    "termin vereinbaren",
    "terminvorschlag",
    "interview",
    "zu einem gespraech",
    "zu einem gespräch",
    "persoenlich vorstellen",
    "persönlich vorstellen",
)


def _score_phrases(haystack: str, phrases: tuple[str, ...]) -> int:
    return sum(1 for phrase in phrases if phrase in haystack)


def classify_local(subject: str, body: str) -> str:
    """Antwort ohne KI einordnen - Absage zuerst, dann Zusage, dann Einladung."""
    haystack = normalize(f"{subject} {strip_html(body)}")
    absage = _score_phrases(haystack, ABSAGE_PHRASES)
    zusage = _score_phrases(haystack, ZUSAGE_PHRASES)
    einladung = _score_phrases(haystack, EINLADUNG_PHRASES)

    # Eine Einladung kann harmlos "leider erst jetzt" enthalten - die Absage
    # braucht deshalb mindestens zwei Formulierungen oder ein klares Wort.
    if absage >= 2 or "absage" in haystack or "abgelehnt" in haystack:
        return ABSAGE
    if zusage >= 1:
        return ZUSAGE
    if einladung >= 1:
        return EINLADUNG
    return INFO


@dataclass
class JobDigest:
    """Ausgelesene Anzeige: sauberer Titel, Beschreibung und Kontaktadresse."""

    title: str
    description: str
    contact_email: str = ""


def local_digest(job: Job) -> JobDigest:
    """Anzeige ohne KI aufbereiten: Gendermarken, IDs und weibliche Formen weg."""
    title = clean_job_title(job.title) or job.title
    description = clean_job_text(job.description) or job.description
    return JobDigest(title=title, description=description, contact_email=job.contact_address())


def local_keywords(job: Job, vocabulary: list[str]) -> list[str]:
    """Stichworte ohne KI: Portalangaben plus Treffer aus dem Verzeichnis."""
    found: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        clean = term.strip().strip(",;.")
        key = normalize(clean)
        if len(key) < 3 or key in seen or key in STOPWORDS:
            return
        seen.add(key)
        found.append(clean)

    for term in job.keywords:
        add(term)

    haystack = normalize(f"{job.title} {job.description}")
    for term in vocabulary:
        if has_term(haystack, term):
            add(term)

    for word in words(job.title):
        if len(word) > 4:
            add(word)
    return found


class AiClient:
    """OpenAI-kompatibler Chat-Client fuer Stichworte und Antwortauswertung."""

    def __init__(
        self,
        settings: Settings,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport or _post_json

    # ------------------------------------------------------------------
    def provider(self) -> str:
        """Anbieter der KI: openai (auch kompatibel) oder groq."""
        provider = self.settings.text("ai.provider", "openai").strip().lower()
        return provider if provider in {"openai", "groq"} else "openai"

    def base_url(self) -> str:
        stored = self.settings.text("ai.base_url").strip().rstrip("/")
        if stored:
            return stored
        return GROQ_BASE if self.provider() == "groq" else OPENAI_BASE

    def model(self) -> str:
        stored = self.settings.text("ai.model").strip()
        if stored:
            return stored
        return GROQ_MODEL if self.provider() == "groq" else OPENAI_MODEL

    def available(self) -> bool:
        return bool(
            self.settings.flag("ai.enabled")
            and self.base_url()
            and self.model()
            and self.settings.ai_key()
        )

    def _chat(self, system: str, user: str, temperature: float = 0.1) -> str:
        url = f"{self.base_url()}/chat/completions"
        payload = {
            "model": self.model(),
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.ai_key()}",
            "Content-Type": "application/json",
        }
        data = self.transport(
            url,
            payload,
            headers,
            float(self.settings.number("ai.timeout", 45) or 45),
        )
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Die KI lieferte keine Antwort.")
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")

    # ------------------------------------------------------------------
    def job_digest(self, job: Job) -> JobDigest:
        """Titel, Beschreibung und Empfaengeradresse aus der Anzeige lesen.

        Die KI entfernt Zusaetze ohne Bezug zur Stelle (Gendermarken wie
        ``(m/w/d)`` oder ``(gn*)``, Anbieter-IDs) und setzt Berufsbezeichnungen
        in die maennliche Form. Ohne KI erledigt das die lokale Aufbereitung.
        """
        local = local_digest(job)
        if not self.available():
            return local
        system = (
            "Du liest Stellenanzeigen aus. Antworte nur mit einem JSON-Objekt "
            'der Form {"titel": "...", "beschreibung": "...", '
            '"kontakt_email": "..."}. '
            "Der Titel ist die reine Berufsbezeichnung in der maennlichen Form, "
            "ohne (m/w/d), (gn*), (all genders) und ohne Nummern oder IDs des "
            "Anbieters. Die Beschreibung enthaelt nur Angaben zur Stelle "
            "(Aufgaben, Anforderungen, Pensum, Ort, Ansprechperson) - keine "
            "Gendermarken, keine Inserats- oder Referenznummern, keine "
            "Werbetexte. kontakt_email ist die Bewerbungsadresse oder leer."
        )
        content = (
            f"Titel: {job.title}\n"
            f"Firma: {job.company}\n"
            f"Ort: {job.city}\n"
            f"Bisherige Kontaktangaben: {job.contact_address() or '-'}\n\n"
            f"{strip_html(job.description)[:6000]}"
        )
        try:
            data = _json_object(self._chat(system, content, temperature=0.0))
            title = clean_job_title(str(data.get("titel") or "")) or local.title
            description = (
                clean_job_text(str(data.get("beschreibung") or "")) or local.description
            )
            address = str(data.get("kontakt_email") or "").strip()
            if "@" not in address:
                address = local.contact_email
            return JobDigest(title=title, description=description, contact_email=address)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Auslesen der Anzeige fehlgeschlagen (%s) - lokal weiter", exc)
            return local

    def write_application(
        self,
        template: Template,
        profile: dict[str, Any],
        job: Job,
        digest: JobDigest | None = None,
    ) -> tuple[str, str] | None:
        """Betreff und Mailtext von der KI schreiben lassen (None = Vorlage)."""
        if not self.available():
            return None
        digest = digest or local_digest(job)
        name = " ".join(
            part for part in (profile.get("vorname"), profile.get("nachname")) if part
        ).strip()
        system = (
            "Du schreibst Bewerbungsmails auf Deutsch. Antworte nur mit einem "
            'JSON-Objekt der Form {"betreff": "...", "text": "..."}. '
            "Der Betreff nennt die Stelle in der maennlichen Form und die Firma. "
            "Der Text ist eine formelle, persoenliche Mail (rund 150 bis 250 "
            "Woerter) mit Anrede, Bezug auf die Stelle, zwei bis drei Bezuegen "
            "zwischen Anforderungen und den Faehigkeiten des Bewerbers und einer "
            "hoeflichen Schlussformel. Erfinde keine Abschluesse, Zeugnisse oder "
            "Berufsjahre. Keine Gendermarken wie (m/w/d) oder (gn*), keine IDs, "
            "keine Platzhalter in geschweiften Klammern."
        )
        content = (
            f"Bewerber: {name or '-'}\n"
            f"Wohnort: {profile.get('wohnort') or '-'}\n"
            f"Erfahrung: {profile.get('erfahrung_jahre') or '-'}\n"
            f"Verfuegbar: {profile.get('verfuegbar') or '-'}\n"
            f"Faehigkeiten: {', '.join(self.settings.skills()) or '-'}\n"
            f"Interessen: {', '.join(self.settings.interests()) or '-'}\n\n"
            f"Stelle: {digest.title}\n"
            f"Firma: {job.company}\n"
            f"Ort: {job.city}\n"
            f"Pensum: {job.workload}\n"
            f"Beschreibung: {digest.description[:3000]}\n\n"
            f"Bisherige Vorlage als Stilvorgabe:\n"
            f"Betreff: {template.subject}\n{template.body[:2000]}"
        )
        try:
            data = _json_object(self._chat(system, content, temperature=0.4))
            subject = re.sub(r"\s+", " ", str(data.get("betreff") or "")).strip()
            body = str(data.get("text") or "").strip()
            if subject and len(body) >= 80 and "{" not in f"{subject}{body}":
                return subject, body
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Bewerbungstext fehlgeschlagen (%s) - Vorlage weiter", exc)
        return None

    def cover_letter(
        self,
        profile: dict[str, Any],
        job: Job,
        digest: JobDigest | None = None,
    ) -> str | None:
        """Anschreiben fuer den PDF-Anhang von der KI schreiben lassen."""
        if not self.available():
            return None
        digest = digest or local_digest(job)
        name = " ".join(
            part for part in (profile.get("vorname"), profile.get("nachname")) if part
        ).strip()
        system = (
            "Du schreibst ein Bewerbungsanschreiben auf Deutsch. Antworte nur "
            'mit einem JSON-Objekt der Form {"anschreiben": "..."}. '
            "Das Anschreiben beginnt mit der Anrede (ohne Adressblock), nennt "
            "die Stelle in der maennlichen Form, verbindet zwei bis drei "
            "Anforderungen mit den Faehigkeiten des Bewerbers und endet mit "
            "einer Schlussformel und dem Namen. Rund 250 bis 350 Woerter, "
            "sachlich und ohne Floskeln. Keine Gendermarken, keine IDs, keine "
            "Platzhalter, keine erfundenen Abschluesse."
        )
        content = (
            f"Bewerber: {name or '-'}\n"
            f"Wohnort: {profile.get('wohnort') or '-'}\n"
            f"Verfuegbar: {profile.get('verfuegbar') or '-'}\n"
            f"Faehigkeiten: {', '.join(self.settings.skills()) or '-'}\n"
            f"Interessen: {', '.join(self.settings.interests()) or '-'}\n\n"
            f"Stelle: {digest.title}\n"
            f"Firma: {job.company}\n"
            f"Beschreibung: {digest.description[:3000]}"
        )
        try:
            data = _json_object(self._chat(system, content, temperature=0.4))
            letter = str(
                data.get("anschreiben") or data.get("text") or ""
            ).strip()
            if len(letter) >= 120 and "{" not in letter:
                return letter
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Anschreiben fehlgeschlagen (%s) - Vorlage weiter", exc)
        return None

    # ------------------------------------------------------------------
    def keywords(self, job: Job, vocabulary: list[str]) -> list[str]:
        """Stichworte zur Stellenbeschreibung - mit Rueckfall auf lokal."""
        if not self.available():
            return local_keywords(job, vocabulary)
        system = (
            "Du ordnest Stellenanzeigen fuer Bewerbungen ein. Antworte nur mit "
            "einem JSON-Objekt der Form "
            '{"stichworte": ["..."], "berufsfeld": "...", "begruendung": "..."}. '
            "Die Stichworte sind kurze deutsche Begriffe aus der Anzeige "
            "(z. B. Spedition, Disposition, Lager, Sachbearbeitung, Kundendienst). "
            "Nenne 3 bis 8 Stichworte, keine ganzen Saetze. Interessen und "
            "Faehigkeiten des Bewerbers muessen nicht uebereinstimmen: Die "
            "Faehigkeiten zeigen, was er kann, die Interessen, wofuer er sich "
            "eher interessiert."
        )
        excerpt = (
            f"Titel: {job.title}\n"
            f"Firma: {job.company}\n"
            f"Ort: {job.city}\n"
            f"Pensum: {job.workload}\n"
            f"Stichworte des Portals: {job.keyword_text()}\n"
            f"Interessen des Bewerbers: {', '.join(self.settings.interests()) or '-'}\n"
            f"Faehigkeiten des Bewerbers: {', '.join(self.settings.skills()) or '-'}\n"
            f"Beschreibung: {strip_html(job.description)[:4000]}"
        )
        try:
            raw = self._chat(system, excerpt)
            data = _json_object(raw)
            terms = data.get("stichworte") or []
            if isinstance(terms, str):
                terms = [part.strip() for part in terms.split(",")]
            cleaned = [str(term).strip() for term in terms if str(term).strip()]
            if cleaned:
                return cleaned
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Stichworte fehlgeschlagen (%s) - lokal weiter", exc)
        return local_keywords(job, vocabulary)

    def classify(self, subject: str, body: str, sender: str = "") -> str:
        """Antwort als absage, zusage, einladung, info oder unbekannt einordnen."""
        if not self.available():
            return classify_local(subject, body)
        system = (
            "Du liest Antworten von Firmen auf Bewerbungen. Antworte nur mit "
            "einem JSON-Objekt der Form "
            '{"art": "absage|zusage|einladung|info|unbekannt"}. '
            "absage = Bewerbung abgelehnt, zusage = Stelle angeboten, "
            "einladung = Gespraech oder Termin gewuenscht, info = sonstiges."
        )
        content = (
            f"Absender: {sender}\nBetreff: {subject}\n\n{strip_html(body)[:4000]}"
        )
        try:
            raw = self._chat(system, content, temperature=0.0)
            data = _json_object(raw)
            kind = normalize(str(data.get("art") or ""))
            if kind in {ABSAGE, ZUSAGE, EINLADUNG, INFO}:
                return kind
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Antwortauswertung fehlgeschlagen (%s) - lokal weiter", exc)
        return classify_local(subject, body)


def _json_object(raw: str) -> dict[str, Any]:
    """JSON aus einer Antwort schneiden - auch aus Code-Zaeunen."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("Keine JSON-Antwort")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON ist kein Objekt")
    return data


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
