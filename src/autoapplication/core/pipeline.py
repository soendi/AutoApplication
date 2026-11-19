"""Der Tageslauf von AutoApplication.

1. Neue Stellen von ostjob.ch holen und Stichworte bestimmen.
2. Passende Vorlage waehlen und eine Bewerbung als Mail-Entwurf ablegen.
3. Gesendete Entwuerfe und Antworten im Posteingang verfolgen.
4. Nach zwei Wochen ohne Antwort eine Nachfrage vorbereiten.
"""

from __future__ import annotations

import logging
import re
import urllib.request
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import embed, ocr, pdf
from .ai import (
    ABSAGE,
    EINLADUNG,
    INFO,
    ZUSAGE,
    AiClient,
    JobDigest,
    classify_local,
    local_digest,
)
from .config import Settings, templates_path, token_path
from .documents import collect, missing_address_placeholders, write_cover_letter
from .imap_mail import GmailImapClient, ImapError
from .models import Job
from .ostjob import OstjobClient, OstjobError, search_jobs
from .outlook import GraphAuth, OutlookClient, OutlookError, message_body, sender_address
from .store import Store
from .templates import (
    Template,
    choose_template,
    follow_up_template,
    load_templates,
    render_mail,
    vocabulary,
)
from .text import (
    contact_name,
    contact_person,
    days_until,
    domain_of,
    emails,
    format_date,
    format_datetime,
    normalize,
    now_iso,
    parse_date,
    salutation,
    short,
    strip_html,
)
from .tracking import find_code, new_code

log = logging.getLogger(__name__)

STATUS_ENTWURF = "entwurf"
STATUS_GESENDET = "gesendet"
STATUS_ANTWORT = INFO  # Antwort ohne Absage, Zusage oder Einladung

# Frisch angelegte Entwuerfe erst spaeter pruefen: ein noch nicht indexierter
# Entwurf soll nicht faelschlich als gesendet gelten.
DRAFT_GRACE_MINUTES = 10
# So viele Mails aus dem Ordner «Gesendet» liest die Versandpruefung.
SENT_LOOKBACK = 100
# Obergrenze fuer den Anzeigentext: die Seite wird nur nachgelesen, wenn der
# Kontakt fehlt.
PAGE_BYTES = 1_000_000
# Technische Kennungen wie Sentry-IDs sehen wie Adressen aus.
_HEX_LOCAL_RE = re.compile(r"[0-9a-f]{16,}")
# Firmenadresse: Schweizer Postleitzahl mit Ort und Strasse mit Hausnummer.
_ZIP_CITY_RE = re.compile(r"\b([1-9]\d{3})\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\- ]{1,40})")
_STREET_RE = re.compile(
    r"\b([A-ZÄÖÜ][A-Za-zÄÖÜäöüß.\- ]{1,40}?"
    r"(?:strasse|str\.|weg|platz|gasse|allee|ring|hof|rain)\s*\d+\s*[a-zA-Z]?)\b"
)
STATUS_ABSAGE = "absage"
STATUS_ZUSAGE = "zusage"
STATUS_EINLADUNG = "einladung"
STATUS_NACHGEFASST = "nachgefasst"
STATUS_ARCHIVIERT = "archiviert"


@dataclass
class RunSummary:
    """Ergebnis eines Suchlaufs."""

    found: int = 0
    new: int = 0
    matched: int = 0
    drafts: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        parts = [
            f"{self.found} Stellen geprüft",
            f"{self.new} neu",
            f"{self.matched} passend",
        ]
        if self.skipped:
            parts.append(f"{self.skipped} ohne Passung")
        text = ", ".join(parts)
        if self.errors:
            text += " – " + "; ".join(self.errors[:3])
        return text


def fetch_page(url: str) -> str:
    """HTML einer Anzeigenseite holen; Fehler ergeben leeren Text."""
    target = (url or "").strip()
    if not target.lower().startswith(("http://", "https://")):
        return ""
    request = urllib.request.Request(target, headers=ocr.HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=ocr.TIMEOUT) as response:
            return response.read(PAGE_BYTES).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - Seite ist nur ein Zusatz
        log.info("Anzeigetext konnte nicht geladen werden (%s): %s", target, exc)
        return ""


def _recent(value: str, minutes: int = DRAFT_GRACE_MINUTES) -> bool:
    """Liegt der Zeitpunkt weniger als ``minutes`` Minuten zurueck?"""
    text = (value or "").strip()
    if not text:
        return False
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment > datetime.now(timezone.utc) - timedelta(minutes=minutes)


def _moment(value: str) -> datetime | None:
    """ISO-Zeitstempel lesen, auch mit ``Z`` am Ende."""
    text = (value or "").strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


