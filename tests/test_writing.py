from __future__ import annotations

from datetime import date

from autoapplication.core.ai import AiClient, JobDigest
from autoapplication.core.config import Settings
from autoapplication.core.documents import build_pdf, write_cover_letter
from autoapplication.core.models import Job
from autoapplication.core.templates import load_defaults

PROFILE = {
    "vorname": "Erika",
    "nachname": "Muster",
    "strasse": "Hauptstrasse 1",
    "plz": "9436",
    "wohnort": "Balgach",
    "telefon": "071 000 00 00",
    "email": "erika@example.ch",
}


def _job() -> Job:
    return Job(
        id="ostjob:1",
        source="ostjob",
        source_id="1",
        title="Speditionskaufmann (m/w/d)",
        company="Muster Logistik AG",
        city="Balgach",
        workload="80-100 %",
        description="Disposition und Zoll (gn*). Job-ID: 445566",
        keywords=["Spedition"],
        contact_email="bewerbung@muster-logistik.ch",
    )


def _settings(tmp_path, enabled: bool = True) -> Settings:
    settings = Settings(tmp_path / "e.json")
    settings.set("ai.enabled", enabled)
    settings.set("ai.base_url", "https://api.example/v1")
    settings.set("ai.model", "test-modell")
    settings.set("ai.api_key", "key")
    settings.set("profile.faehigkeiten", ["Disposition", "SAP"])
    settings.set("profile.interessen", ["Logistik"])
    return settings


def _transport(answer: dict, calls: list) -> object:
    def send(url, payload, headers, timeout):
        calls.append((url, payload))
        import json

        return {"choices": [{"message": {"content": json.dumps(answer)}}]}

    return send


def test_cover_letter_pdf_is_written(tmp_path) -> None:
    path = write_cover_letter(
        PROFILE,
        "Speditionskaufmann",
        "Muster Logistik AG",
        "Sehr geehrte Damen und Herren,\n\nmit Interesse bewerbe ich mich.",
        folder=tmp_path,
        day=date(2026, 11, 18),
    )
    raw = path.read_bytes()
    assert raw.startswith(b"%PDF-1.4")
    assert raw.rstrip().endswith(b"%%EOF")
    assert path.name.startswith("Anschreiben")
    assert path.suffix == ".pdf"
    assert b"Muster Logistik AG" in raw
    assert b"Erika Muster" in raw


def test_pdf_uses_several_pages_for_long_text() -> None:
    pages = build_pdf([["Zeile"] * 44, ["Zeile"] * 10])
    assert pages.count(b"/Type /Page ") == 2


def test_job_digest_cleans_ai_answer(tmp_path) -> None:
    calls: list = []
    settings = _settings(tmp_path)
    client = AiClient(
        settings,
        transport=_transport(
            {
                "titel": "Speditionskaufmann (m/w/d) Job-ID: 999",
                "beschreibung": "Disposition und Zoll (gn*). Referenz: 123456",
                "kontakt_email": "jobs@muster.ch",
            },
            calls,
        ),
    )
    digest = client.job_digest(_job())
    assert digest.title == "Speditionskaufmann"
    assert "gn*" not in digest.description
    assert "123456" not in digest.description
    assert digest.contact_email == "jobs@muster.ch"


def test_job_digest_falls_back_locally(tmp_path) -> None:
    settings = _settings(tmp_path, enabled=False)
    digest = AiClient(settings).job_digest(_job())
    assert digest.title == "Speditionskaufmann"
    assert "m/w/d" not in digest.title
    assert digest.contact_email == "bewerbung@muster-logistik.ch"


def test_write_application_uses_ai(tmp_path) -> None:
    calls: list = []
    settings = _settings(tmp_path)
    client = AiClient(
        settings,
        transport=_transport(
            {
                "betreff": "Bewerbung als Speditionskaufmann",
                "text": "Sehr geehrte Damen und Herren,\n\n" + "Ich disponiere gerne. " * 8,
            },
            calls,
        ),
    )
    template = load_defaults()[0]
    written = client.write_application(template, PROFILE, _job(), JobDigest("Speditionskaufmann", "Disposition"))
    assert written is not None
    subject, body = written
    assert subject == "Bewerbung als Speditionskaufmann"
    assert "Ich disponiere" in body
    prompt = calls[0][1]["messages"]
    assert "Faehigkeiten: Disposition, SAP" in prompt[1]["content"]


def test_write_application_ignores_placeholders(tmp_path) -> None:
    settings = _settings(tmp_path)
    client = AiClient(
        settings,
        transport=_transport({"betreff": "Bewerbung {firma}", "text": "Text " * 40}, []),
    )
    template = load_defaults()[0]
    assert client.write_application(template, PROFILE, _job(), None) is None


def test_cover_letter_uses_ai(tmp_path) -> None:
    settings = _settings(tmp_path)
    client = AiClient(
        settings,
        transport=_transport({"anschreiben": "Sehr geehrte Damen und Herren,\n\n" + "Absatz. " * 20}, []),
    )
    letter = client.cover_letter(PROFILE, _job(), None)
    assert letter is not None
    assert letter.startswith("Sehr geehrte")
