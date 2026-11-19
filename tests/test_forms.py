from __future__ import annotations

from autoapplication.core.config import Settings
from autoapplication.core.models import Job
from autoapplication.core.pipeline import Pipeline, has_application_form
from autoapplication.core.store import Store


def _job(**overrides) -> Job:
    values: dict = {
        "id": "ostjob:1",
        "source": "ostjob",
        "source_id": "1",
        "title": "Speditionskaufmann",
        "company": "Muster AG",
        "city": "Balgach",
        "published": "2026-11-18",
        "url": "https://www.ostjob.ch/job/speditionskaufmann/1",
        "raw": {"urlApplication": "https://jobs.example/apply/1"},
    }
    values.update(overrides)
    return Job(**values)


def _pipeline(tmp_path, pages: dict[str, str]) -> tuple[Pipeline, Store, list[str]]:
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return pages.get(url, "")

    pipeline = Pipeline(
        settings,
        store,
        page_fetcher=fetch,
        templates_file=tmp_path / "vorlagen.json",
    )
    return pipeline, store, calls


def test_form_with_fields_and_upload_is_detected() -> None:
    html = """
    <form action="/apply" method="post">
      <input type="text" name="name">
      <input type="email" name="email">
      <textarea name="text"></textarea>
      <input type="file" name="cv">
      <p>Bewerbung</p>
    </form>
    """
    assert has_application_form(html)


def test_text_form_with_application_words_is_detected() -> None:
    html = """
    <form>
      <textarea name="message"></textarea>
      <input type="text" name="vorname">
      <input type="text" name="nachname">
      <span>Bewerbung</span>
    </form>
    """
    assert has_application_form(html)


def test_job_page_search_mask_is_not_a_form() -> None:
    html = """
    <form>
      <input type="text" name="search">
      <input type="text" name="place">
      <input type="text" name="type">
    </form>
    """
    assert not has_application_form(html)


def test_login_form_is_not_an_application_form() -> None:
    html = """
    <form>
      <input type="email" name="user">
      <input type="password" name="pw">
      <button>Anmelden</button>
    </form>
    """
    assert not has_application_form(html)


def test_pipeline_marks_job_with_application_form(tmp_path) -> None:
    job = _job()
    pages = {
        "https://jobs.example/apply/1": (
            '<form><textarea name="text"></textarea>'
            '<input type="text" name="name">'
            '<input type="email" name="email">'
            "<p>Bewerbung</p></form>"
        )
    }
    pipeline, store, calls = _pipeline(tmp_path, pages)
    store.upsert_job(job)

    assert pipeline._mark_form(Job.from_row(store.get_job(job.id)))
    row = store.get_job(job.id)
    assert row["has_form"] == 1
    assert row["form_checked"] == 1
    assert Job.from_row(row).has_form is True
    assert calls == ["https://jobs.example/apply/1"]


def test_mailto_application_needs_no_page(tmp_path) -> None:
    job = _job(raw={"urlApplication": "mailto:personal@muster.ch"})
    pipeline, store, calls = _pipeline(tmp_path, {})
    store.upsert_job(job)

    assert pipeline._mark_form(Job.from_row(store.get_job(job.id)))
    row = store.get_job(job.id)
    assert row["has_form"] == 0
    assert row["form_checked"] == 1
    assert calls == []


def test_unreachable_application_page_is_checked_later(tmp_path) -> None:
    job = _job()
    pipeline, store, _calls = _pipeline(tmp_path, {})
    store.upsert_job(job)

    assert pipeline._mark_form(Job.from_row(store.get_job(job.id))) is False
    row = store.get_job(job.id)
    assert row["has_form"] == 0
    assert row["form_checked"] == 0
