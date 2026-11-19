from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from autoapplication.core.ai import JobDigest, local_digest
from autoapplication.core.config import Settings
from autoapplication.core.models import Job
from autoapplication.core.pipeline import Pipeline
from autoapplication.core.store import Store


def _job(identifier: str, title: str, description: str, keywords: list[str]) -> Job:
    return Job(
        id=f"ostjob:{identifier}",
        source="ostjob",
        source_id=identifier,
        title=title,
        company="Muster Logistik AG",
        city="Balgach",
        workload="80-100 %",
        workload_min=80,
        workload_max=100,
        published="2026-11-18",
        description=description,
        keywords=keywords,
        contact_email="bewerbung@muster-logistik.ch",
        raw={"company": {"homepage": "https://muster-logistik.ch"}},
    )


MATCHING = _job("1", "Speditionskaufmann", "Disposition, Transport und Zoll", ["Spedition"])
UNRELATED = _job("2", "Buchhalter Treuhand", "Belege und Jahresabschluss", ["Buchhaltung"])


class FakeOstjob:
    def __init__(self, jobs: list[Job]) -> None:
        self.jobs = jobs

    def vacancies(self, query, home=None):
        return list(self.jobs), 1


class FakeAI:
    def keywords(self, job: Job, vocabulary: list[str]) -> list[str]:
        return list(job.keywords)

    def classify(
        self, subject: str, body: str, sender: str = "", context: str = ""
    ) -> str:
        return "absage" if "Absage" in body or "Absage" in subject else "info"

    def job_digest(self, job: Job) -> JobDigest:
        return local_digest(job)

    def write_application(self, template, profile, job, digest=None):
        return None

    def cover_letter(self, profile, job, digest=None):
        return None


class WritingAI(FakeAI):
    """Attrappe, die Mailtext und Anschreiben selbst schreibt."""

    def job_digest(self, job: Job) -> JobDigest:
        if job.source_id != "1":
            return local_digest(job)
        return JobDigest(
            "Speditionskaufmann",
            "Disposition und Zoll",
            "ki@muster-logistik.ch",
        )

    def write_application(self, template, profile, job, digest=None):
        return (
            "Bewerbung als Speditionskaufmann",
            "Sehr geehrte Damen und Herren,\n\n" + "Ich disponiere gerne. " * 8,
        )

    def cover_letter(self, profile, job, digest=None):
        return "Sehr geehrte Damen und Herren,\n\n" + "Anschreiben zur Stelle. " * 12


class FakeOutlook:
    def __init__(self) -> None:
        self.drafts: list[dict] = []
        self.sent_messages: list[dict] = []
        self.sent_limit: int | None = None
        self.messages: list[dict] = []

    def create_draft(
        self, subject, body, to_address="", attachments=None, tracking=""
    ):
        self.drafts.append(
            {
                "subject": subject,
                "body": body,
                "to": to_address,
                "tracking": tracking,
                "attachments": [str(path) for path in attachments or []],
            }
        )
        return {
            "id": f"draft{len(self.drafts)}",
            "conversationId": f"conv{len(self.drafts)}",
            "webLink": "https://outlook.test/draft",
        }

    def sent_recent(self, limit: int = 100):
        self.sent_limit = limit
        return list(self.sent_messages)

    def inbox_since(self, since_iso: str, top: int = 50):
        return list(self.messages)


def _pipeline(
    tmp_path,
    *,
    jobs=None,
    outlook=None,
    ai=None,
    imap=None,
    api_enabled=True,
    page_fetcher=None,
):
    settings = Settings(tmp_path / "einstellungen.json")
    settings.set("search.api_enabled", api_enabled)
    settings.set("search.queries", ["Spedition"])
    settings.set("matching.min_score", 2)
    settings.set("documents.attach", False)
    store = Store(tmp_path / "daten.db")
    outlook = outlook or FakeOutlook()
    pipeline = Pipeline(
        settings,
        store,
        ai_client=ai or FakeAI(),
        outlook_client=outlook,
        imap_client=imap,
        ostjob_client=FakeOstjob(jobs if jobs is not None else [MATCHING, UNRELATED]),
        templates_file=tmp_path / "vorlagen.json",
        # Kein echter Netzzugriff in Tests: Seiten nur, wenn ausdruecklich geliefert.
        page_fetcher=page_fetcher or (lambda url: ""),
    )
    return pipeline, store, outlook, settings


