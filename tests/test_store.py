from __future__ import annotations

from datetime import date, timedelta

from autoapplication.core.models import Job
from autoapplication.core.store import Store
from autoapplication.core.text import now_iso


def _job(identifier: str = "1") -> Job:
    return Job(
        id=f"ostjob:{identifier}",
        source="ostjob",
        source_id=identifier,
        title="Speditionskaufmann",
        company="Muster AG",
        city="Balgach",
        workload="100 %",
        published="2026-11-01",
        description="Disposition",
        keywords=["Spedition", "Disposition"],
    )


def test_upsert_job_only_new_once(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    assert store.upsert_job(_job(), now=now_iso()) is True
    assert store.upsert_job(_job(), now=now_iso()) is False
    rows = store.list_jobs()
    assert len(rows) == 1
    assert rows[0]["status"] == "neu"


def test_job_analysis_and_status(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.upsert_job(_job(), now=now_iso())
    store.set_job_analysis("ostjob:1", 3, "spedition", ["Spedition", "Disposition"])
    store.update_job("ostjob:1", status="beworben")
    row = store.get_job("ostjob:1")
    assert row["score"] == 3
    assert row["template_id"] == "spedition"
    assert "Disposition" in row["keywords"]
    assert row["status"] == "beworben"
    assert store.job_counts()["beworben"] == 1


def test_application_lifecycle(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.upsert_job(_job(), now=now_iso())
    app_id = store.add_application(
        "ostjob:1", "spedition", "Betreff", "Text", status="entwurf", created_at=now_iso()
    )
    application = store.get_application(app_id)
    assert application["company"] == "Muster AG"
    assert store.application_by_job("ostjob:1")["id"] == app_id

    store.update_application(app_id, status="gesendet", sent_at="2026-11-05T08:00:00+00:00")
    assert store.list_applications(status="gesendet")
    assert store.application_counts()["gesendet"] == 1
    assert store.active_applications()[0]["title"] == "Speditionskaufmann"

    store.update_application(app_id, status="absage", archived_at=now_iso())
    assert store.application_counts()["absage"] == 1
    assert store.active_applications() == []


def test_application_tracking_code(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.upsert_job(_job(), now=now_iso())
    app_id = store.add_application(
        "ostjob:1", "spedition", "B", "T", tracking="AA-7K4P-Q9XM-3TRZ"
    )
    assert store.get_application(app_id)["tracking"] == "AA-7K4P-Q9XM-3TRZ"
    assert store.application_by_tracking("AA-7K4P-Q9XM-3TRZ")["id"] == app_id
    assert store.application_by_tracking("AA-ZZZZ-ZZZZ-ZZZZ") is None
    # Ohne Kennung darf keine alte Bewerbung ohne Kennung herausfallen.
    assert store.application_by_tracking("") is None


def test_list_applications_filters_several_statuses(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.upsert_job(_job(), now=now_iso())
    sent = store.add_application(
        "ostjob:1", "spedition", "A", "Text", status="gesendet"
    )
    rejected = store.add_application(
        "ostjob:1", "spedition", "B", "Text", status="absage"
    )
    store.add_application("ostjob:1", "spedition", "C", "Text", status="entwurf")

    combined = store.list_applications(statuses=["gesendet", "absage"])
    assert {row["id"] for row in combined} == {sent, rejected}
    assert [row["id"] for row in store.list_applications(statuses=["absage"])] == [
        rejected
    ]
    # Ohne Häkchen bleibt die ganze Liste stehen.
    assert len(store.list_applications(statuses=[])) == 3
    assert len(store.list_applications()) == 3


def test_due_follow_ups_after_two_weeks(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.upsert_job(_job(), now=now_iso())
    app_id = store.add_application("ostjob:1", "spedition", "Betreff", "Text")
    recent = date.today() - timedelta(days=5)
    store.update_application(app_id, status="gesendet", sent_at=recent.isoformat())
    assert store.due_follow_ups(14) == []

    old = date.today() - timedelta(days=15)
    store.update_application(app_id, sent_at=old.isoformat())
    due = store.due_follow_ups(14)
    assert len(due) == 1

    store.update_application(app_id, status="nachgefasst", follow_up_at=now_iso())
    assert store.due_follow_ups(14) == []


def test_replies_are_deduplicated(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.upsert_job(_job(), now=now_iso())
    app_id = store.add_application("ostjob:1", "spedition", "Betreff", "Text")
    assert store.add_reply(app_id, "m1", now_iso(), "hr@muster.ch", "Absage", "absage", "…")
    assert not store.add_reply(app_id, "m1", now_iso(), "hr@muster.ch", "Absage", "absage", "…")
    assert len(store.replies_for(app_id)) == 1


def test_meta_and_events(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    store.meta_set("letzter_lauf", "2026-11-18T07:30:00+00:00")
    assert store.meta_get("letzter_lauf").startswith("2026-11-18")
    store.log("lauf", "Test")
    assert store.events()[0]["message"] == "Test"


def test_old_info_replies_get_the_answer_status(tmp_path) -> None:
    path = tmp_path / "daten.db"
    store = Store(path)
    store.upsert_job(_job())
    application_id = store.add_application(
        "ostjob:1", "spedition", "Betreff", "Text", status="gesendet"
    )
    store.update_application(application_id, reply_kind="info")
    # Ablage erneut oeffnen: die Migration zieht den Status nach.
    reopened = Store(path)
    assert reopened.get_application(application_id)["status"] == "info"
    assert [row["id"] for row in reopened.list_applications(statuses=["info"])] == [
        application_id
    ]


def test_replies_store_the_whole_mail_and_stay_unread_until_opened(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    job = Job(id="ostjob:1", source="ostjob", source_id="1", title="T", company="C")
    store.upsert_job(job)
    application_id = store.add_application(job.id, "spedition", "Betreff", "Text")
    long_body = "Zeile\n" * 400
    assert store.add_reply(
        application_id, "m1", "2026-11-18T09:00:00Z", "hr@firma.ch",
        "Einladung", "einladung", "kurz", body=long_body,
    )
    replies = store.replies_for(application_id)
    assert replies[0]["body"] == long_body
    assert replies[0]["seen"] == 0
    assert store.unseen_by_application() == {application_id: 1}
    assert store.reply_counts() == {application_id: 1}

    assert store.mark_replies_seen(application_id) == 1
    assert store.unseen_by_application() == {}
    assert store.replies_for(application_id)[0]["seen"] == 1
    # Zweite Mail kommt an: wieder ungelesen.
    assert store.add_reply(
        application_id, "m2", "2026-11-19T09:00:00Z", "hr@firma.ch",
        "Absage", "absage", "kurz", body="Leider abgesagt.",
    )
    assert store.unseen_by_application() == {application_id: 1}
    assert store.reply_counts() == {application_id: 2}


def test_unseen_total_counts_only_unread_replies(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    job = Job(id="ostjob:1", source="ostjob", source_id="1", title="T", company="C")
    store.upsert_job(job)
    first = store.add_application(job.id, "spedition", "Betreff", "Text")
    second = store.add_application(job.id, "lager", "Betreff", "Text")
    store.add_reply(first, "m1", "2026-11-18T09:00:00Z", "a@firma.ch", "Antwort", "info", "")
    store.add_reply(second, "m2", "2026-11-18T10:00:00Z", "b@firma.ch", "Antwort", "info", "")
    store.add_reply(second, "m3", "2026-11-18T11:00:00Z", "b@firma.ch", "Antwort", "info", "")
    assert store.unseen_total() == 3
    store.mark_replies_seen(first)
    assert store.unseen_total() == 2
    store.mark_replies_seen(second)
    assert store.unseen_total() == 0


def test_job_stores_street_postcode_and_email(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    job = Job(
        id="ostjob:9",
        source="ostjob",
        source_id="9",
        title="Speditionskaufmann",
        company="Muster AG",
        city="Balgach",
        zip="9436",
        street="Bahnhofstrasse 12",
        contact_email="bewerbung@muster.ch",
        contact_name="Frau Meier",
    )
    assert store.upsert_job(job) is True
    row = store.get_job(job.id)
    assert row["street"] == "Bahnhofstrasse 12"
    assert row["zip"] == "9436"
    assert row["contact_email"] == "bewerbung@muster.ch"
    assert row["contact_name"] == "Frau Meier"
    # Adresse laesst sich nachtragen und in der Suche finden.
    store.update_job(job.id, street="Neue Strasse 7")
    assert store.get_job(job.id)["street"] == "Neue Strasse 7"
    assert [item["id"] for item in store.list_jobs(search="Neue Strasse")] == [job.id]
    assert [item["id"] for item in store.list_jobs(search="9436")] == [job.id]


def test_only_unclassified_unread_replies_need_attention(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    job = Job(id="ostjob:1", source="ostjob", source_id="1", title="T", company="C")
    store.upsert_job(job)
    application_id = store.add_application(job.id, "spedition", "Betreff", "Text")
    store.add_reply(
        application_id, "m1", "2026-11-18T09:00:00Z", "hr@firma.ch",
        "Ihre Bewerbung", "info", "kurz",
    )
    store.add_reply(
        application_id, "m2", "2026-11-18T10:00:00Z", "hr@firma.ch",
        "Absage", "absage", "kurz",
    )
    # Nur die unklare Antwort blinkt, die Absage ist bereits zugeordnet.
    assert store.unclassified_by_application() == {application_id: 1}
    # Angeschaut: das Blinken hoert auf.
    store.mark_replies_seen(application_id)
    assert store.unclassified_by_application() == {}
    assert store.unseen_total() == 0


def test_latest_reply_can_be_classified_afterwards(tmp_path) -> None:
    store = Store(tmp_path / "daten.db")
    job = Job(id="ostjob:1", source="ostjob", source_id="1", title="T", company="C")
    store.upsert_job(job)
    application_id = store.add_application(job.id, "spedition", "Betreff", "Text")
    store.add_reply(
        application_id, "m1", "2026-11-18T09:00:00Z", "hr@firma.ch",
        "Ihre Bewerbung", "info", "kurz",
    )
    assert store.set_reply_kind(application_id, "zusage") is True
    replies = store.replies_for(application_id)
    assert replies[-1]["kind"] == "zusage"
    # Zugeordnet heisst: kein Blinken mehr, auch wenn die Mail ungelesen ist.
    assert store.unclassified_by_application() == {}
    assert store.unseen_total() == 1
