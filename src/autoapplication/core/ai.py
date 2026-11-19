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

from .. import APP_VERSION
from .config import Settings
from .models import Job
from .templates import Template
from .text import (
    clean_job_text,
    clean_job_title,
    contact_person,
    domain_of,
    emails,
    has_term,
    normalize,
    person_name,
    strip_html,
    words,
)

log = logging.getLogger(__name__)

# Ohne eigenen Programm-Namen weist Cloudflare (vor Groq) die Anfrage mit
# 403 ab - die KI waere dann nicht erreichbar, obwohl der Schluessel stimmt.
USER_AGENT = f"AutoApplication/{APP_VERSION}"

OPENAI_BASE = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"
GROQ_BASE = "https://api.groq.com/openai/v1"
GROQ_MODEL = "openai/gpt-oss-120b"

# Nicht als Sprachmodell fuer Stichworte und Texte geeignet.
_MODEL_SKIP = (
    "embed",
    "whisper",
    "tts",
    "dall-e",
    "moderation",
    "transcrib",
    "realtime",
    "audio",
    "image",
    "rerank",
    "guard",
    "safety",
)

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

# Feste Stellenzusage: Vertrag, Einstellung, Stellenangebot.
FESTE_ZUSAGE_PHRASES = (
    "arbeitsvertrag",
    "vertragsentwurf",
    "vertragsunterlagen",
    "vertrag zugesandt",
    "stellen wir sie ein",
    "wir moechten sie einstellen",
    "wir möchten sie einstellen",
    "willkommen im team",
    "herzlichen glueckwunsch",
    "herzlichen glückwunsch",
    "wir freuen uns, ihnen mitzuteilen",
    "ihnen eine stelle anbieten",
    "bieten wir ihnen eine stelle",
    "feste zusage",
    "verbindliche zusage",
    "einstellung zugesagt",
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
    "zusage zum gespraech",
    "termin am",
    "termin um",
    "termin bestaetigen",
    "termin bestätigen",
    "bestaetigen sie den termin",
    "bestaetigen sie bitte den termin",
    "gespraech am",
    "gespraech um",
    "zusage zum vorstellungsgespraech",
    "zu einem kennenlernen",
    "einladen wir sie",
    "wir laden sie ein",
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
    fest = _score_phrases(haystack, FESTE_ZUSAGE_PHRASES)
    zusage = _score_phrases(haystack, ZUSAGE_PHRASES)
    einladung = _score_phrases(haystack, EINLADUNG_PHRASES)

    # Eine Einladung kann harmlos "leider erst jetzt" enthalten - die Absage
    # braucht deshalb mindestens zwei Formulierungen oder ein klares Wort.
    if absage >= 2 or "absage" in haystack or "abgelehnt" in haystack:
        return ABSAGE
    # Ein Terminwunsch bleibt eine Einladung, auch wenn das Wort "Zusage"
    # faellt ("Danke fuer Ihre Zusage zum Gespraech"). Erst Vertrag oder
    # feste Einstellung machen daraus eine Zusage.
    if fest >= 1:
        return ZUSAGE
    if einladung >= 1:
        return EINLADUNG
    if zusage >= 1:
        return ZUSAGE
    return INFO


@dataclass
class JobDigest:
    """Ausgelesene Anzeige: sauberer Titel, Beschreibung und Kontaktadresse."""

    title: str
    description: str
    contact_email: str = ""
    contact_name: str = ""


def local_digest(job: Job) -> JobDigest:
    """Anzeige ohne KI aufbereiten: Gendermarken, IDs und weibliche Formen weg."""
    title = clean_job_title(job.title) or job.title
    description = clean_job_text(job.description) or job.description
    contact = (
        job.contact_name
        or contact_person(job.description)
        or contact_person(description)
    )
    return JobDigest(
        title=title,
        description=description,
        contact_email=job.contact_address(),
        contact_name=contact,
    )


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
        lister: Callable[..., Any] | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport or _post_json
        self.lister = lister or _get_json

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

    def models(self) -> list[str]:
        """Modelle, die der Anbieter mit diesem Schluessel anbietet.

        Gefragt wird die OpenAI-kompatible Modellliste (``GET /models``). Sie
        zeigt, welche Sprachmodelle das Konto wirklich nutzen kann - ein
        eingetragenes Modell, das dort fehlt, laesst sich nicht verwenden.
        Einbettungs-, Bild- und Sprachmodelle bleiben aussen vor; das zuletzt
        eingestellte Modell steht oben, danach folgt die alphabetische Liste.
        """
        url = f"{self.base_url()}/models"
        headers = {
            "Authorization": f"Bearer {self.settings.ai_key()}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        timeout = min(float(self.settings.number("ai.timeout", 45) or 45), 30)
        try:
            data = self.lister(url, headers, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                raise ValueError(
                    "Der Schluessel wurde abgelehnt (401). Bitte den Schluessel "
                    "des Anbieters pruefen."
                ) from exc
            if exc.code == 403:
                detail = _http_detail(exc)
                raise ValueError(
                    "Der Anbieter hat die Anfrage abgewiesen (403). Haeufige "
                    "Ursachen: dem Schluessel fehlen die Rechte, im Konto sind "
                    "Modelle gesperrt, oder ein Filter dazwischen (Firmennetz, "
                    "VPN, Cloudflare) blockt die Anfrage"
                    + (f". Antwort: {detail}" if detail else ".")
                ) from exc
            if exc.code == 404:
                raise ValueError(
                    f"Unter {url} gibt es keine Modellliste (404). Bitte die "
                    "Adresse der Schnittstelle pruefen."
                ) from exc
            raise
        entries = data.get("data") if isinstance(data, dict) else data
        found: list[str] = []
        for entry in entries or []:
            if isinstance(entry, dict):
                name = str(entry.get("id") or "").strip()
            else:
                name = str(entry or "").strip()
            if not name or name.lower() in {item.lower() for item in found}:
                continue
            lowered = name.lower()
            if any(skip in lowered for skip in _MODEL_SKIP):
                continue
            found.append(name)
        if not found:
            return []
        current = self.model()
        ordered = sorted(found)
        if current in ordered:
            ordered.remove(current)
            ordered.insert(0, current)
        return ordered

    def probe_model(self) -> str:
        """Das eingestellte Modell wirklich anfragen - der sicherste Test.

        Die Modellliste allein sagt nicht, ob eine Anfrage durchgeht (Rechte,
        abgeschaltetes Modell, Filter dazwischen). Hier geht eine winzige
        Anfrage an genau dieses Modell.
        """
        try:
            return self._chat(
                "Antworte nur mit dem Wort ok.", "Verbindungstest.", 0.0
            ).strip()
        except urllib.error.HTTPError as exc:
            detail = _http_detail(exc)
            suffix = f" Antwort: {detail}" if detail else ""
            if exc.code == 401:
                raise ValueError(
                    "Der Schluessel wurde abgelehnt (401). Bitte den Schluessel "
                    "des Anbieters pruefen."
                ) from exc
            if exc.code == 403:
                raise ValueError(
                    "Der Anbieter hat die Anfrage abgewiesen (403). Haeufige "
                    "Ursachen: dem Schluessel fehlen die Rechte, im Konto sind "
                    "Modelle gesperrt, oder ein Filter dazwischen (Firmennetz, "
                    f"VPN, Cloudflare) blockt die Anfrage.{suffix}"
                ) from exc
            if exc.code == 404:
                raise ValueError(
                    f"Das Modell «{self.model()}» gibt es bei diesem Anbieter "
                    f"nicht oder der Schluessel hat keinen Zugriff (404).{suffix}"
                ) from exc
            raise ValueError(
                f"Der Anbieter antwortet mit einem Fehler ({exc.code}).{suffix}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ValueError(f"Keine Verbindung zum Anbieter: {exc}") from exc

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
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        timeout = float(self.settings.number("ai.timeout", 45) or 45)
        try:
            data = self.transport(url, payload, headers, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code != 400:
                raise
            # Neuere Modelle mit festem Reasoning lehnen temperature ab.
            # Ohne diese Angabe geht derselbe Aufruf durch.
            without = {key: value for key, value in payload.items() if key != "temperature"}
            data = self.transport(url, without, headers, timeout)
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("Die KI lieferte keine Antwort.")
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")

    def synonyms(self, terms: list[str], kind: str = "Interessen") -> list[str]:
        """Verwandte Begriffe zu einer Stichwortliste vorschlagen.

        Gedacht fuer den Knopf neben «Interessen» und «Faehigkeiten»: Die KI
        ergaenzt Begriffe, die in Stellenanzeigen dasselbe meinen (etwa
        «Lager» -> «Kommissionierung», «Warenannahme»). Zurueck kommen nur
        neue, kurze Stichworte ohne Wiederholungen; die vorhandene Liste
        bleibt unveraendert. Ohne eingerichtete KI bleibt das Ergebnis leer.
        """
        clean: list[str] = []
        for term in terms:
            value = re.sub(r"\s+", " ", str(term or "")).strip(" .,;:–-")
            if value and value.casefold() not in {item.casefold() for item in clean}:
                clean.append(value)
        if not clean or not self.available():
            return []
        system = (
            "Du erweiterst eine Stichwortliste fuer die Stellensuche um verwandte "
            "Begriffe. Antworte nur mit einem JSON-Objekt der Form "
            '{"synonyme": ["...", "..."]}. Nimm je Stichwort drei bis fuenf '
            "deutsche Begriffe auf, die in Stellenanzeigen dieselbe Taetigkeit "
            "oder dasselbe Thema bezeichnen (etwa Lager -> Kommissionierung, "
            "Warenannahme; IT -> Helpdesk, Anwenderbetreuung). Nur Substantive "
            "oder kurze Wendungen, keine Saetze, keine Erklaerungen, keine "
            "Firmen- oder Personennamen. Nichts erfinden, was eine Ausbildung, "
            "ein Zertifikat oder Berufserfahrung behauptet. Keine Wiederholung "
            "der bereits genannten Stichworte."
        )
        content = f"Liste: {kind}\nStichworte: {', '.join(clean)}"
        try:
            data = _json_object(self._chat(system, content, temperature=0.3))
        except urllib.error.HTTPError as exc:
            detail = _http_detail(exc)
            suffix = f" Antwort: {detail}" if detail else ""
            raise ValueError(
                f"Der Anbieter antwortet mit einem Fehler ({exc.code}).{suffix}"
            ) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ValueError(f"Keine Verbindung zum Anbieter: {exc}") from exc
        except ValueError as exc:
            raise ValueError(
                "Die KI antwortete nicht wie erwartet - bitte nochmals versuchen."
            ) from exc
        values = data.get("synonyme") or data.get("synonyms") or []
        # Manche Modelle liefern die Liste als einen Satz mit Kommas statt als
        # JSON-Liste. Auch das wird uebernommen, statt die Antwort zu verwerfen.
        if isinstance(values, str):
            values = re.split(r"[,;\n]", values)
        if not isinstance(values, list):
            return []
        known = {item.casefold() for item in clean}
        result: list[str] = []
        for raw in values:
            # Mehrere Begriffe in einem Eintrag ("Kommissionierung, Versand")
            # werden einzeln uebernommen, statt den ganzen Eintrag zu verwerfen.
            for part in re.split(r"[,;\n]", str(raw or "")):
                value = re.sub(r"\s+", " ", part).strip(" .,;:–-•\"'")
                if not value or len(value) > 60 or len(value.split()) > 5:
                    continue
                key = value.casefold()
                if key in known:
                    continue
                known.add(key)
                result.append(value)
        return result[:30]

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
            '"kontakt_email": "...", "ansprechperson": "..."}. '
            "ansprechperson ist die Ansprechperson der Anzeige mit Anrede, also "
            "\"Herr Müller\" oder \"Frau Meier\" (nur der Nachname). Steht "
            "dort nur ein Name ohne Herr/Frau, leiten Sie die Anrede aus dem "
            "Vornamen ab, wenn er eindeutig männlich oder weiblich ist (Sandra "
            "-> Frau, Michael -> Herr). Bei unklaren, mehrdeutigen oder "
            "fehlenden Vornamen bleibt ansprechperson leer - raten Sie dort nie. "
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
            person = contact_person(str(data.get("ansprechperson") or ""))
            return JobDigest(
                title=title,
                description=description,
                contact_email=address,
                contact_name=person or local.contact_name,
            )
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Auslesen der Anzeige fehlgeschlagen (%s) - lokal weiter", exc)
            return local

    def contact_from_page(
        self, text: str, portal: str = "", company: str = ""
    ) -> tuple[str, str]:
        """Ansprechperson und E-Mail aus einem Seitentext lesen.

        Ergänzt die lokale Auslese, wenn Text unübersichtlich ist: Die KI
        übernimmt ausschliesslich, was im vorliegenden Text ausdrücklich steht,
        und liefert sonst leere Angaben. Die Adresse wird gegen die
        Portaldomain und technische Kennungen geprüft; ohne eingerichtete KI
        bleibt das Ergebnis leer.
        """
        if not self.available() or not (text or "").strip():
            return "", ""
        system = (
            "Du liest aus dem Text einer Stellenanzeige die Ansprechperson und "
            "die Bewerbungsadresse heraus. Antworte nur mit einem JSON-Objekt "
            'der Form {"ansprechperson": "...", "email": "..."}. '
            "Übernimm ausschliesslich, was im Text ausdrücklich steht - "
            "erfinde weder Namen noch Adressen. Steht die Ansprechperson mit "
            "Anrede da (Herr/Frau), übernimm die Anrede und den Nachnamen; "
            "steht dort nur ein Name, übernimm ihn wie geschrieben. Ist die "
            "Person unklar oder nicht genannt, bleibt ansprechperson leer. "
            "email ist die Bewerbungsadresse aus dem Text, Zeichen für Zeichen "
            "übernommen; die Adresse des Portals selbst und technische "
            "Kennungen zählen nicht, dann bleibt email leer. Nenne keine "
            "Telefonnummern und keine Postadressen."
        )
        content = (
            f"Portaldomain: {portal or '-'}\n"
            f"Firmendomain: {company or '-'}\n\n"
            f"Seitentext:\n{_contact_excerpt(text)}"
        )
        try:
            data = _json_object(self._chat(system, content, temperature=0.0))
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            log.info("KI-Kontaktsuche fehlgeschlagen (%s) - lokal weiter", exc)
            return "", ""
        address = _checked_email(str(data.get("email") or ""), portal)
        person = person_name(str(data.get("ansprechperson") or ""))
        return address, person

    # Firmenadressen liest bewusst keine KI: sie kämen aus dem Modellgedächtnis
    # und könnten erfunden sein. Adressen stammen nur aus Portalangaben oder
    # klar aus dem Seitentext gelesenen Zeilen (siehe Pipeline).

    def proofread(self, text: str) -> str:
        """Rechtschreibung und Grammatik korrigieren, Inhalt unverändert.

        Ohne eingerichtete KI kommt der Text unverändert zurück.
        """
        value = (text or "").strip()
        if not value or not self.available():
            return text
        system = (
            "Du korrigierst deutsche Texte: Rechtschreibung, Grammatik und "
            "Zeichensetzung. Inhalt, Anrede, Namen, Zahlen und der Aufbau mit "
            "Zeilenumbrüchen bleiben unverändert. Antworte nur mit dem "
            "korrigierten Text, ohne Kommentar und ohne Anführungszeichen."
        )
        corrected = self._chat(system, value, temperature=0.0).strip()
        return corrected or text

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
            "Die Anrede lautet \"Sehr geehrter Herr <Nachname>\" oder \"Sehr "
            "geehrte Frau <Nachname>\", wenn eine Ansprechperson genannt ist, "
            "sonst \"Sehr geehrte Damen und Herren\". "
            "Der Text ist eine formelle, persoenliche Mail (rund 150 bis 250 "
            "Woerter) mit Anrede, Bezug auf die Stelle, zwei bis drei Bezuegen "
            "zwischen Anforderungen und den Faehigkeiten des Bewerbers und einer "
            "hoeflichen Schlussformel. Erfinde keine Abschluesse, Zeugnisse oder "
            "Berufsjahre. Keine Gendermarken wie (m/w/d) oder (gn*), keine IDs, "
            "keine Platzhalter in geschweiften Klammern."
            "\n\nFirmen und Zeitraeume stammen ausschliesslich aus dem Werdegang "
            "des Bewerbers unten. Nenne nur Stationen, die dort stehen, "
            "uebernimm Schreibweise und Jahre unveraendert und erfinde keine "
            "Firma, keinen Zeitraum und keine Aufgabe."
        )
        content = (
            f"Bewerber: {name or '-'}\n"
            f"Wohnort: {profile.get('wohnort') or '-'}\n"
            f"Erfahrung gesamt: {profile.get('erfahrung_jahre') or '-'}\n"
            f"Erfahrung in Spedition und Export: "
            f"{profile.get('erfahrung_spedition') or '-'}\n"
            f"Verfuegbar: {profile.get('verfuegbar') or '-'}\n"
            f"Faehigkeiten: {', '.join(self.settings.skills()) or '-'}\n"
            f"Interessen: {', '.join(self.settings.interests()) or '-'}\n"
            f"Werdegang (Stationen mit Zeitraum und Aufgabe):\n"
            f"{profile.get('werdegang') or '-'}\n\n"
            f"Stelle: {digest.title}\n"
            f"Firma: {job.company}\n"
            f"Ort: {job.city}\n"
            f"Pensum: {job.workload}\n"
            f"Ansprechperson: {digest.contact_name or '-'}\n"
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
            "Das Anschreiben beginnt mit der Anrede (ohne Adressblock): "
            "\"Sehr geehrter Herr <Nachname>\" oder \"Sehr geehrte Frau "
            "<Nachname>\", wenn eine Ansprechperson genannt ist, sonst "
            "\"Sehr geehrte Damen und Herren\". Danach nennt es "
            "die Stelle in der maennlichen Form, verbindet zwei bis drei "
            "Anforderungen mit den Faehigkeiten des Bewerbers und endet mit "
            "einer Schlussformel und dem Namen. Rund 250 bis 350 Woerter, "
            "sachlich und ohne Floskeln. Keine Gendermarken, keine IDs, keine "
            "Platzhalter, keine erfundenen Abschluesse. Firmen und Zeitraeume "
            "stammen ausschliesslich aus dem Werdegang des Bewerbers unten; "
            "erfinde keine Station, keinen Zeitraum und keine Aufgabe."
        )
        content = (
            f"Bewerber: {name or '-'}\n"
            f"Wohnort: {profile.get('wohnort') or '-'}\n"
            f"Verfuegbar: {profile.get('verfuegbar') or '-'}\n"
            f"Faehigkeiten: {', '.join(self.settings.skills()) or '-'}\n"
            f"Interessen: {', '.join(self.settings.interests()) or '-'}\n"
            f"Werdegang (Stationen mit Zeitraum und Aufgabe):\n"
            f"{profile.get('werdegang') or '-'}\n\n"
            f"Stelle: {digest.title}\n"
            f"Firma: {job.company}\n"
            f"Ansprechperson: {digest.contact_name or '-'}\n"
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

    def classify(
        self,
        subject: str,
        body: str,
        sender: str = "",
        context: str = "",
    ) -> str:
        """Antwort als absage, zusage, einladung, info oder unbekannt einordnen."""
        if not self.available():
            return classify_local(subject, body)
        system = (
            "Du liest die Antwort einer Firma auf eine Bewerbung und ordnest "
            "sie ein. Antworte nur mit einem JSON-Objekt der Form "
            '{"art": "absage|zusage|einladung|info|unbekannt"}. '
            "zusage = die Stelle ist verbindlich zugesagt: Arbeitsvertrag oder "
            "Vertragsentwurf, feste Einstellungszusage, mit Stellenantritt, "
            "Pensum oder Lohn. "
            "einladung = Einladung zu einem Vorstellungsgespraech, Kennenlernen, "
            "Interview, Telefonat oder Assessment, oder die Bitte, einen Termin "
            "zu vereinbaren. "
            "absage = die Bewerbung wird abgelehnt. "
            "info = alles andere, etwa Eingangsbestaetigung, Rueckfrage oder "
            "Zwischenstand ohne Termin und ohne Entscheid. "
            "Wichtig: Ein Gespraechstermin ist immer eine einladung, auch wenn "
            "die Mail das Wort Zusage enthaelt (\"Zusage zum "
            "Vorstellungsgespraech\") oder sich sehr freundlich ueber die "
            "Bewerbung aeussert. Eine zusage nur dann, wenn die Anstellung "
            "selbst zugesagt ist, nicht bloss ein Termin oder ein Kennenlernen. "
            "Wenn Merkmale beider Arten vorkommen, entscheide nach dem, was die "
            "Mail tatsaechlich verlangt: Termin vereinbaren = einladung, "
            "Vertrag unterschreiben = zusage."
        )
        content = (
            f"Absender: {sender or '-'}\n"
            f"Betreff: {subject or '-'}\n"
            f"Bezug: {context or '-'}\n\n"
            f"Antwort der Firma:\n{strip_html(body)[:6000]}"
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


_HEX_LOCAL_RE = re.compile(r"[0-9a-f]{16,}")
_CONTACT_WORDS = (
    "ansprechperson",
    "ansprechpartner",
    "kontakt",
    "bewerbung",
    "e-mail",
    "email",
)


def _contact_excerpt(value: str, limit: int = 8000) -> str:
    """Seitentext für die KI kürzen, aber die Kontaktstelle behalten.

    Lange Portalseiten (ähnliche Jobs, Navigation) würden den Kontaktblock sonst
    aus dem Fenster drängen. Der Anfang und je ein Stück um die typischen
    Kontaktwörter kommen mit.
    """
    text = strip_html(value)
    if len(text) <= limit:
        return text
    lowered = text.lower()
    pieces: list[str] = [text[:3000]]
    for word in _CONTACT_WORDS:
        start = lowered.find(word)
        if start == -1:
            continue
        piece = text[max(0, start - 500) : start + 1500]
        if piece not in pieces:
            pieces.append(piece)
    return "\n...\n".join(pieces)[:limit]


def _checked_email(value: str, portal: str = "") -> str:
    """Adresse prüfen: echte Adresse, nicht die des Portals."""
    for candidate in emails(value):
        domain = domain_of(candidate)
        if not domain or (portal and domain == portal):
            continue
        if _HEX_LOCAL_RE.fullmatch(candidate.split("@", 1)[0].lower()):
            # Technische Kennung statt Kontaktadresse.
            continue
        return candidate
    return ""


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


def _http_detail(exc: urllib.error.HTTPError) -> str:
    """Antworttext einer Fehlermeldung lesen - kurz und ohne Zeilenumbrueche."""
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - die Meldung darf daran nicht scheitern
        return ""
    text = re.sub(r"\s+", " ", raw).strip()
    return text[:300]


def _json_headers(headers: dict[str, str]) -> dict[str, str]:
    """Kopfzeilen ergaenzen, die Cloudflare sonst mit 403 quittiert."""
    result = dict(headers)
    result.setdefault("Accept", "application/json")
    result.setdefault("User-Agent", USER_AGENT)
    return result


def _get_json(
    url: str, headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers=_json_headers(headers), method="GET"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, headers=_json_headers(headers), method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))