class Pipeline:
    """Verbindet Stellenquelle, KI, Vorlagen, Ablage und Outlook."""

    def __init__(
        self,
        settings: Settings,
        store: Store,
        *,
        ai_client: AiClient | None = None,
        outlook_client: OutlookClient | None = None,
        imap_client: GmailImapClient | None = None,
        ostjob_client: OstjobClient | None = None,
        notifier: Callable[[str, str], None] | None = None,
        templates_file: Path | None = None,
        page_fetcher: Callable[[str], str] | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self._ai = ai_client or AiClient(settings)
        self._outlook = outlook_client
        self._imap = imap_client
        self._ostjob = ostjob_client
        self.notifier = notifier
        self.templates_file = templates_file or templates_path()
        # Anzeigenseite nachlesen; im Test durch eine Attrappe ersetzbar.
        self._page_fetcher = page_fetcher or fetch_page
        # Einmal geholte Anzeigenseiten nicht erneut laden.
        self._page_texts: dict[str, str] = {}
        # Firmenadressen je Domain nur einmal im Netz suchen.
        self._address_cache: dict[str, tuple[str, str]] = {}
        # Text der PDF-Beilaen je Anzeige (viele Portale haengen eine an).
        self._pdf_texts: dict[str, str] = {}
        # Inhalt eingebetteter Rahmen (dort steht oft die ganze Ausschreibung).
        self._frame_texts: dict[str, str] = {}
        # Zuletzt zusammengestellte Bewerbung je Stelle (fuer die Vorschau).
        self._previews: dict[str, dict[str, Any]] = {}
        # Dasselbe fuer Nachfragen, damit die Vorlage nicht doppelt laeuft.
        self._follow_up_previews: dict[int, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Vorlagen und Verbindungen
    # ------------------------------------------------------------------
    def templates(self) -> list[Template]:
        return load_templates(self.templates_file)

    def save_templates(self, templates: list[Template]) -> None:
        from .templates import save_templates

        save_templates(self.templates_file, templates)

    def auth(self) -> GraphAuth:
        return GraphAuth(
            self.settings.text("outlook.client_id"),
            tenant=self.settings.text("outlook.tenant", "common") or "common",
            token_file=token_path(),
        )

    def mail_provider(self) -> str:
        return self.settings.mail_provider()

    def outlook_ready(self) -> bool:
        """Ist die gewaehlte E-Mail-Anbindung bereit fuer Entwuerfe?"""
        return self.mail_ready()

    def mail_ready(self) -> bool:
        if self._outlook is not None or self._imap is not None:
            return True
        provider = self.mail_provider()
        if provider == "imap":
            return bool(
                self.settings.text("imap.email").strip()
                and self.settings.text("imap.password")
            )
        if provider != "outlook":
            return False
        if not self.settings.flag("outlook.enabled"):
            return False
        if not self.settings.text("outlook.client_id").strip():
            return False
        try:
            return self.auth().connected()
        except OutlookError:
            return False

    def outlook(self) -> OutlookClient:
        """Client der gewaehlten E-Mail-Anbindung."""
        return self.mail()

    def mail(self) -> OutlookClient | GmailImapClient:
        if self._imap is not None and self.mail_provider() == "imap":
            return self._imap
        if self._outlook is not None:
            return self._outlook
        if self.mail_provider() == "imap":
            return GmailImapClient(
                self.settings.text("imap.email"),
                self.settings.text("imap.password"),
            )
        return OutlookClient(self.auth())

    def notify(self, title: str, message: str) -> None:
        self.store.log("hinweis", f"{title}: {message}")
        if self.notifier is not None:
            try:
                self.notifier(title, message)
            except Exception as exc:  # noqa: BLE001 - Hinweis darf nichts stoppen
                log.warning("Hinweis konnte nicht angezeigt werden: %s", exc)

    # ------------------------------------------------------------------
    # KI-Aufbereitung von Anzeige und Texten
    # ------------------------------------------------------------------
    def _digest(self, job: Job) -> JobDigest:
        """Anzeige auslesen - per KI, sonst lokal bereinigt."""
        digest = local_digest(job)
        method = getattr(self._ai, "job_digest", None)
        if callable(method):
            try:
                found = method(job)
                if isinstance(found, JobDigest):
                    digest = found
            except Exception as exc:  # noqa: BLE001 - lokaler Rueckfall
                log.warning("Anzeige konnte nicht gelesen werden: %s", exc)
        return self._with_image_contact(job, digest)

    def _with_image_contact(self, job: Job, digest: JobDigest) -> JobDigest:
        """Fehlenden Kontakt aus Anzeigetext, Seite und Bildern lesen."""
        # Was die Anzeige schon mitgibt, gilt vor jedem Nachladen.
        digest.contact_email = digest.contact_email or job.contact_email
        digest.contact_name = digest.contact_name or job.contact_name
        if digest.contact_email and digest.contact_name:
            return digest
        address, person = self._find_contact(job)
        if not digest.contact_email and address:
            digest.contact_email = address
        if not digest.contact_name and person:
            digest.contact_name = person
        return digest

    @staticmethod
    def _contact_domains(job: Job) -> tuple[str, str]:
        """Portaldomain der Anzeige und Domain des Arbeitgebers."""
        portal = domain_of(job.url or job.apply_url)
        raw = job.raw if isinstance(job.raw, dict) else {}
        company = raw.get("company")
        homepage = str(company.get("homepage") or "") if isinstance(company, dict) else ""
        return portal, domain_of(homepage)

    @staticmethod
    def _contact_from_text(
        value: str, portal: str = "", company: str = ""
    ) -> tuple[str, str]:
        """Adresse und Ansprechperson aus einem Textstueck lesen."""
        text = strip_html(value or "")
        # Maskierte Umbrueche aus Skripten kleben sonst an der Adresse.
        text = text.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
        if not text.strip():
            return "", ""
        candidates: list[str] = []
        for address in emails(text):
            domain = domain_of(address)
            if not domain or (portal and domain == portal):
                continue
            if _HEX_LOCAL_RE.fullmatch(address.split("@", 1)[0].lower()):
                # Technische Kennung statt Kontaktadresse.
                continue
            candidates.append(address)
        address = ""
        if candidates:
            preferred = [item for item in candidates if company and domain_of(item) == company]
            address = (preferred or candidates)[0]
        return address, contact_person(text) or contact_name(text)

    def _text_contact(self, job: Job) -> tuple[str, str]:
        """Ansprechperson und Adresse aus dem Fliesstext der Anzeige lesen."""
        raw = job.raw if isinstance(job.raw, dict) else {}
        parts = [job.description or ""]
        for key in ("description", "beschreibung", "contact", "kontakt"):
            value = raw.get(key)
            if isinstance(value, str):
                parts.append(value)
        return self._contact_from_text(" ".join(parts), *self._contact_domains(job))

    def _page_text(self, job: Job) -> str:
        """Text der Anzeigenseite - einmal je Adresse geholt."""
        url = job.url or job.apply_url
        if not url:
            return ""
        if url not in self._page_texts:
            self._page_texts[url] = self._page_fetcher(url)
        return self._page_texts[url]

    def _frame_text(self, job: Job) -> str:
        """HTML der eingebetteten Rahmen einer Anzeige - einmal geholt.

        Viele Portale zeigen die Ausschreibung in einem iframe (z. B. bei
        umantis). Dort stehen Ansprechperson und E-Mail; die Portalseite
        selbst nennt oft nur das Portal.
        """
        key = job.url or job.apply_url or job.id
        cached = self._frame_texts.get(key)
        if cached is not None:
            return cached
        raw = job.raw if isinstance(job.raw, dict) else {}
        sources = [self._page_text(job)]
        sources.extend(value for value in raw.values() if isinstance(value, str))
        base = job.url or job.apply_url
        text = ""
        for source in sources:
            if not source:
                continue
            for url in embed.frame_urls(source, base):
                page = self._page_text_for(url)
                if page:
                    text = "\n".join(part for part in (text, page) if part)
        self._frame_texts[key] = text
        return text

    def _pdf_text(self, job: Job) -> str:
        """Text der PDF-Beilaen einer Anzeige - einmal je Anzeige geholt.

        Viele Portale verlinken die Ausschreibung als PDF; dort stehen
        Ansprechperson, E-Mail und Adresse oft im Klartext, waehrend die
        Anzeigenseite selbst nur den Link zeigt.
        """
        key = job.url or job.apply_url or job.id
        cached = self._pdf_texts.get(key)
        if cached is not None:
            return cached
        raw = job.raw if isinstance(job.raw, dict) else {}
        sources = [self._page_text(job), self._frame_text(job)]
        sources.extend(value for value in raw.values() if isinstance(value, str))
        base = job.url or job.apply_url
        text = ""
        for source in sources:
            if not source:
                continue
            found = pdf.text_from_html(source, base)
            if found:
                text = "\n".join(part for part in (text, found) if part)
        self._pdf_texts[key] = text
        return text

    def _find_contact(self, job: Job) -> tuple[str, str]:
        """Kontakt suchen: Anzeigetext, Rahmen, Seite, PDF, dann Bilder."""
        address, person = self._text_contact(job)
        if not address or not person:
            # Eingebettete Ausschreibung zuerst: dort steht die Ansprechperson
            # der Firma, waehrend die Portalseite nur eigene Adressen nennt.
            frame = self._frame_text(job)
            if frame:
                frame_address, frame_person = self._contact_from_text(
                    frame, *self._contact_domains(job)
                )
                address = address or frame_address
                person = person or frame_person
        if not address or not person:
            # Viele Portale betten den Anzeigentext als Seite ein; dort steht
            # die Adresse oft im Fliesstext.
            page = self._page_text(job)
            if page:
                page_address, page_person = self._contact_from_text(
                    page, *self._contact_domains(job)
                )
                address = address or page_address
                person = person or page_person
        if not address or not person:
            # PDF-Beilage vor der Bildauslese: dort steht der Text im Klartext.
            pdf_text = self._pdf_text(job)
            if pdf_text:
                pdf_address, pdf_person = self._contact_from_text(
                    pdf_text, *self._contact_domains(job)
                )
                address = address or pdf_address
                person = person or pdf_person
        if not address or not person:
            image_address, image_person = self._ocr_contact(job)
            address = address or image_address
            person = person or image_person
        return address, person

    def _ocr_contact(self, job: Job) -> tuple[str, str]:
        """Ansprechperson und Adresse aus den Bildern der Anzeige lesen."""
        raw = job.raw if isinstance(job.raw, dict) else {}
        html = " ".join(
            str(value)
            for value in raw.values()
            if isinstance(value, str) and "<img" in value.lower()
        )
        if not html or not ocr.available():
            return "", ""
        text = ocr.text_from_html(html, job.url or job.apply_url)
        if not text.strip():
            return "", ""
        addresses = emails(text)
        return (addresses[0] if addresses else ""), (
            contact_person(text) or contact_name(text)
        )

    # ------------------------------------------------------------------
    # Firmenadresse (Strasse und Postleitzahl)
    # ------------------------------------------------------------------
    @staticmethod
    def _portal_address(job: Job) -> tuple[str, str]:
        """Adresse aus den Portalangaben - ohne Netzzugriff."""
        raw = job.raw if isinstance(job.raw, dict) else {}
        company = raw.get("company") if isinstance(raw.get("company"), dict) else {}
        street = str(job.street or company.get("street") or "").strip()
        number = str(company.get("houseNumber") or "").strip()
        if street and number and number not in street.split():
            street = f"{street} {number}"
        zip_code = str(
            job.zip or company.get("zip") or raw.get("workplaceZip") or ""
        ).strip()
        return street, zip_code

    @staticmethod
    def _address_from_text(text: str, city: str = "") -> tuple[str, str]:
        """Strasse und Postleitzahl aus einem geholten Seitentext lesen."""
        plain = re.sub(r"[ \t]+", " ", strip_html(text or ""))
        if not plain.strip():
            return "", ""
        zip_code = ""
        for match in _ZIP_CITY_RE.finditer(plain):
            place = match.group(2).strip()
            if not city or normalize(place).startswith(normalize(city)):
                zip_code = match.group(1)
                break
        street = ""
        for match in _STREET_RE.finditer(plain):
            street = re.sub(r"\s+", " ", match.group(1)).strip()
            break
        return street, zip_code

    def _page_text_for(self, url: str) -> str:
        """Seite einmal holen - gleicher Zwischenspeicher wie die Kontaktsuche."""
        if url not in self._page_texts:
            self._page_texts[url] = self._page_fetcher(url)
        return self._page_texts[url]

    def _lookup_address(self, job: Job) -> tuple[str, str]:
        """Firmenadresse: Portalangaben, sonst Homepage und Impressum im Netz.

        Gelesen wird nur, was im Portal steht oder klar im Seitentext zu
        erkennen ist (Strasse mit Hausnummer, vierstellige PLZ). Die KI ist
        hier bewusst nicht beteiligt, damit nie eine erfundene Adresse im
        Brief landet; bleibt die Adresse unklar, bleibt sie leer.
        """
        street, zip_code = self._portal_address(job)
        if street and zip_code:
            return street, zip_code
        raw = job.raw if isinstance(job.raw, dict) else {}
        company = raw.get("company") if isinstance(raw.get("company"), dict) else {}
        homepage = str(company.get("homepage") or "").strip()
        if not homepage:
            return street, zip_code
        domain = domain_of(homepage) or homepage
        cached = self._address_cache.get(domain)
        if cached:
            found_street, found_zip = cached
            return street or found_street, zip_code or found_zip
        base = homepage.rstrip("/")
        for url in (homepage, f"{base}/impressum", f"{base}/kontakt"):
            page = self._page_text_for(url)
            if not page:
                continue
            found_street, found_zip = self._address_from_text(page, job.city)
            street = street or found_street
            zip_code = zip_code or found_zip
            if street and zip_code:
                break
        self._address_cache[domain] = (street, zip_code)
        return street, zip_code

    @staticmethod
    def _postal_address(job: Job) -> str:
        """Anschrift der Firma für Vorschau und Anschreiben."""
        lines = [
            job.company.strip(),
            job.street.strip(),
            " ".join(part for part in (job.zip.strip(), job.city.strip()) if part),
        ]
        return "\n".join(line for line in lines if line)

    def contact_check(self, job_id: str) -> list[str]:
        """Vor dem Entwurf melden, welche Kontaktdaten noch fehlen.

        Fehlendes wird zuerst aus dem Anzeigetext und dann aus Bildern der
        Anzeige gelesen; was danach fehlt, fragt die Oberflaeche von Hand ab,
        bevor der Entwurf entsteht.
        """
        row = self.store.get_job(job_id)
        if row is None:
            return []
        job = Job.from_row(row)
        address = job.contact_address()
        portal = domain_of(job.url or job.apply_url)
        if address and portal and domain_of(address) == portal:
            # Nur die Adresse des Portals selbst: keine Bewerbungsadresse.
            address = ""
        person = job.contact_name
        if not address or not person:
            # Zuerst der Fliesstext: viele Anzeigen nennen die Adresse nur dort
            # und verlinken im Kontaktfeld bloss ein Bewerbungsformular.
            found_address, found_person = self._find_contact(job)
            updates: dict[str, Any] = {}
            if not address and found_address:
                address = found_address
                updates["contact_email"] = found_address
            if not person and found_person:
                person = found_person
                updates["contact_name"] = found_person
            if updates:
                self.store.update_job(job_id, **updates)
                log.info("Kontakt aus der Anzeige gelesen: %s", job_id)
        gaps: list[str] = []
        if not address:
            gaps.append("email")
        if not person:
            gaps.append("anrede")
        return gaps

    # ------------------------------------------------------------------
    # Datensaetze vervollstaendigen
    # ------------------------------------------------------------------
    def complete_job(self, job_id: str) -> bool:
        """Eine gespeicherte Stelle um fehlende Kontaktdaten ergaenzen."""
        row = self.store.get_job(job_id)
        if row is None:
            return False
        return self._complete_job(Job.from_row(row))

    @staticmethod
    def _missing_contact_fields(job: Job) -> list[str]:
        """Welche Kontaktangaben fehlen noch?"""
        return [
            key
            for key, value in (
                ("contact_email", job.contact_email),
                ("contact_name", job.contact_name),
                ("street", job.street),
                ("zip", job.zip),
            )
            if not value
        ]

    def _complete_job(self, job: Job) -> bool:
        """Name, E-Mail und Adresse nachschauen, solange sie fehlen.

        Gelesen wird nur, was Anzeige, Portal, PDF-Beilage oder Firmenseite
        klar hergeben; geraten wird nichts, und vorhandene Angaben bleiben
        stehen. Uebersprungen wird erst ein Datensatz, dessen Zeile in der
        Stellentabelle alle Angaben zeigt - fehlt eines, wird bei der
        naechsten Suche erneut nachgesehen.
        """
        missing = self._missing_contact_fields(job)
        if not missing:
            return False
        updates: dict[str, Any] = {}
        if not (job.contact_email and job.contact_name):
            address, person = self._find_contact(job)
            portal = domain_of(job.url or job.apply_url)
            # Die Adresse des Portals selbst ist keine Bewerbungsadresse.
            if address and not (portal and domain_of(address) == portal):
                if not job.contact_email:
                    updates["contact_email"] = address
            if person and not job.contact_name:
                updates["contact_name"] = person
        if not (job.street and job.zip):
            street, zip_code = self._lookup_address(job)
            if not (street and zip_code):
                # Bleibt die Firmenseite stumm, steht die Adresse oft in der
                # PDF-Beilage der Anzeige.
                pdf_street, pdf_zip = self._address_from_text(
                    self._pdf_text(job), job.city
                )
                street = street or pdf_street
                zip_code = zip_code or pdf_zip
            if street and not job.street:
                updates["street"] = street
            if zip_code and not job.zip:
                updates["zip"] = zip_code
        values = {
            "contact_email": job.contact_email,
            "contact_name": job.contact_name,
            "street": job.street,
            "zip": job.zip,
        }
        values.update(updates)
        # Nur zur Information (wann zuletzt gesucht, was damals fehlte); der
        # Vermerk blockiert keinen neuen Versuch, solange etwas fehlt.
        self.store.update_job(
            job.id,
            contact_tried_at=now_iso(),
            contact_tried_for=",".join(
                key for key, value in values.items() if not value
            ),
            **updates,
        )
        if not updates:
            return False
        log.info(
            "Stelle vervollstaendigt: %s (%s)", job.id, ", ".join(sorted(updates))
        )
        return True

    def _complete_stored_jobs(self, seen: set[str], limit: int = 15) -> int:
        """Gespeicherte Stellen mit Luecken nachziehen - begrenzt je Lauf.

        Vollstaendige Zeilen kosten nur einen Vergleich; unvollstaendige werden
        erneut gesucht, damit am Ende jede Zeile alle Angaben zeigt.
        """
        done = 0
        for row in self.store.list_jobs(limit=400):
            if done >= limit:
                break
            job_id = str(row.get("id") or "")
            if not job_id or job_id in seen:
                continue
            if str(row.get("status") or "") in {"ignoriert", "archiviert"}:
                continue
            if self._complete_job(Job.from_row(row)):
                done += 1
        return done

    def _write_mail(
        self,
        template: Template,
        job: Job,
        digest: JobDigest,
        day: date | None = None,
    ) -> tuple[str, str]:
        """Betreff und Mailtext - per KI, sonst aus der Vorlage."""
        anrede = salutation(digest.contact_name or job.contact_name)
        method = getattr(self._ai, "write_application", None)
        if callable(method):
            try:
                written = method(template, self.settings.profile(), job, digest)
            except Exception as exc:  # noqa: BLE001 - Vorlage als Rueckfall
                log.warning("KI-Bewerbungstext fehlgeschlagen: %s", exc)
                written = None
            if written and written[0] and written[1]:
                return written[0], self._with_salutation(written[1], anrede)
        return render_mail(
            template,
            self.settings.profile(),
            job,
            day=day,
            extra={"anrede": anrede},
        )

    @staticmethod
    def _with_salutation(text: str, anrede: str) -> str:
        """Erste Anredezeile durch die passende Anrede ersetzen."""
        if not text or anrede.startswith("Sehr geehrte Damen und Herren"):
            return text
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if line.strip().lower().startswith("sehr geehrte"):
                lines[index] = anrede
                return "\n".join(lines)
        return f"{anrede}\n\n{text}"

    def _cover_letter(self, job: Job, digest: JobDigest, fallback: str) -> str:
        """Anschreiben fuer den Anhang - per KI, sonst der Mailtext."""
        anrede = salutation(digest.contact_name or job.contact_name)
        method = getattr(self._ai, "cover_letter", None)
        if callable(method):
            try:
                text = method(self.settings.profile(), job, digest)
            except Exception as exc:  # noqa: BLE001 - Mailtext als Rueckfall
                log.warning("KI-Anschreiben fehlgeschlagen: %s", exc)
                text = None
            if text:
                return self._with_salutation(text, anrede)
        return self._with_salutation(fallback, anrede)

    def _tracking_code(self) -> str:
        """Einmalige Kennung, die in jeder Mail unsichtbar mitreist."""
        return new_code(
            lambda code: self.store.application_by_tracking(code) is not None
        )

    def _attachments(
        self,
        job: Job,
        digest: JobDigest,
        letter: str,
        day: date | None = None,
    ) -> list[Path]:
        """Unterlagen aus dem Ordner, davor das Anschreiben als PDF."""
        attachments = collect(
            self.settings.text("documents.folder"),
            enabled=self.settings.flag("documents.attach", True),
            max_mb=self.settings.number("documents.max_mb", 20) or 20,
        )
        if not self.settings.flag("documents.cover_letter", True):
            return attachments
        text = self._cover_letter(job, digest, letter)
        try:
            path = write_cover_letter(
                self.settings.profile(),
                job.title,
                job.company,
                text,
                city=job.city,
                street=job.street,
                zip_code=job.zip,
                day=day,
                template=self.settings.text("documents.letter_template"),
            )
        except OSError as exc:
            log.warning("Anschreiben konnte nicht gespeichert werden: %s", exc)
            return attachments
        return [path] + attachments

    # ------------------------------------------------------------------
    # Stellen suchen und Bewerbungen vorbereiten
    # ------------------------------------------------------------------
    def run_search(self, now: datetime | None = None) -> RunSummary:
        moment = now or datetime.now(timezone.utc)
        stamp = moment.isoformat(timespec="seconds")
        summary = RunSummary()
        if not self.settings.flag("search.api_enabled", False):
            summary.errors.append(
                "Die Stellen-API von ostjob.ch ist ausgeschaltet "
                "(Einstellungen > Suche)."
            )
            self.store.log("hinweis", "Stellensuche übersprungen: API ist ausgeschaltet.")
            return summary
        templates = self.templates()
        terms = (
            vocabulary(templates)
            + self.settings.skills()
            + self.settings.interests()
        )
        try:
            jobs = search_jobs(self.settings, client=self._ostjob, now=moment)
        except OstjobError as exc:
            summary.errors.append(str(exc))
            self.store.log("fehler", f"Stellensuche fehlgeschlagen: {exc}")
            return summary

        summary.found = len(jobs)
        min_score = int(self.settings.number("matching.min_score", 2) or 2)

        for job in jobs:
            is_new = self.store.upsert_job(job, now=stamp)
            if is_new:
                summary.new += 1
            known = self.store.get_job(job.id) or {}
            if known.get("status") == "ignoriert":
                summary.skipped += 1
                continue

            # Neue Anzeigen einmal auslesen: Titel und Beschreibung bereinigt
            # ablegen, damit weitere Laeufe keine KI mehr brauchen.
            if is_new:
                digest = self._digest(job)
                job = replace(
                    job,
                    title=digest.title or job.title,
                    description=digest.description or job.description,
                    contact_email=digest.contact_email or job.contact_email,
                    contact_name=digest.contact_name or job.contact_name,
                )
                self.store.update_job(
                    job.id,
                    title=job.title,
                    description=job.description,
                    contact_email=job.contact_email,
                    contact_name=job.contact_name,
                )
            else:
                stored_job = Job.from_row(known)
                job = replace(
                    job,
                    title=stored_job.title or job.title,
                    description=stored_job.description or job.description,
                    contact_email=stored_job.contact_email or job.contact_email,
                    contact_name=stored_job.contact_name or job.contact_name,
                )
                digest = local_digest(job)

            # Adresse, E-Mail und Ansprechperson gleich mitnehmen, damit der
            # Datensatz vollstaendig ist - auch bei Stellen ohne Passung.
            self._complete_job(job)
            stored = self.store.get_job(job.id)
            if stored:
                job = Job.from_row(stored)

            if self.store.application_by_job(job.id) is not None:
                continue

            keywords = self._ai.keywords(job, terms)
            template, score, matches = choose_template(
                templates, job, keywords, min_score
            )
            self.store.set_job_analysis(
                job.id, score, template.id if template else "", keywords
            )
            if template is None:
                summary.skipped += 1
                if is_new:
                    self.store.update_job(job.id, status="ohne_passung")
                continue

            summary.matched += 1
            # Entwuerfe entstehen nur noch auf Klick in der Stellenliste,
            # damit zuerst die gefundenen Stellen geprueft werden koennen.
            self.store.update_job(job.id, status="passend")
            self.store.log(
                "stelle",
                (
                    f"Passend: {job.title} bei {job.company} "
                    f"({template.name}, {score} Stichworte: {', '.join(matches[:4])})"
                ),
            )
            if is_new:
                self.notify(
                    "Neue passende Stelle",
                    f"{job.company}: {job.title} – unter Stellen ansehen.",
                )

        # Aeltere Datensaetze mit Luecken ebenfalls nachziehen; begrenzt,
        # damit ein Lauf nicht an vielen fremden Seiten haengt.
        completed = self._complete_stored_jobs({job.id for job in jobs})
        if completed:
            self.store.log(
                "stelle", f"Kontaktdaten ergänzt: {completed} Stellen"
            )

        self.store.meta_set("letzter_lauf", stamp)
        self.store.log("lauf", f"Stellensuche: {summary.as_text()}")
        return summary

    def draft_preview(self, job_id: str) -> dict[str, Any]:
        """Empfänger, Anrede, Betreff und Text für die Vorschau zusammenstellen.

        Es entsteht noch kein Entwurf; die Zwischenstände bleiben für
        :meth:`create_draft` liegen, damit die KI nicht zweimal laufen muss.
        """
        row = self.store.get_job(job_id)
        if row is None:
            raise ValueError("Diese Stelle steht nicht in der Ablage.")
        job = Job.from_row(row)
        digest = self._digest(job)
        job = replace(
            job,
            title=digest.title or job.title,
            description=digest.description or job.description,
            contact_email=digest.contact_email or job.contact_email,
            contact_name=digest.contact_name or job.contact_name,
        )
        self.store.update_job(
            job.id,
            title=job.title,
            description=job.description,
            contact_email=job.contact_email,
            contact_name=job.contact_name,
        )
        # Adresse für den Empfängerblock nachschauen, damit Vorschau und PDF
        # dasselbe zeigen.
        if not (job.street and job.zip):
            street, zip_code = self._lookup_address(job)
            if (street, zip_code) != (job.street, job.zip):
                job = replace(
                    job, street=street or job.street, zip=zip_code or job.zip
                )
                self.store.update_job(job.id, street=job.street, zip=job.zip)
        templates = self.templates()
        keywords = self._ai.keywords(
            job,
            vocabulary(templates)
            + self.settings.skills()
            + self.settings.interests(),
        )
        min_score = int(self.settings.number("matching.min_score", 2) or 2)
        template, score, matches = choose_template(templates, job, keywords, min_score)
        if template is None:
            raise ValueError(
                "Zu dieser Stelle passen zu wenige Stichworte einer Vorlage. "
                "Wählen Sie eine Vorlage mit passenden Stichworten oder "
                "ergänzen Sie die Vorlagen."
            )
        subject, body = self._write_mail(template, job, digest)
        # Fehlt der Anschrift-Platzhalter in der eigenen Vorlage, muss die
        # Vorschau das sagen - sonst fehlt die Adresse still im PDF.
        warnings: list[str] = []
        missing = missing_address_placeholders(
            self.settings.text("documents.letter_template")
        )
        if missing and (job.street or job.zip):
            warnings.append(
                "Die gewählte Anschreiben-Vorlage enthält keinen Platzhalter "
                f"für {' und '.join(missing)} der Firma. Im PDF fehlen diese "
                "Angaben deshalb – ergänzen Sie {firma_strasse} und "
                "{firma_plz_ort} in der Vorlage."
            )
        self._previews[job.id] = {
            "job": job,
            "digest": digest,
            "template": template,
            "keywords": keywords,
            "score": score,
            "matches": matches,
            "subject": subject,
            "body": body,
        }
        return {
            "job_id": job.id,
            "email": job.contact_address(),
            "address": self._postal_address(job),
            "warnings": warnings,
            "salutation": salutation(digest.contact_name or job.contact_name),
            "subject": subject,
            "body": body,
        }

    def proofread_available(self) -> bool:
        """Ist eine KI für die Rechtschreibprüfung eingerichtet?"""
        method = getattr(self._ai, "proofread", None)
        if not callable(method):
            return False
        available = getattr(self._ai, "available", None)
        return bool(available()) if callable(available) else True

    def proofread(self, text: str) -> str:
        """Rechtschreibung prüfen; ohne KI bleibt der Text unverändert."""
        method = getattr(self._ai, "proofread", None)
        if not callable(method) or not (text or "").strip():
            return text
        try:
            corrected = method(text)
        except Exception as exc:  # noqa: BLE001 - Prüfung ist ein Zusatz
            log.warning("Rechtschreibprüfung fehlgeschlagen: %s", exc)
            return text
        return str(corrected or "").strip() or text

    def create_draft(
        self,
        job_id: str,
        *,
        email: str = "",
        subject: str = "",
        body: str = "",
    ) -> int:
        """Entwurf anlegen - mit den Angaben aus der Vorschau, falls geändert."""
        preview = self._previews.get(job_id)
        if preview is None:
            self.draft_preview(job_id)
            preview = self._previews.get(job_id) or {}
        job = preview.get("job")
        if job is None or not isinstance(job, Job):
            raise ValueError("Diese Stelle steht nicht in der Ablage.")
        digest = preview["digest"]
        template = preview["template"]
        subject = (subject or preview.get("subject") or "").strip()
        body = (body or preview.get("body") or "").strip()
        address = (email or "").strip() or job.contact_address()
        attachments = self._attachments(job, digest, body)
        tracking = self._tracking_code()
        draft_id = ""
        conversation_id = ""
        web_link = ""
        if self.outlook_ready():
            draft = self.outlook().create_draft(
                subject, body, address, attachments, tracking=tracking
            )
            draft_id = str(draft.get("id") or "")
            conversation_id = str(draft.get("conversationId") or "")
            web_link = str(draft.get("webLink") or "")
        application_id = self.store.add_application(
            job.id,
            template.id,
            subject,
            body,
            draft_id=draft_id,
            conversation_id=conversation_id,
            web_link=web_link,
            status=STATUS_ENTWURF,
            created_at=now_iso(),
            tracking=tracking,
        )
        score = int(preview.get("score") or 0)
        keywords = list(preview.get("keywords") or [])
        matches = list(preview.get("matches") or [])
        self.store.set_job_analysis(job.id, score, template.id, keywords)
        self.store.update_job(job.id, status="beworben")
        self.store.log(
            "bewerbung",
            f"Entwurf für {job.title} bei {job.company} ({template.name}, "
            f"{score} Stichworte: {', '.join(matches[:4])})",
        )
        self.notify(
            "Bewerbung vorbereitet",
            f"{job.company}: {job.title} liegt als Entwurf bereit.",
        )
        self._previews.pop(job.id, None)
        return application_id

    def prepare_application(self, job_id: str) -> int:
        """Bewerbung ohne Vorschau anlegen (Aufruf ohne Oberfläche)."""
        preview = self.draft_preview(job_id)
        return self.create_draft(
            job_id, subject=str(preview["subject"]), body=str(preview["body"])
        )

    def follow_up_preview(self, application_id: int) -> dict[str, Any]:
        """Empfänger, Anrede, Betreff und Text der Nachfrage zusammenstellen.

        Es entsteht noch kein Entwurf; die Angaben bleiben für
        :meth:`create_follow_up_draft` liegen.
        """
        application = self.store.get_application(application_id)
        if application is None:
            raise ValueError("Bewerbung nicht gefunden.")
        template = follow_up_template(self.templates())
        if template is None:
            raise ValueError("Keine Vorlage für Nachfragen vorhanden.")
        job_row = self.store.get_job(str(application.get("job_id") or ""))
        job = Job.from_row(job_row) if job_row else None
        # Die Nachfrage traegt dieselbe Kennung wie die Bewerbung - auch fuer
        # Bewerbungen aus frueheren Fassungen, die noch keine haben.
        tracking = str(application.get("tracking") or "") or self._tracking_code()
        if not str(application.get("tracking") or ""):
            self.store.update_application(application_id, tracking=tracking)
        days = int(self.settings.number("automation.follow_up_days", 14) or 14)
        anrede = salutation(job.contact_name if job else "")
        subject, body = render_mail(
            template,
            self.settings.profile(),
            job,
            extra={
                "bewerbungsdatum": format_date(application.get("sent_at")),
                "tage": str(days),
                "anrede": anrede,
            },
        )
        preview = {
            "application_id": application_id,
            "company": str(application.get("company") or ""),
            "title": str(application.get("title") or ""),
            "email": (job.contact_address() if job else "") or "",
            "salutation": anrede,
            "subject": subject,
            "body": body,
            "tracking": tracking,
            "days": days,
        }
        self._follow_up_previews[application_id] = preview
        return preview

    def create_follow_up_draft(
        self,
        application_id: int,
        *,
        email: str = "",
        subject: str = "",
        body: str = "",
    ) -> bool:
        """Nachfrage anlegen - mit den Angaben aus der Vorschau, falls geändert."""
        preview = self._follow_up_previews.get(application_id)
        if preview is None:
            preview = self.follow_up_preview(application_id)
        application = self.store.get_application(application_id)
        if application is None:
            raise ValueError("Bewerbung nicht gefunden.")
        job_row = self.store.get_job(str(application.get("job_id") or ""))
        job = Job.from_row(job_row) if job_row else None
        subject = (subject or str(preview.get("subject") or "")).strip()
        body = (body or str(preview.get("body") or "")).strip()
        address = (email or "").strip() or str(preview.get("email") or "")
        if not address:
            address = job.contact_address() if job else ""
        tracking = str(preview.get("tracking") or "") or str(
            application.get("tracking") or ""
        )
        draft_id = ""
        conversation_id = ""
        web_link = ""
        if self.outlook_ready():
            draft = self.outlook().create_draft(
                subject,
                body,
                address,
                tracking=tracking,
            )
            draft_id = str(draft.get("id") or "")
            conversation_id = str(draft.get("conversationId") or "")
            web_link = str(draft.get("webLink") or "")
        self.store.update_application(
            application_id,
            status=STATUS_NACHGEFASST,
            follow_up_at=now_iso(),
            follow_up_subject=subject,
            follow_up_body=body,
            follow_up_draft_id=draft_id,
            follow_up_conversation_id=conversation_id,
            follow_up_web_link=web_link,
        )
        company = application.get("company") or "Firma"
        self.store.log("nachfrage", f"Nachfrage für {company} vorbereitet.")
        self.notify("Nachfrage vorbereitet", f"{company}: {application.get('title') or ''}")
        return True

    def prepare_follow_up(self, application_id: int) -> bool:
        """Nachfrage ohne Vorschau anlegen (Tageslauf, Aufruf ohne Oberfläche)."""
        preview = self.follow_up_preview(application_id)
        return self.create_follow_up_draft(
            application_id,
            email=str(preview.get("email") or ""),
            subject=str(preview.get("subject") or ""),
            body=str(preview.get("body") or ""),
        )

    # ------------------------------------------------------------------
    # Versand erkennen
    # ------------------------------------------------------------------
    def check_drafts(self) -> int:
        """Versand prüfen: nur eine Mail im Ordner «Gesendet» zählt.

        Gelesen werden die letzten 100 Mails aus «Gesendet». Fehlt der Entwurf,
        ohne dass die Mail dort auftaucht, bleibt die Bewerbung ein Entwurf.
        """
        if not self.outlook_ready():
            return 0
        client = self.outlook()
        try:
            sent = self._sent_messages(client)
        except (OutlookError, ImapError) as exc:
            self.store.log("fehler", f"Versandprüfung: {exc}")
            return 0
        if sent is None:
            # Ohne Sammelabruf gibt es keinen zweiten Weg: nichts markieren.
            self.store.log(
                "fehler",
                "Versandprüfung: Das Mailkonto liefert keinen Sent-Abruf.",
            )
            return 0
        count = 0
        for application in self.store.list_applications(status=STATUS_ENTWURF):
            code = str(application.get("tracking") or "")
            conversation = str(application.get("conversation_id") or "")
            if not code and not conversation:
                continue
            if _recent(str(application.get("created_at") or "")):
                continue
            message = self._sent_entry(application, sent)
            if message is None:
                continue
            sent_at = str(message.get("sentDateTime") or "")
            self.store.update_application(
                int(application["id"]),
                status=STATUS_GESENDET,
                sent_at=sent_at or now_iso(),
                internet_message_id=str(message.get("internetMessageId") or ""),
            )
            company = application.get("company") or "Firma"
            self.store.log(
                "versand",
                f"Bewerbung an {company} steht im Ordner Gesendet "
                f"({code}, {format_datetime(sent_at) or sent_at}) – "
                "als gesendet markiert.",
            )
            self.notify(
                "Bewerbung gesendet",
                f"{company}: {application.get('title') or ''}",
            )
            count += 1
        count += self._check_follow_up_drafts(sent)
        return count

    def _sent_messages(self, client: Any) -> list[dict[str, Any]] | None:
        """Die letzten Mails aus «Gesendet»; ``None`` ohne Sammelabruf."""
        recent = getattr(client, "sent_recent", None)
        if callable(recent):
            return list(recent(SENT_LOOKBACK) or [])
        return None

    def _sent_entry(
        self,
        application: dict[str, Any],
        sent: list[dict[str, Any]],
        *,
        conversation_key: str = "conversation_id",
        not_before: str = "",
    ) -> dict[str, Any] | None:
        """Mail zu einer Bewerbung in «Gesendet» finden – sonst ``None``."""
        conversation = str(application.get(conversation_key) or "")
        code = str(application.get("tracking") or "").lower()
        threshold = _moment(not_before)
        for message in sent:
            moment = _moment(str(message.get("sentDateTime") or ""))
            if threshold is not None and moment is not None and moment < threshold:
                continue
            if conversation and str(message.get("conversationId") or "") == conversation:
                return message
        if not code:
            return None
        for message in sent:
            moment = _moment(str(message.get("sentDateTime") or ""))
            if threshold is not None and moment is not None and moment < threshold:
                continue
            haystack = " ".join(
                str(message.get(key) or "")
                for key in ("tracking", "subject", "text", "body")
            ).lower()
            if code in haystack:
                return message
        return None

    def _check_follow_up_drafts(self, sent: list[dict[str, Any]]) -> int:
        """Nachfragen gelten erst als verschickt, wenn sie in «Gesendet» liegen."""
        count = 0
        for application in self.store.list_applications():
            if str(application.get("status") or "") != STATUS_NACHGEFASST:
                continue
            if not application.get("follow_up_at"):
                continue
            if application.get("follow_up_sent_at"):
                continue
            # Ohne angelegten Entwurf (Mailkonto war nicht bereit) gibt es
            # nichts zu pruefen.
            if not str(application.get("follow_up_draft_id") or ""):
                continue
            code = str(application.get("tracking") or "")
            conversation = str(application.get("follow_up_conversation_id") or "")
            if not code and not conversation:
                continue
            if _recent(str(application.get("follow_up_at") or "")):
                continue
            try:
                message = self._sent_entry(
                    application,
                    sent,
                    conversation_key="follow_up_conversation_id",
                    not_before=str(application.get("follow_up_at") or ""),
                )
            except (OutlookError, ImapError) as exc:
                self.store.log("fehler", f"Nachfrage-Prüfung: {exc}")
                return count
            if message is None:
                continue
            sent_at = str(message.get("sentDateTime") or now_iso())
            self.store.update_application(
                int(application["id"]),
                follow_up_sent_at=sent_at,
            )
            company = application.get("company") or "Firma"
            self.store.log(
                "versand",
                f"Nachfrage an {company} steht im Ordner Gesendet "
                f"({code}) – als verschickt vermerkt.",
            )
            self.notify(
                "Nachfrage gesendet",
                f"{company}: {application.get('title') or ''}",
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Antworten auswerten
    # ------------------------------------------------------------------
    def check_replies(self) -> list[dict[str, Any]]:
        if not self.outlook_ready():
            return []
        client = self.outlook()
        since = self.store.meta_get("posteingang_seit", "")
        if not since:
            since = (
                datetime.now(timezone.utc) - timedelta(days=30)
            ).isoformat(timespec="seconds")
        try:
            messages = client.inbox_since(since)
        except (OutlookError, ImapError) as exc:
            self.store.log("fehler", f"Posteingang: {exc}")
            return []

        active = self.store.active_applications()
        found: list[dict[str, Any]] = []
        newest = since
        for message in messages:
            received = str(message.get("receivedDateTime") or "")
            if received and received > newest:
                newest = received
            matched = self._match_reply(message, active)
            if matched is None:
                continue
            application, via = matched
            message_id = str(message.get("id") or "")
            if not message_id:
                continue
            sender = sender_address(message)
            subject = str(message.get("subject") or "")
            body = message_body(message)
            job_row = self.store.get_job(str(application.get("job_id") or ""))
            job = Job.from_row(job_row) if job_row else None
            context = (
                f"Bewerbung als {job.title} bei {job.company}" if job else ""
            )
            kind = self._ai.classify(subject, body, sender, context)
            added = self.store.add_reply(
                int(application["id"]),
                message_id,
                received,
                sender,
                subject,
                kind,
                short(body, 400),
                body=body[:20000],
            )
            if not added:
                continue
            self._apply_reply(application, kind, sender, subject, via)
            found.append(
                {
                    "application": application,
                    "kind": kind,
                    "sender": sender,
                    "subject": subject,
                }
            )
        self.store.meta_set(
            "posteingang_seit",
            (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(
                timespec="seconds"
            ),
        )
        return found

    def _match_reply(
        self, message: dict[str, Any], active: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], str] | None:
        """Bewerbung und Weg der Zuordnung (für das Protokoll)."""
        # Zuerst die mitgereiste Kennung: sie bleibt eindeutig, auch wenn
        # Betreff und Absender nichts verraten.
        code = str(message.get("tracking") or "") or find_code(
            f"{message.get('subject') or ''}\n{message_body(message)}"
        )
        if code:
            application = self.store.application_by_tracking(code)
            if application is not None:
                return application, f"Kennung {code}"
        conversation = str(message.get("conversationId") or "")
        sender = sender_address(message)
        sender_domain = domain_of(sender)
        subject = normalize(str(message.get("subject") or ""))
        for application in active:
            if conversation and conversation == application.get("conversation_id"):
                return application, "Unterhaltung"
            job_row = self.store.get_job(str(application.get("job_id") or ""))
            job = Job.from_row(job_row) if job_row else None
            if job is None:
                continue
            if sender_domain and sender_domain in job.domained():
                return application, f"Absenderdomain {sender_domain}"
            company = normalize(job.company)
            if len(company) >= 4 and company in subject:
                return application, "Firmenname"
            title = normalize(job.title)
            if len(title) >= 12 and title in subject:
                return application, "Stellentitel"
        return None

    def _apply_reply(
        self,
        application: dict[str, Any],
        kind: str,
        sender: str,
        subject: str,
        via: str = "",
        manual: bool = False,
    ) -> None:
        app_id = int(application["id"])
        company = application.get("company") or "Firma"
        job_id = str(application.get("job_id") or "")
        stamp = now_iso()
        self.store.update_application(
            app_id, last_reply_at=stamp, reply_kind=kind
        )
        label = {
            ABSAGE: "Absage",
            ZUSAGE: "Zusage",
            EINLADUNG: "Einladung zum Gespräch",
            INFO: "Antwort",
        }.get(kind, "Antwort")
        if manual:
            routing = " – von Hand eingeordnet"
        else:
            routing = f" – zugeordnet über {via}" if via else ""
        self.store.log("antwort", f"{label} von {company}: {subject}{routing}")
        if kind == ABSAGE:
            self.store.update_application(
                app_id,
                status=STATUS_ABSAGE,
                archived_at=stamp,
                reply_note=subject,
            )
            self.store.update_job(job_id, status=STATUS_ARCHIVIERT)
            self.notify("Absage", f"{company}: {subject}")
        elif kind == ZUSAGE:
            self.store.update_application(
                app_id, status=STATUS_ZUSAGE, reply_note=subject
            )
            self.store.update_job(job_id, status=STATUS_ZUSAGE)
            self.notify("Zusage", f"{company}: {subject}")
        elif kind == EINLADUNG:
            self.store.update_application(app_id, status=STATUS_EINLADUNG)
            self.notify("Einladung", f"{company}: {subject}")
        else:
            # Eine blosse Antwort ist ein eigener Status, damit der Filter
            # «Antwort» im Tab Bewerbungen etwas zeigt. Absage, Zusage und
            # Einladung bleiben stehen, wenn danach noch eine Info kommt.
            changes: dict[str, Any] = {"reply_note": subject}
            if application.get("status") in {STATUS_GESENDET, STATUS_NACHGEFASST}:
                changes["status"] = STATUS_ANTWORT
            self.store.update_application(app_id, **changes)

    def set_reply_kind(self, application_id: int, kind: str) -> None:
        """Antwort von Hand als Zusage, Einladung oder Absage einordnen."""
        if kind not in {ABSAGE, ZUSAGE, EINLADUNG}:
            return
        application = self.store.get_application(application_id)
        if application is None:
            return
        self.store.set_reply_kind(application_id, kind)
        if kind in {ZUSAGE, EINLADUNG}:
            # Eine frueher erfasste Absage nimmt die Bewerbung nicht mit.
            self.store.update_application(application_id, archived_at="")
        replies = self.store.replies_for(application_id)
        subject = str(replies[-1].get("subject") or "") if replies else ""
        if not subject:
            subject = str(application.get("reply_note") or "")
        self._apply_reply(application, kind, "", subject, manual=True)

    # ------------------------------------------------------------------
    # Nachfassen
    # ------------------------------------------------------------------
    def prepare_follow_ups(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(timezone.utc)
        days = int(self.settings.number("automation.follow_up_days", 14) or 14)
        due = self.store.due_follow_ups(days, moment.date())
        if not due:
            return 0
        count = 0
        for application in due:
            try:
                if self.prepare_follow_up(int(application["id"])):
                    count += 1
            except (OutlookError, ImapError, ValueError) as exc:
                self.store.log("fehler", f"Nachfrage-Entwurf: {exc}")
        return count

    # ------------------------------------------------------------------
    def run_daily(self, now: datetime | None = None) -> RunSummary:
        moment = now or datetime.now(timezone.utc)
        summary = self.run_search(moment)
        try:
            self.check_drafts()
            if self.settings.flag("automation.check_replies", True):
                self.check_replies()
        except (OutlookError, ImapError) as exc:
            summary.errors.append(str(exc))
            self.store.log("fehler", f"E-Mail-Anbindung: {exc}")
        self.store.meta_set("letzter_tageslauf", now_iso())
        return summary


def next_run_at(daily_time: str, reference: datetime | None = None) -> datetime | None:
    """Naechster geplanter Lauf zur Uhrzeit HH:MM."""
    text = (daily_time or "").strip()
    if ":" not in text:
        return None
    try:
        hour, minute = (int(part) for part in text.split(":", 1))
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    moment = reference or datetime.now()
    candidate = moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= moment:
        candidate += timedelta(days=1)
    return candidate


def reply_summary(application: dict[str, Any]) -> str:
    kind = str(application.get("reply_kind") or "")
    if not kind:
        return ""
    return {
        ABSAGE: "Absage",
        ZUSAGE: "Zusage",
        EINLADUNG: "Einladung",
        INFO: "Antwort",
    }.get(kind, kind)


def follow_up_in_days(application: dict[str, Any], days: int = 14) -> int | None:
    """Wie viele Tage bis zur Nachfrage bleiben?"""
    if application.get("status") != STATUS_GESENDET:
        return None
    if application.get("last_reply_at") or application.get("follow_up_at"):
        return None
    sent = parse_date(application.get("sent_at"))
    if sent is None:
        return None
    due = sent + timedelta(days=max(1, days))
    return (due - date.today()).days


def due_label(application: dict[str, Any], days: int = 14) -> str:
    remaining = follow_up_in_days(application, days)
    if remaining is None:
        return ""
    if remaining <= 0:
        return "fällig"
    return f"in {remaining} Tagen"


__all__ = [
    "Pipeline",
    "RunSummary",
    "STATUS_ABSAGE",
    "STATUS_ARCHIVIERT",
    "STATUS_EINLADUNG",
    "STATUS_ENTWURF",
    "STATUS_GESENDET",
    "STATUS_NACHGEFASST",
    "STATUS_ZUSAGE",
    "classify_local",
    "days_until",
    "due_label",
    "follow_up_in_days",
    "next_run_at",
    "reply_summary",
]
