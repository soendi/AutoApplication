from __future__ import annotations

from autoapplication.core import ocr, text
from autoapplication.core.ai import local_digest
from autoapplication.core.config import Settings
from autoapplication.core.models import Job
from autoapplication.core.pipeline import Pipeline
from autoapplication.core.store import Store


class FakeAI:
    def keywords(self, job: Job, vocabulary: list[str]) -> list[str]:
        return list(job.keywords)

    def job_digest(self, job: Job):
        return local_digest(job)


def _image_job(**overrides) -> Job:
    values: dict = {
        "id": "ostjob:77",
        "source": "ostjob",
        "source_id": "77",
        "title": "Speditionskaufmann",
        "company": "Muster Logistik AG",
        "city": "Balgach",
        "published": "2026-11-18",
        "description": "Disposition, Transport und Zoll",
        "keywords": ["Spedition"],
        "url": "https://www.ostjob.ch/job/speditionskaufmann/77",
        "raw": {"contact": '<img src="https://cdn.example/kontakt.png">'},
    }
    values.update(overrides)
    return Job(**values)


def _pipeline(tmp_path, job: Job) -> tuple[Pipeline, Store]:
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    store.upsert_job(job)
    pipeline = Pipeline(
        settings,
        store,
        ai_client=FakeAI(),
        templates_file=tmp_path / "vorlagen.json",
        # Kein Netz im Test: die Anzeigenseite wird nur auf Wunsch geliefert.
        page_fetcher=lambda url: "",
    )
    return pipeline, store


def test_emails_reads_obfuscated_address() -> None:
    assert text.emails("Bewerbung an: personal [at] muster-logistik [dot] ch") == [
        "personal@muster-logistik.ch"
    ]


def test_contact_person_requires_herr_or_frau() -> None:
    assert text.contact_person("Ihre Ansprechpartnerin: Frau Meier") == "Frau Meier"
    assert text.contact_person("Bitte an Herrn Müller senden") == "Herr Müller"
    assert text.contact_person("Frau Dr. Meier") == "Frau Meier"
    assert text.contact_person("Gesucht wird eine Person mit Erfahrung") == ""
    assert text.contact_person("Sehr geehrte Damen und Herren") == ""


def test_image_urls_are_made_absolute() -> None:
    html = '<p>Kontakt</p><img src="/bilder/kontakt.png">'
    assert ocr.image_urls(html, "https://www.ostjob.ch/job/x/1") == [
        "https://www.ostjob.ch/bilder/kontakt.png"
    ]


def test_text_from_html_reads_images() -> None:
    seen: list[str] = []
    result = ocr.text_from_html(
        '<img src="https://cdn.example/kontakt.png">',
        fetch=lambda url: seen.append(url) or b"bild",
        recognize=lambda data: "Frau Meier, personal@muster-logistik.ch",
    )
    assert seen == ["https://cdn.example/kontakt.png"]
    assert "Frau Meier" in result


def test_contact_check_reads_contact_from_image(tmp_path, monkeypatch) -> None:
    pipeline, store = _pipeline(tmp_path, _image_job())
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(
        ocr,
        "text_from_html",
        lambda html, base="": (
            "Ihre Ansprechpartnerin: Frau Meier, personal@muster-logistik.ch"
        ),
    )
    assert pipeline.contact_check("ostjob:77") == []
    row = store.get_job("ostjob:77")
    assert row["contact_email"] == "personal@muster-logistik.ch"
    assert row["contact_name"] == "Frau Meier"
    # Genau diese Adresse steht im Entwurf als Empfänger.
    assert Job.from_row(row).contact_address() == "personal@muster-logistik.ch"


def test_contact_check_reports_missing_data(tmp_path, monkeypatch) -> None:
    pipeline, _store = _pipeline(tmp_path, _image_job())
    monkeypatch.setattr(ocr, "available", lambda: False)
    assert pipeline.contact_check("ostjob:77") == ["email", "anrede"]


def test_contact_check_keeps_known_data(tmp_path) -> None:
    job = _image_job(
        contact_email="personal@muster-logistik.ch", contact_name="Frau Meier"
    )
    pipeline, _store = _pipeline(tmp_path, job)
    assert pipeline.contact_check("ostjob:77") == []


def test_contact_from_ad_text_is_read_before_images(tmp_path, monkeypatch) -> None:
    job = _image_job(
        contact_email="",
        description=(
            "Ihre vollständigen Unterlagen senden Sie bitte an "
            "personal@progresspersonal.ch. Ansprechpartnerin: Frau Keller."
        ),
    )
    pipeline, store = _pipeline(tmp_path, job)
    monkeypatch.setattr(ocr, "available", lambda: True)

    def not_used(html: str, base: str = "") -> str:
        raise AssertionError("Bilder dürfen nicht gelesen werden, wenn der Text reicht")

    monkeypatch.setattr(ocr, "text_from_html", not_used)
    assert pipeline.contact_check("ostjob:77") == []
    row = store.get_job("ostjob:77")
    assert row["contact_email"] == "personal@progresspersonal.ch"
    assert row["contact_name"] == "Frau Keller"
    assert Job.from_row(row).contact_address() == "personal@progresspersonal.ch"


def test_ad_text_address_without_person_asks_only_for_salutation(
    tmp_path, monkeypatch
) -> None:
    job = _image_job(
        contact_email="",
        description="Bewerbung an personal@progresspersonal.ch",
    )
    pipeline, store = _pipeline(tmp_path, job)
    monkeypatch.setattr(ocr, "available", lambda: False)
    assert pipeline.contact_check("ostjob:77") == ["anrede"]
    assert store.get_job("ostjob:77")["contact_email"] == "personal@progresspersonal.ch"


