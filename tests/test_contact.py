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