def test_search_api_off_by_default(tmp_path) -> None:
    pipeline, store, outlook, settings = _pipeline(tmp_path, api_enabled=False)
    summary = pipeline.run_search()
    assert summary.found == 0
    assert summary.drafts == 0
    assert summary.errors and "ausgeschaltet" in summary.errors[0]
    assert store.list_jobs() == []
    assert outlook.drafts == []
    assert settings.flag("search.api_enabled") is False


def test_run_search_marks_jobs_without_draft(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    summary = pipeline.run_search(datetime(2026, 11, 18, 7, 30, tzinfo=timezone.utc))
    assert summary.found == 2
    assert summary.new == 2
    assert summary.matched == 1
    assert summary.drafts == 0
    assert outlook.drafts == []
    assert store.list_applications() == []
    assert store.get_job("ostjob:1")["status"] == "passend"
    assert store.get_job("ostjob:2")["status"] == "ohne_passung"

    application_id = pipeline.prepare_application(MATCHING.id)
    assert application_id > 0
    assert len(outlook.drafts) == 1
    draft = outlook.drafts[0]
    assert "Muster Logistik AG" in draft["body"]
    assert draft["to"] == "bewerbung@muster-logistik.ch"
    applications = store.list_applications()
    assert len(applications) == 1
    assert applications[0]["template_id"] == "spedition"
    assert applications[0]["status"] == "entwurf"
    assert store.get_job("ostjob:1")["status"] == "beworben"


def test_run_search_fills_address_from_company_website(tmp_path) -> None:
    pages = {
        "https://muster-logistik.ch": (
            "<html><body><p>Muster Logistik AG</p>"
            "<p>Bahnhofstrasse 12</p><p>9436 Balgach</p></body></html>"
        )
    }
    pipeline, store, _, _ = _pipeline(
        tmp_path, page_fetcher=lambda url: pages.get(url.rstrip("/"), "")
    )
    pipeline.run_search(datetime(2026, 11, 18, 7, 30, tzinfo=timezone.utc))
    job = store.get_job("ostjob:1")
    assert job["street"] == "Bahnhofstrasse 12"
    assert job["zip"] == "9436"


def test_portal_address_needs_no_web_lookup(tmp_path) -> None:
    from dataclasses import replace

    def boom(url: str) -> str:
        raise AssertionError(f"Portalangaben genuegen, kein Abruf noetig: {url}")

    job = replace(
        MATCHING,
        id="ostjob:3",
        source_id="3",
        raw={
            "company": {
                "homepage": "https://muster-logistik.ch",
                "street": "Industriestrasse",
                "houseNumber": "35",
                "zip": "9101",
            }
        },
    )
    pipeline, store, _, _ = _pipeline(tmp_path, jobs=[job], page_fetcher=boom)
    pipeline.run_search(datetime(2026, 11, 18, 7, 30, tzinfo=timezone.utc))
    row = store.get_job("ostjob:3")
    assert row["street"] == "Industriestrasse 35"
    assert row["zip"] == "9101"


def test_ai_writes_mail_and_cover_letter(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, ai=WritingAI())
    pipeline.run_search(datetime(2026, 11, 18, 7, 30, tzinfo=timezone.utc))
    pipeline.prepare_application(MATCHING.id)
    draft = outlook.drafts[0]
    assert draft["subject"] == "Bewerbung als Speditionskaufmann"
    assert draft["to"] == "ki@muster-logistik.ch"
    assert "Ich disponiere" in draft["body"]
    pdfs = [path for path in draft["attachments"] if path.endswith(".pdf")]
    assert pdfs, draft["attachments"]
    assert Path(pdfs[0]).read_bytes().startswith(b"%PDF")
    application = store.list_applications()[0]
    assert application["subject"] == "Bewerbung als Speditionskaufmann"
    assert store.get_job("ostjob:1")["title"] == "Speditionskaufmann"


def test_second_run_does_not_duplicate(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    pipeline.run_search()
    assert len(outlook.drafts) == 1
    assert len(store.list_applications()) == 1


def test_draft_uses_known_contact_person(tmp_path) -> None:
    job = _job("1", "Speditionskaufmann", "Disposition, Transport und Zoll", ["Spedition"])
    job.contact_name = "Frau Meier"
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[job])
    pipeline.run_search()
    pipeline.prepare_application(job.id)
    body = outlook.drafts[0]["body"]
    assert body.startswith("Sehr geehrte Frau Meier")
    assert "Sehr geehrte Damen und Herren" not in body
    assert store.get_job(job.id)["contact_name"] == "Frau Meier"


def test_sent_check_marks_only_once(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"],
        created_at=(datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
    )
    outlook.sent_messages.append(
        {
            "id": "s1",
            "conversationId": application["conversation_id"],
            "internetMessageId": "<s1@example.test>",
            "sentDateTime": "2026-11-18T08:15:00+00:00",
            "subject": "Bewerbung",
            "text": "",
        }
    )
    assert pipeline.check_drafts() == 1
    assert pipeline.check_drafts() == 0
    stored = store.list_applications()[0]
    assert stored["status"] == "gesendet"
    assert stored["sent_at"].startswith("2026-11-18")


def test_reply_rejection_archives(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    store.update_application(
        store.list_applications()[0]["id"],
        status="gesendet",
        sent_at="2026-11-18T08:15:00+00:00",
    )
    outlook.messages = [
        {
            "id": "inbox1",
            "conversationId": "conv1",
            "receivedDateTime": "2026-11-18T09:00:00Z",
            "subject": "Ihre Bewerbung als Speditionskaufmann – Absage",
            "bodyPreview": "Leider eine Absage",
            "body": {"contentType": "text", "content": "Leider eine Absage."},
            "from": {"emailAddress": {"address": "hr@muster-logistik.ch"}},
        }
    ]
    found = pipeline.check_replies()
    assert len(found) == 1
    assert found[0]["kind"] == "absage"
    application = store.list_applications()[0]
    assert application["status"] == "absage"
    assert application["archived_at"]
    assert store.get_job("ostjob:1")["status"] == "archiviert"
    # Das Protokoll nennt den Weg der Zuordnung.
    assert any(
        "zugeordnet über Unterhaltung" in event["message"]
        for event in store.events()
    )

    # Dieselbe Mail wird nicht ein zweites Mal verbucht.
    assert pipeline.check_replies() == []


def test_reply_invitation_notifies(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"], status="gesendet", sent_at="2026-11-15T08:00:00+00:00"
    )
    outlook.messages = [
        {
            "id": "inbox2",
            "conversationId": "conv1",
            "receivedDateTime": "2026-11-16T09:00:00Z",
            "subject": "Einladung zum Gespräch",
            "body": {
                "contentType": "text",
                "content": "Gerne laden wir Sie zu einem Vorstellungsgespräch ein.",
            },
        }
    ]
    pipeline._ai = type(
        "AI", (), {"classify": lambda self, subject, body, sender="", context="": "einladung"}
    )()
    found = pipeline.check_replies()
    assert found and found[0]["kind"] == "einladung"
    assert store.list_applications()[0]["status"] == "einladung"


def test_follow_up_after_two_weeks_only_once(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(
        application_id,
        sent_at=(date.today() - timedelta(days=15)).isoformat(),
    )
    assert pipeline.prepare_follow_ups() == 1
    assert len(outlook.drafts) == 1
    assert "Nachfrage" in outlook.drafts[0]["subject"]
    application = store.get_application(application_id)
    assert application["status"] == "nachgefasst"
    assert application["follow_up_at"]
    assert pipeline.prepare_follow_ups() == 0


def test_manual_prepare_application(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    store.upsert_job(UNRELATED)
    application_id = pipeline.prepare_application(MATCHING.id)
    assert application_id > 0
    assert len(outlook.drafts) == 1
    with pytest.raises(ValueError):
        pipeline.prepare_application(UNRELATED.id)
    with pytest.raises(ValueError):
        pipeline.prepare_application("gibt-es-nicht")


def test_manual_follow_up(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, sent_at="2026-11-01T08:00:00+00:00")
    assert pipeline.prepare_follow_up(application_id) is True
    assert store.get_application(application_id)["follow_up_subject"]
    with pytest.raises(ValueError):
        pipeline.prepare_follow_up(9999)


def test_imap_provider_uses_imap_client(tmp_path) -> None:
    imap = FakeOutlook()
    pipeline, store, outlook, settings = _pipeline(tmp_path, imap=imap)
    settings.set("mail.provider", "imap")
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    assert len(imap.drafts) == 1
    assert len(outlook.drafts) == 0


def test_every_application_gets_a_tracking_code(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    code = application["tracking"]
    assert code.startswith("AA-") and len(code) == 17
    assert outlook.drafts[0]["tracking"] == code
    assert store.application_by_tracking(code)["id"] == application["id"]


def test_reply_is_matched_by_tracking_code(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    code = application["tracking"]
    store.update_application(
        application["id"],
        status="gesendet",
        sent_at="2026-11-18T08:15:00+00:00",
    )
    # Betreff und Absender passen zu keiner Bewerbung - nur die Kennung tut es.
    outlook.messages = [
        {
            "id": "inbox9",
            "conversationId": "",
            "receivedDateTime": "2026-11-18T09:00:00Z",
            "subject": "Rückfrage zu Ihrer Nachricht",
            "body": {
                "contentType": "Text",
                "content": "Leider eine Absage.\n\n> AutoApplication-Referenz " + code,
            },
        }
    ]
    found = pipeline.check_replies()
    assert len(found) == 1
    assert found[0]["application"]["id"] == application["id"]
    assert any(
        f"zugeordnet über Kennung {code}" in event["message"]
        for event in store.events()
    )


def test_follow_up_reuses_tracking_code(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(
        application_id,
        sent_at=(date.today() - timedelta(days=15)).isoformat(),
        tracking="AA-7K4P-Q9XM-3TRZ",
    )
    assert pipeline.prepare_follow_ups() == 1
    assert outlook.drafts[0]["tracking"] == "AA-7K4P-Q9XM-3TRZ"


def test_ai_greeting_is_replaced_with_contact(tmp_path) -> None:
    job = _job("1", "Speditionskaufmann", "Disposition, Transport und Zoll", ["Spedition"])
    job.contact_name = "Herr Müller"

    class NamedAI(WritingAI):
        def job_digest(self, job):
            digest = local_digest(job)
            digest.contact_name = "Herr Müller"
            return digest

    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[job], ai=NamedAI())
    pipeline.run_search()
    pipeline.prepare_application(job.id)
    body = outlook.drafts[0]["body"]
    assert body.startswith("Sehr geehrter Herr Müller")
    assert "Sehr geehrte Damen und Herren" not in body


def test_info_reply_sets_answer_status(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"], status="gesendet", sent_at="2026-11-16T08:00:00+00:00"
    )
    outlook.messages = [
        {
            "id": "inbox-info",
            "conversationId": "conv1",
            "receivedDateTime": "2026-11-18T09:00:00Z",
            "subject": "Ihre Unterlagen sind eingegangen",
            "body": {
                "contentType": "text",
                "content": "Wir prüfen Ihre Unterlagen und melden uns.",
            },
        }
    ]
    found = pipeline.check_replies()
    assert found and found[0]["kind"] == "info"
    assert store.get_application(application["id"])["status"] == "info"
    # Genau diese Bewerbung zeigt der Filter «Antwort».
    filtered = store.list_applications(statuses=["info"])
    assert [row["id"] for row in filtered] == [application["id"]]


def test_info_reply_keeps_stronger_status(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"], status="einladung", sent_at="2026-11-16T08:00:00+00:00"
    )
    outlook.messages = [
        {
            "id": "inbox-info2",
            "conversationId": "conv1",
            "receivedDateTime": "2026-11-18T09:00:00Z",
            "subject": "Willkommen im Team",
            "body": {"contentType": "text", "content": "Wir freuen uns auf Sie."},
        }
    ]
    found = pipeline.check_replies()
    assert found and found[0]["kind"] == "info"
    # Eine Einladung wird durch eine blosse Antwort nicht zurückgestuft.
    assert store.get_application(application["id"])["status"] == "einladung"


def test_draft_preview_creates_nothing(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    preview = pipeline.draft_preview(MATCHING.id)
    assert preview["email"] == "bewerbung@muster-logistik.ch"
    assert preview["salutation"]
    assert preview["subject"] and preview["body"]
    # Noch kein Entwurf und noch keine Bewerbung.
    assert store.list_applications() == []
    assert outlook.drafts == []


def test_create_draft_uses_edited_text(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.draft_preview(MATCHING.id)
    application_id = pipeline.create_draft(
        MATCHING.id,
        email="personal@muster-logistik.ch",
        subject="Bewerbung als Speditionskaufmann",
        body="Sehr geehrte Frau Meier,\n\nangepasster Text.",
    )
    assert application_id > 0
    draft = outlook.drafts[0]
    assert draft["to"] == "personal@muster-logistik.ch"
    assert draft["subject"] == "Bewerbung als Speditionskaufmann"
    assert "angepasster Text" in draft["body"]
    stored = store.get_application(application_id)
    assert stored["body"].startswith("Sehr geehrte Frau Meier")


def test_proofread_uses_the_ai(tmp_path) -> None:
    class CorrectingAI(FakeAI):
        def proofread(self, text: str) -> str:
            return text.replace("Sehr geehrte", "Sehr geehrte")

    pipeline, _store, _outlook, _ = _pipeline(tmp_path, ai=CorrectingAI())
    assert pipeline.proofread_available() is True
    assert pipeline.proofread("Hallo Welt") == "Hallo Welt"


def test_proofread_without_ai_keeps_the_text(tmp_path) -> None:
    pipeline, _store, _outlook, _ = _pipeline(tmp_path)
    assert pipeline.proofread_available() is False
    assert pipeline.proofread("Hallo Welt") == "Hallo Welt"


def test_proofread_failure_keeps_the_text(tmp_path) -> None:
    class BrokenAI(FakeAI):
        def proofread(self, text: str) -> str:
            raise RuntimeError("kein Netz")

    pipeline, _store, _outlook, _ = _pipeline(tmp_path, ai=BrokenAI())
    assert pipeline.proofread("Hallo Welt") == "Hallo Welt"


def test_vanished_draft_alone_is_not_sent(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"],
        created_at=(datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
    )
    assert application["status"] == "entwurf"
    # Der Entwurf verschwindet, liegt aber nicht in «Gesendet»: bleibt Entwurf.
    outlook.drafts.clear()
    assert pipeline.check_drafts() == 0
    assert store.get_application(application["id"])["status"] == "entwurf"
    assert not any(event["message"].startswith("Bewerbung an") for event in store.events())


def test_sent_folder_marks_application_sent(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"],
        created_at=(datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
    )
    outlook.drafts.clear()
    # Erst die Mail im Ordner «Gesendet» zählt als Versand.
    outlook.sent_messages.append(
        {
            "id": "s1",
            "conversationId": application["conversation_id"],
            "internetMessageId": "<m1@example.test>",
            "sentDateTime": "2026-11-19T07:36:00+00:00",
            "subject": "Bewerbung",
            "text": f"Kennung {application['tracking']}",
        }
    )
    assert pipeline.check_drafts() == 1
    stored = store.get_application(application["id"])
    assert stored["status"] == "gesendet"
    assert stored["sent_at"] == "2026-11-19T07:36:00+00:00"
    assert stored["internet_message_id"] == "<m1@example.test>"
    assert outlook.sent_limit == 100
    assert any("Gesendet" in event["message"] for event in store.events())


def test_draft_check_needs_a_tracking_code(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    store.add_application(MATCHING.id, "spedition", "Betreff", "Text", status="entwurf")
    # Ohne Kennung bleibt der Eintrag unangetastet (kein Fehlalarm).
    assert pipeline.check_drafts() == 0
    assert store.list_applications()[0]["status"] == "entwurf"


def test_fresh_draft_is_not_checked_yet(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    # Gerade angelegt: der Entwurf wird beim ersten Lauf noch nicht geprüft.
    outlook.drafts.clear()
    assert pipeline.check_drafts() == 0
    assert store.list_applications()[0]["status"] == "entwurf"


def test_reply_goes_to_the_ai_with_text_and_job(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"],
        status="gesendet",
        sent_at="2026-11-15T08:00:00+00:00",
    )
    body = (
        "Gerne laden wir Sie zu einem Vorstellungsgespräch ein. Passt Ihnen "
        "Dienstag, 24. November, um 14 Uhr?"
    )
    outlook.messages = [
        {
            "id": "inbox9",
            "conversationId": "conv1",
            "receivedDateTime": "2026-11-16T09:00:00Z",
            "subject": "Ihre Bewerbung",
            "body": {"contentType": "text", "content": body},
        }
    ]
    seen: dict[str, str] = {}

    class CapturingAI:
        def classify(self, subject, body, sender="", context=""):
            seen.update(subject=subject, body=body, sender=sender, context=context)
            return "einladung"

    pipeline._ai = CapturingAI()
    found = pipeline.check_replies()
    assert found and found[0]["kind"] == "einladung"
    assert body in seen["body"]
    assert "Speditionskaufmann" in seen["context"]
    assert store.list_applications()[0]["status"] == "einladung"


def test_reply_is_stored_with_its_whole_text(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application = store.list_applications()[0]
    store.update_application(
        application["id"], status="gesendet", sent_at="2026-11-15T08:00:00+00:00"
    )
    body = "Guten Tag\n\nGerne laden wir Sie zu einem Vorstellungsgespräch ein.\n" + "Zeile\n" * 200
    outlook.messages = [
        {
            "id": "inbox10",
            "conversationId": "conv1",
            "receivedDateTime": "2026-11-16T09:00:00Z",
            "subject": "Einladung",
            "body": {"contentType": "text", "content": body},
        }
    ]
    pipeline._ai = type(
        "AI", (), {"classify": lambda self, subject, body, sender="", context="": "einladung"}
    )()
    assert pipeline.check_replies()
    replies = store.replies_for(int(application["id"]))
    assert len(replies) == 1
    assert replies[0]["body"] == body
    assert replies[0]["seen"] == 0


def test_follow_up_preview_creates_nothing(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, sent_at="2026-11-01T08:00:00+00:00")
    preview = pipeline.follow_up_preview(application_id)
    assert outlook.drafts == []
    assert store.get_application(application_id)["status"] == "gesendet"
    assert "Nachfrage" in preview["subject"]
    assert preview["body"].strip()
    assert preview["salutation"].startswith("Sehr geehrte")
    assert preview["email"] == "bewerbung@muster-logistik.ch"
    assert preview["company"] == "Muster Logistik AG"
    assert preview["title"] == "Speditionskaufmann"


def test_follow_up_draft_takes_the_edited_values(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, sent_at="2026-11-01T08:00:00+00:00")
    pipeline.follow_up_preview(application_id)
    subject = "Nachfrage zu meiner Bewerbung als Speditionskaufmann"
    body = "Sehr geehrte Damen und Herren,\n\nich frage nach dem Stand meiner Bewerbung."
    assert pipeline.create_follow_up_draft(
        application_id, email="neu@muster-logistik.ch", subject=subject, body=body
    )
    draft = outlook.drafts[0]
    assert draft["to"] == "neu@muster-logistik.ch"
    assert draft["subject"] == subject
    assert draft["body"] == body
    application = store.get_application(application_id)
    assert application["status"] == "nachgefasst"
    assert application["follow_up_subject"] == subject
    assert application["follow_up_body"] == body
    assert draft["tracking"] == application["tracking"]
    assert store.get_application(application_id)["follow_up_at"]


def test_follow_up_without_preview_still_works(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, sent_at="2026-11-01T08:00:00+00:00")
    assert pipeline.create_follow_up_draft(application_id)
    assert len(outlook.drafts) == 1
    assert outlook.drafts[0]["to"] == "bewerbung@muster-logistik.ch"
    assert store.get_application(application_id)["status"] == "nachgefasst"


def test_check_drafts_marks_follow_up_as_sent(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, sent_at="2026-11-01T08:00:00+00:00")
    pipeline.prepare_follow_up(application_id)
    assert outlook.drafts
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(
        timespec="seconds"
    )
    store.update_application(application_id, follow_up_at=old)

    # Entwurf liegt noch im Ordner: nichts vermerken.
    assert pipeline.check_drafts() == 0
    assert not store.get_application(application_id)["follow_up_sent_at"]

    # Der verschwundene Entwurf allein genügt nicht.
    outlook.drafts.clear()
    assert pipeline.check_drafts() == 0
    application = store.get_application(application_id)
    assert not application["follow_up_sent_at"]

    # Die alte Bewerbungsmail trägt dieselbe Kennung, ist aber zu früh.
    outlook.sent_messages.append(
        {
            "id": "alt",
            "conversationId": application["conversation_id"],
            "internetMessageId": "<alt@example.test>",
            "sentDateTime": "2026-11-01T08:00:00+00:00",
            "subject": "Bewerbung",
            "text": f"Kennung {application['tracking']}",
        }
    )
    assert pipeline.check_drafts() == 0

    # Erst die Nachfrage selbst im Ordner «Gesendet» zählt.
    sent_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
    outlook.sent_messages.append(
        {
            "id": "f1",
            "conversationId": application["follow_up_conversation_id"],
            "internetMessageId": "<f1@example.test>",
            "sentDateTime": sent_time,
            "subject": "Nachfrage",
            "text": "",
        }
    )
    assert pipeline.check_drafts() == 1
    application = store.get_application(application_id)
    assert application["follow_up_sent_at"] == sent_time
    assert application["status"] == "nachgefasst"
    assert pipeline.check_drafts() == 0
    messages = [entry["message"] for entry in store.events()]
    assert any("Nachfrage" in text and "Gesendet" in text for text in messages)


def test_check_drafts_ignores_follow_up_shortly_after_preparation(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path, jobs=[])
    store.upsert_job(MATCHING)
    application_id = store.add_application(
        MATCHING.id, "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, sent_at="2026-11-01T08:00:00+00:00")
    pipeline.prepare_follow_up(application_id)
    outlook.drafts.clear()
    # Gerade eben angelegt - Karenzzeit gilt auch fuer Nachfragen.
    assert pipeline.check_drafts() == 0
    assert not store.get_application(application_id)["follow_up_sent_at"]


def test_draft_preview_shows_letter_address(tmp_path) -> None:
    pages = {
        "https://muster-logistik.ch": (
            "<html><body><p>Muster Logistik AG</p>"
            "<p>Bahnhofstrasse 12</p><p>9436 Balgach</p></body></html>"
        )
    }
    pipeline, _, _, _ = _pipeline(
        tmp_path, page_fetcher=lambda url: pages.get(url.rstrip("/"), "")
    )
    pipeline.run_search()
    preview = pipeline.draft_preview(MATCHING.id)
    assert preview["address"] == (
        "Muster Logistik AG\nBahnhofstrasse 12\n9436 Balgach"
    )


def test_draft_preview_warns_about_template_without_address(tmp_path) -> None:
    pages = {
        "https://muster-logistik.ch": (
            "<p>Muster Logistik AG</p><p>Bahnhofstrasse 12</p><p>9436 Balgach</p>"
        )
    }
    template = tmp_path / "alt.txt"
    template.write_text("{firma}\n{ort}\n\n{text}\n\nFreundliche Grüsse\n", encoding="utf-8")
    pipeline, _, _, settings = _pipeline(
        tmp_path, page_fetcher=lambda url: pages.get(url.rstrip("/"), "")
    )
    settings.set("documents.letter_template", str(template))
    pipeline.run_search()
    preview = pipeline.draft_preview(MATCHING.id)
    assert preview["warnings"], "Vorlage ohne Adress-Platzhalter muss gemeldet werden"
    assert "Strasse" in preview["warnings"][0]

    # Mit der eingebauten Standardvorlage gibt es nichts zu melden.
    settings.set("documents.letter_template", "")
    assert pipeline.draft_preview(MATCHING.id)["warnings"] == []


class NoAddressAI(FakeAI):
    """KI, die keine Firmenadresse liefern darf."""

    def company_address(self, *args, **kwargs):
        raise AssertionError("Die KI darf keine Firmenadresse liefern")


def test_address_never_comes_from_the_ai(tmp_path) -> None:
    pipeline, store, _, _ = _pipeline(
        tmp_path,
        ai=NoAddressAI(),
        page_fetcher=lambda url: "<p>Muster Logistik AG</p><p>Willkommen</p>",
    )
    pipeline.run_search()
    row = store.get_job("ostjob:1")
    # Ohne klare Angabe im Portal oder Seitentext bleibt die Adresse leer.
    assert row["street"] == ""
    assert row["zip"] == ""
    preview = pipeline.draft_preview("ostjob:1")
    assert preview["address"] == "Muster Logistik AG\nBalgach"


def test_reply_can_be_classified_by_hand(tmp_path) -> None:
    pipeline, store, _outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    application_id = int(store.list_applications()[0]["id"])
    store.update_application(application_id, status="info", reply_kind="info")
    store.add_reply(
        application_id, "m1", "2026-11-16T09:00:00Z", "hr@muster.ch",
        "Ihre Bewerbung", "info", "Kurz", body="Guten Tag",
    )

    pipeline.set_reply_kind(application_id, "einladung")
    row = store.get_application(application_id)
    assert row["status"] == "einladung"
    assert row["reply_kind"] == "einladung"
    assert store.replies_for(application_id)[-1]["kind"] == "einladung"

    pipeline.set_reply_kind(application_id, "absage")
    row = store.get_application(application_id)
    assert row["status"] == "absage"
    assert row["archived_at"]

    # Eine Absage laesst sich korrigieren: die Bewerbung ist wieder aktiv.
    pipeline.set_reply_kind(application_id, "zusage")
    row = store.get_application(application_id)
    assert row["status"] == "zusage"
    assert row["archived_at"] == ""
    assert store.replies_for(application_id)[-1]["kind"] == "zusage"
    assert any("von Hand eingeordnet" in event["message"] for event in store.events())


def test_search_completes_contact_data_right_away(tmp_path) -> None:
    page = "Muster Logistik AG, Bahnhofstrasse 12, 9436 Balgach"
    pipeline, store, _outlook, _ = _pipeline(
        tmp_path, jobs=[UNRELATED], page_fetcher=lambda url: page
    )
    # Ein alter Datensatz, der bei dieser Suche nicht geliefert wird.
    old = Job(
        id="ostjob:alt",
        source="ostjob",
        source_id="alt",
        title="Lagerist",
        company="Muster Logistik AG",
        city="Balgach",
        raw={"company": {"homepage": "https://muster-logistik.ch"}},
    )
    store.upsert_job(old, now="2026-11-01T08:00:00+00:00")
    pipeline.run_search()

    # Auch ohne passende Vorlage ist die Adresse der gefundenen Stelle da.
    fetched = store.get_job(UNRELATED.id)
    assert fetched["street"] == "Bahnhofstrasse 12"
    assert fetched["zip"] == "9436"

    # Der alte, unvollstaendige Datensatz wurde mit nachgezogen.
    stored = store.get_job("ostjob:alt")
    assert stored["street"] == "Bahnhofstrasse 12"
    assert stored["zip"] == "9436"


def test_only_complete_rows_are_skipped(tmp_path) -> None:
    urls: list[str] = []

    def fetch(url: str) -> str:
        urls.append(url)
        return "Muster Logistik AG, Bahnhofstrasse 12, 9436 Balgach"

    pipeline, store, _outlook, _ = _pipeline(tmp_path, jobs=[], page_fetcher=fetch)
    complete = Job(
        id="ostjob:komplett",
        source="ostjob",
        source_id="komplett",
        title="Komplett",
        company="Muster AG",
        city="Balgach",
        street="Bahnhofstrasse 12",
        zip="9436",
        contact_email="hr@muster.ch",
        contact_name="Frau Meier",
        published="2026-11-19",
        raw={"company": {"homepage": "https://komplett.ch"}},
    )
    store.upsert_job(complete, now="2026-11-19T08:00:00+00:00")
    incomplete = Job(
        id="ostjob:offen",
        source="ostjob",
        source_id="offen",
        title="Offen",
        company="Nirgends AG",
        city="Balgach",
        published="2026-11-01",
        raw={"company": {"homepage": "https://nirgends.ch"}},
    )
    store.upsert_job(incomplete, now="2026-11-01T08:00:00+00:00")

    assert pipeline._complete_stored_jobs(set(), limit=1) == 1
    # Die vollstaendige Zeile kostet kein Netz; die offene wurde gesucht.
    assert not any("komplett" in url for url in urls)
    assert any("nirgends" in url for url in urls)
    assert store.get_job("ostjob:komplett")["contact_tried_at"] == ""
    assert store.get_job("ostjob:offen")["contact_tried_at"]


EXPIRED_PAGE = (
    "<html><body><p>Das gesuchte Inserat ist abgelaufen oder wurde "
    "deaktiviert. Unten findest du ähnliche Jobs, die für dich von "
    "Interesse sein könnten.</p>"
    "<p>Frau Meier, meier@beispiel.ch, Bahnhofstrasse 12, 9436 Balgach</p>"
    "</body></html>"
)


def _expired_job() -> Job:
    return Job(
        id="ostjob:1130000",
        source="ostjob",
        source_id="1130000",
        title="Speditionskaufmann",
        company="Muster AG",
        city="Balgach",
        url="https://www.ostjob.ch/job/alt/1130000",
    )


def test_expired_advert_is_removed_from_the_store(tmp_path) -> None:
    pipeline, store, _outlook, _ = _pipeline(
        tmp_path, jobs=[], page_fetcher=lambda url: EXPIRED_PAGE
    )
    store.upsert_job(_expired_job(), now="2026-11-01T08:00:00+00:00")

    assert pipeline.complete_job("ostjob:1130000") is False
    assert store.get_job("ostjob:1130000") is None


def test_expired_advert_leaves_an_application_alone(tmp_path) -> None:
    pipeline, store, _outlook, _ = _pipeline(
        tmp_path, jobs=[], page_fetcher=lambda url: EXPIRED_PAGE
    )
    job = _expired_job()
    store.upsert_job(job, now="2026-11-01T08:00:00+00:00")
    store.add_application(job.id, "spedition", "Betreff", "Text")

    pipeline.complete_job("ostjob:1130000")
    # An der Stelle haengt die Bewerbung; sie bleibt erhalten.
    assert store.get_job("ostjob:1130000") is not None


def test_expired_advert_during_search_is_skipped(tmp_path) -> None:
    job = Job(
        id="ostjob:2",
        source="ostjob",
        source_id="2",
        title="Buchhalter Treuhand",
        company="Muster AG",
        city="Balgach",
        description="Belege und Jahresabschluss",
        keywords=["Buchhaltung"],
        url="https://www.ostjob.ch/job/alt/2",
    )
    pipeline, store, _outlook, _ = _pipeline(
        tmp_path, jobs=[job], page_fetcher=lambda url: EXPIRED_PAGE
    )

    summary = pipeline.run_search()
    assert summary.found == 1
    assert store.get_job("ostjob:2") is None
