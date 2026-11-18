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

    def classify(self, subject: str, body: str, sender: str = "") -> str:
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
        self.sent: dict | None = None
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

    def find_sent(self, conversation_id: str):
        return self.sent

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


def test_sync_sent_marks_application(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    outlook.sent = {"id": "s1", "sentDateTime": "2026-11-18T08:15:00Z"}
    assert pipeline.sync_sent() == 1
    application = store.list_applications()[0]
    assert application["status"] == "gesendet"
    assert application["sent_at"].startswith("2026-11-18")
    assert outlook.sent is not None  # bleibt gesetzt, zweiter Lauf findet nichts Neues
    assert pipeline.sync_sent() == 0


def test_reply_rejection_archives(tmp_path) -> None:
    pipeline, store, outlook, _ = _pipeline(tmp_path)
    pipeline.run_search()
    pipeline.prepare_application(MATCHING.id)
    outlook.sent = {"sentDateTime": "2026-11-18T08:15:00+00:00"}
    pipeline.sync_sent()
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
        "AI", (), {"classify": lambda self, subject, body, sender="": "einladung"}
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
    outlook.sent = {"sentDateTime": "2026-11-18T08:15:00+00:00"}
    pipeline.sync_sent()
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
