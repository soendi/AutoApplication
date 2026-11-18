"""Der Tageslauf von AutoApplication.

1. Neue Stellen von ostjob.ch holen und Stichworte bestimmen.
2. Passende Vorlage waehlen und eine Bewerbung als Mail-Entwurf ablegen.
3. Gesendete Entwuerfe und Antworten im Posteingang verfolgen.
4. Nach zwei Wochen ohne Antwort eine Nachfrage vorbereiten.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import ocr
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
from .documents import collect, write_cover_letter
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
    contact_person,
    days_until,
    domain_of,
    emails,
    format_date,
    normalize,
    now_iso,
    parse_date,
    salutation,
    short,
)
from .tracking import find_code, new_code

log = logging.getLogger(__name__)

STATUS_ENTWURF = "entwurf"
STATUS_GESENDET = "gesendet"
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
    ) -> None:
        self.settings = settings
        self.store = store
        self._ai = ai_client or AiClient(settings)
        self._outlook = outlook_client
        self._imap = imap_client
        self._ostjob = ostjob_client
        self.notifier = notifier
        self.templates_file = templates_file or templates_path()

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
        """Fehlenden Kontakt aus Bildern der Anzeige lesen (Texterkennung)."""
        if digest.contact_email and digest.contact_name:
            return digest
        address, person = self._ocr_contact(job)
        if not digest.contact_email and address:
            digest.contact_email = address
        if not digest.contact_name and person:
            digest.contact_name = person
        return digest

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
        return (addresses[0] if addresses else ""), contact_person(text)

    def contact_check(self, job_id: str) -> list[str]:
        """Vor dem Entwurf melden, welche Kontaktdaten noch fehlen.

        Fehlendes wird zuerst aus Bildern der Anzeige gelesen; was danach
        fehlt, fragt die Oberflaeche von Hand ab, bevor der Entwurf entsteht.
        """
        row = self.store.get_job(job_id)
        if row is None:
            return []
        job = Job.from_row(row)
        address = job.contact_address()
        person = job.contact_name
        if not address or not person:
            found_address, found_person = self._ocr_contact(job)
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
                day=day,
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
        terms = vocabulary(templates) + self.settings.skills()
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
            existing = self.store.application_by_job(job.id)
            if existing is not None:
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

        self.store.meta_set("letzter_lauf", stamp)
        self.store.log("lauf", f"Stellensuche: {summary.as_text()}")
        return summary

    def prepare_application(self, job_id: str) -> int:
        """Bewerbung fuer eine einzelne Stelle von Hand vorbereiten."""
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
        templates = self.templates()
        keywords = self._ai.keywords(
            job, vocabulary(templates) + self.settings.skills()
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
        attachments = self._attachments(job, digest, body)
        tracking = self._tracking_code()
        draft_id = ""
        conversation_id = ""
        web_link = ""
        if self.outlook_ready():
            draft = self.outlook().create_draft(
                subject, body, job.contact_address(), attachments, tracking=tracking
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
        return application_id

    def prepare_follow_up(self, application_id: int) -> bool:
        """Nachfrage fuer eine bestimmte Bewerbung vorbereiten."""
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
        subject, body = render_mail(
            template,
            self.settings.profile(),
            job,
            extra={
                "bewerbungsdatum": format_date(application.get("sent_at")),
                "tage": str(days),
                "anrede": salutation(job.contact_name if job else ""),
            },
        )
        draft_id = ""
        conversation_id = ""
        web_link = ""
        if self.outlook_ready():
            draft = self.outlook().create_draft(
                subject,
                body,
                job.contact_address() if job else "",
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

    # ------------------------------------------------------------------
    # Versand erkennen
    # ------------------------------------------------------------------
    def sync_sent(self) -> int:
        if not self.outlook_ready():
            return 0
        client = self.outlook()
        count = 0
        for application in self.store.list_applications(status=STATUS_ENTWURF):
            conversation = application.get("conversation_id") or ""
            if not conversation:
                continue
            try:
                sent = client.find_sent(conversation)
            except (OutlookError, ImapError) as exc:
                self.store.log("fehler", f"Versandprüfung: {exc}")
                return count
            if not sent:
                continue
            sent_at = str(sent.get("sentDateTime") or now_iso())
            self.store.update_application(
                application["id"],
                status=STATUS_GESENDET,
                sent_at=sent_at,
                internet_message_id=str(sent.get("internetMessageId") or ""),
            )
            self.store.log(
                "versand",
                f"Bewerbung an {application.get('company') or ''} wurde gesendet.",
            )
            self.notify(
                "Bewerbung gesendet",
                f"{application.get('company') or 'Firma'}: {application.get('title') or ''}",
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
            kind = self._ai.classify(subject, body, sender)
            added = self.store.add_reply(
                int(application["id"]),
                message_id,
                received,
                sender,
                subject,
                kind,
                short(body, 400),
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
            self.store.update_application(app_id, reply_note=subject)

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
            self.sync_sent()
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
