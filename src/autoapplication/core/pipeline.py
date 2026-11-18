"""Der Tageslauf von AutoApplication.

1. Neue Stellen von ostjob.ch holen und Stichworte bestimmen.
2. Passende Vorlage waehlen und eine Bewerbung als Outlook-Entwurf ablegen.
3. Gesendete Entwuerfe und Antworten im Posteingang verfolgen.
4. Nach zwei Wochen ohne Antwort eine Nachfrage vorbereiten.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

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
from .documents import collect, describe, write_cover_letter
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
    days_until,
    domain_of,
    format_date,
    normalize,
    now_iso,
    parse_date,
    short,
)

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
            f"{self.drafts} Entwürfe",
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
        ostjob_client: OstjobClient | None = None,
        notifier: Callable[[str, str], None] | None = None,
        templates_file: Path | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self._ai = ai_client or AiClient(settings)
        self._outlook = outlook_client
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
        if self._outlook is not None:
            return True
        if self.mail_provider() != "outlook":
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

    def mail(self) -> OutlookClient:
        if self._outlook is not None:
            return self._outlook
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
        method = getattr(self._ai, "job_digest", None)
        if callable(method):
            try:
                digest = method(job)
                if isinstance(digest, JobDigest):
                    return digest
            except Exception as exc:  # noqa: BLE001 - lokaler Rueckfall
                log.warning("Anzeige konnte nicht gelesen werden: %s", exc)
        return local_digest(job)

    def _write_mail(
        self,
        template: Template,
        job: Job,
        digest: JobDigest,
        day: date | None = None,
    ) -> tuple[str, str]:
        """Betreff und Mailtext - per KI, sonst aus der Vorlage."""
        method = getattr(self._ai, "write_application", None)
        if callable(method):
            try:
                written = method(template, self.settings.profile(), job, digest)
            except Exception as exc:  # noqa: BLE001 - Vorlage als Rueckfall
                log.warning("KI-Bewerbungstext fehlgeschlagen: %s", exc)
                written = None
            if written and written[0] and written[1]:
                return written
        return render_mail(template, self.settings.profile(), job, day=day)

    def _cover_letter(self, job: Job, digest: JobDigest, fallback: str) -> str:
        """Anschreiben fuer den Anhang - per KI, sonst der Mailtext."""
        method = getattr(self._ai, "cover_letter", None)
        if callable(method):
            try:
                text = method(self.settings.profile(), job, digest)
            except Exception as exc:  # noqa: BLE001 - Mailtext als Rueckfall
                log.warning("KI-Anschreiben fehlgeschlagen: %s", exc)
                text = None
            if text:
                return text
        return fallback

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
        auto_draft = self.settings.flag("matching.auto_draft", True)
        remaining = int(self.settings.number("matching.max_drafts_per_run", 5) or 5)

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
                )
                self.store.update_job(
                    job.id,
                    title=job.title,
                    description=job.description,
                    contact_email=job.contact_email,
                )
            else:
                stored_job = Job.from_row(known)
                job = replace(
                    job,
                    title=stored_job.title or job.title,
                    description=stored_job.description or job.description,
                    contact_email=stored_job.contact_email or job.contact_email,
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
            if not auto_draft or remaining <= 0:
                self.store.update_job(job.id, status="passend")
                continue

            subject, body = self._write_mail(template, job, digest, moment.date())
            attachments = self._attachments(job, digest, body, moment.date())
            draft_id = ""
            conversation_id = ""
            web_link = ""
            problem = ""
            if self.outlook_ready():
                try:
                    draft = self.outlook().create_draft(
                        subject,
                        body,
                        job.contact_address(),
                        attachments,
                    )
                    draft_id = str(draft.get("id") or "")
                    conversation_id = str(draft.get("conversationId") or "")
                    web_link = str(draft.get("webLink") or "")
                except OutlookError as exc:
                    problem = str(exc)
                    summary.errors.append(problem)
                    self.store.log("fehler", f"E-Mail-Entwurf: {problem}")
            application_id = self.store.add_application(
                job.id,
                template.id,
                subject,
                body,
                draft_id=draft_id,
                conversation_id=conversation_id,
                web_link=web_link,
                status=STATUS_ENTWURF,
                created_at=stamp,
            )
            self.store.update_job(job.id, status="beworben")
            self.store.log(
                "bewerbung",
                (
                    f"Entwurf für {job.title} bei {job.company} "
                    f"({template.name}, {score} Stichworte: {', '.join(matches[:4])})"
                    + ("" if attachments else ", ohne Anhänge")
                    + (f" – {describe(attachments or [])}" if attachments else "")
                ),
            )
            remaining -= 1
            summary.drafts += 1
            if application_id and problem:
                self.store.update_application(application_id, reply_note=problem)
            if is_new:
                self.notify(
                    "Bewerbung vorbereitet",
                    f"{job.company}: {job.title} liegt als Entwurf bereit.",
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
        )
        self.store.update_job(
            job.id,
            title=job.title,
            description=job.description,
            contact_email=job.contact_email,
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
        draft_id = ""
        conversation_id = ""
        web_link = ""
        if self.outlook_ready():
            draft = self.outlook().create_draft(
                subject, body, job.contact_address(), attachments
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
        days = int(self.settings.number("automation.follow_up_days", 14) or 14)
        subject, body = render_mail(
            template,
            self.settings.profile(),
            job,
            extra={
                "bewerbungsdatum": format_date(application.get("sent_at")),
                "tage": str(days),
            },
        )
        draft_id = ""
        conversation_id = ""
        web_link = ""
        if self.outlook_ready():
            draft = self.outlook().create_draft(
                subject, body, job.contact_address() if job else ""
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
            except OutlookError as exc:
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
        except OutlookError as exc:
            self.store.log("fehler", f"Posteingang: {exc}")
            return []

        active = self.store.active_applications()
        found: list[dict[str, Any]] = []
        newest = since
        for message in messages:
            received = str(message.get("receivedDateTime") or "")
            if received and received > newest:
                newest = received
            application = self._match_reply(message, active)
            if application is None:
                continue
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
            self._apply_reply(application, kind, sender, subject)
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
    ) -> dict[str, Any] | None:
        conversation = str(message.get("conversationId") or "")
        sender = sender_address(message)
        sender_domain = domain_of(sender)
        subject = normalize(str(message.get("subject") or ""))
        for application in active:
            if conversation and conversation == application.get("conversation_id"):
                return application
            job_row = self.store.get_job(str(application.get("job_id") or ""))
            job = Job.from_row(job_row) if job_row else None
            if job is None:
                continue
            if sender_domain and sender_domain in job.domained():
                return application
            company = normalize(job.company)
            if len(company) >= 4 and company in subject:
                return application
            title = normalize(job.title)
            if len(title) >= 12 and title in subject:
                return application
        return None

    def _apply_reply(
        self,
        application: dict[str, Any],
        kind: str,
        sender: str,
        subject: str,
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
        self.store.log("antwort", f"{label} von {company}: {subject}")
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
            except (OutlookError, ValueError) as exc:
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
            self.prepare_follow_ups(moment)
        except OutlookError as exc:
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
