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