def test_portal_address_is_not_taken_as_contact(tmp_path, monkeypatch) -> None:
    job = _image_job(
        contact_email="",
        description=(
            "Fragen zur Anzeige: info@ostjob.ch. Bewerbung an "
            "personal@progresspersonal.ch"
        ),
    )
    pipeline, store = _pipeline(tmp_path, job)
    monkeypatch.setattr(ocr, "available", lambda: False)
    pipeline.contact_check("ostjob:77")
    assert store.get_job("ostjob:77")["contact_email"] == (
        "personal@progresspersonal.ch"
    )


def test_person_from_image_fills_the_rest(tmp_path, monkeypatch) -> None:
    job = _image_job(
        contact_email="",
        description="Bewerbung an personal@progresspersonal.ch",
    )
    pipeline, store = _pipeline(tmp_path, job)
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(
        ocr,
        "text_from_html",
        lambda html, base="": "Ihre Ansprechpartnerin: Frau Keller",
    )
    assert pipeline.contact_check("ostjob:77") == []
    row = store.get_job("ostjob:77")
    assert row["contact_email"] == "personal@progresspersonal.ch"
    assert row["contact_name"] == "Frau Keller"


def test_address_from_the_linked_ad_page_is_used(tmp_path) -> None:
    job = _image_job(
        contact_email="",
        description="",
        raw={
            "contact": (
                '<p>Apply to this job offer by clicking here:<br />'
                '<a href="https://careers.example/job/1">https://careers.example/job/1</a></p>'
            )
        },
    )
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    store.upsert_job(job)
    page = (
        '<div class="job"><p>Ihre Bewerbung richten Sie bitte an '
        "marina.peter@progresspersonal.ch.</p></div>"
    )
    pipeline = Pipeline(
        settings,
        store,
        ai_client=FakeAI(),
        templates_file=tmp_path / "vorlagen.json",
        page_fetcher=lambda url: page,
    )
    assert pipeline.contact_check("ostjob:77") == ["anrede"]
    assert store.get_job("ostjob:77")["contact_email"] == (
        "marina.peter@progresspersonal.ch"
    )


def test_technical_and_portal_addresses_are_ignored_in_page_text(tmp_path) -> None:
    job = _image_job(contact_email="", description="")
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    store.upsert_job(job)
    page = (
        "Fragen: info@ostjob.ch, inserate@ostjob.ch, "
        "73996f9349b9426fa79ea6c2c7ff62bc@sentry.example, "
        "marina.peter@progresspersonal.ch"
    )
    pipeline = Pipeline(
        settings,
        store,
        ai_client=FakeAI(),
        templates_file=tmp_path / "vorlagen.json",
        page_fetcher=lambda url: page,
    )
    pipeline.contact_check("ostjob:77")
    assert store.get_job("ostjob:77")["contact_email"] == (
        "marina.peter@progresspersonal.ch"
    )


def test_escaped_line_break_does_not_glue_to_the_address(tmp_path) -> None:
    job = _image_job(contact_email="", description="")
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    store.upsert_job(job)
    page = '<script>var text = "Kontakt:\\nmarina.peter@progresspersonal.ch";</script>'
    pipeline = Pipeline(
        settings,
        store,
        ai_client=FakeAI(),
        templates_file=tmp_path / "vorlagen.json",
        page_fetcher=lambda url: page,
    )
    pipeline.contact_check("ostjob:77")
    assert store.get_job("ostjob:77")["contact_email"] == (
        "marina.peter@progresspersonal.ch"
    )


def test_complete_job_fills_missing_name_email_and_address(tmp_path) -> None:
    job = _image_job(
        contact_email="",
        street="",
        zip="",
        description=(
            "Bewerbung an personal@progresspersonal.ch. "
            "Ansprechpartnerin: Frau Keller."
        ),
        raw={"company": {"homepage": "https://muster-logistik.ch"}},
    )
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    store.upsert_job(job)
    pipeline = Pipeline(
        settings,
        store,
        ai_client=FakeAI(),
        templates_file=tmp_path / "vorlagen.json",
        page_fetcher=lambda url: (
            "Muster Logistik AG, Bahnhofstrasse 12, 9436 Balgach"
        ),
    )
    assert pipeline.complete_job("ostjob:77") is True
    row = store.get_job("ostjob:77")
    assert row["contact_email"] == "personal@progresspersonal.ch"
    assert row["contact_name"] == "Frau Keller"
    assert row["street"] == "Bahnhofstrasse 12"
    assert row["zip"] == "9436"
    # Beim zweiten Mal ist nichts mehr zu ergaenzen.
    assert pipeline.complete_job("ostjob:77") is False


def test_complete_job_keeps_existing_values(tmp_path) -> None:
    job = _image_job(
        contact_email="bewerbung@muster-logistik.ch",
        contact_name="Frau Meier",
        street="Bahnhofstrasse 12",
        zip="9436",
    )
    settings = Settings(tmp_path / "einstellungen.json")
    store = Store(tmp_path / "daten.db")
    store.upsert_job(job)
    pipeline = Pipeline(
        settings,
        store,
        ai_client=FakeAI(),
        templates_file=tmp_path / "vorlagen.json",
        page_fetcher=lambda url: "Muster AG, Andere Strasse 9, 8000 Zürich",
    )
    assert pipeline.complete_job("ostjob:77") is False
    row = store.get_job("ostjob:77")
    assert row["contact_email"] == "bewerbung@muster-logistik.ch"
    assert row["contact_name"] == "Frau Meier"
    assert row["street"] == "Bahnhofstrasse 12"
    assert row["zip"] == "9436"
