from __future__ import annotations

import json

from autoapplication.core.models import Job
from autoapplication.core.templates import (
    Template,
    choose_template,
    follow_up_template,
    load_defaults,
    load_templates,
    render_mail,
    save_templates,
    vocabulary,
)


def _job(title: str = "Speditionskaufmann", description: str = "Disposition und Zoll") -> Job:
    return Job(
        id="ostjob:1",
        source="ostjob",
        source_id="1",
        title=title,
        company="Muster Logistik AG",
        city="Balgach",
        workload="80-100 %",
        description=description,
        keywords=["Spedition", "Disposition"],
    )


def test_defaults_contain_spedition_and_follow_up() -> None:
    templates = load_defaults()
    ids = {template.id for template in templates}
    assert {"spedition", "tapetenwechsel", "lager", "nachfassen"} <= ids
    assert follow_up_template(templates) is not None
    assert "Spedition" in vocabulary(templates)
    assert all(template.body for template in templates)
    assert all(template.subject for template in templates)


def test_choose_template_needs_two_keywords() -> None:
    templates = load_defaults()
    template, score, matches = choose_template(templates, _job(), ["Spedition"], 2)
    assert template is not None
    assert template.id == "spedition"
    assert score >= 2
    assert "Spedition" in matches


def test_no_template_when_too_few_keywords() -> None:
    templates = load_defaults()
    job = Job(
        id="ostjob:9",
        source="ostjob",
        source_id="9",
        title="Buchhalter",
        company="Treuhand AG",
        description="Zahlen und Belege",
    )
    template, score, _ = choose_template(templates, job, [], 2)
    assert template is None
    assert score == 0


def test_choice_between_templates() -> None:
    templates = load_defaults()
    job = _job("Sachbearbeiter Administration", "Kundendienst und Verwaltung")
    template, _score, _ = choose_template(templates, job, ["Sachbearbeitung", "Kundendienst"], 2)
    assert template is not None and template.id == "tapetenwechsel"


def test_render_mail_replaces_all_placeholders() -> None:
    templates = load_defaults()
    template = next(item for item in templates if item.id == "spedition")
    profile = {
        "vorname": "Erika",
        "nachname": "Muster",
        "strasse": "Wolfsbachstrasse 6",
        "plz": "9436",
        "wohnort": "Balgach",
        "telefon": "+41 71 000 00 00",
        "email": "erika@example.ch",
        "erfahrung_jahre": "acht",
        "verfuegbar": "sofort",
    }
    subject, body = render_mail(template, profile, _job())
    assert "Speditionskaufmann" in subject
    assert "Erika Muster" in subject
    assert "Muster Logistik AG" in body
    assert "acht" in body
    assert "{" not in body and "}" not in body


def test_unknown_placeholder_becomes_empty() -> None:
    template = Template(id="x", name="X", subject="Hallo {gibt_es_nicht}", body="Text {auch_nicht}")
    subject, body = render_mail(template, {}, None)
    assert subject.strip() == "Hallo"
    assert body.strip() == "Text"


def test_save_and_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    templates = [
        Template(id="a", name="A", keywords=["x"], subject="S", body="B"),
        Template(id="b", name="B", follow_up=True, subject="S2", body="B2"),
    ]
    save_templates(path, templates)
    loaded = load_templates(path)
    assert [item.id for item in loaded] == ["a", "b"]
    assert loaded[1].follow_up is True


def test_first_load_seeds_file(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    assert not path.exists()
    loaded = load_templates(path)
    assert path.exists()
    assert loaded
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1


def test_broken_file_uses_defaults(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    path.write_text("{kaputt", encoding="utf-8")
    loaded = load_templates(path)
    assert loaded == load_defaults()


def test_defaults_use_salutation_placeholder() -> None:
    templates = load_defaults()
    assert all("{anrede}" in template.body for template in templates)


def test_render_uses_contact_salutation() -> None:
    templates = load_defaults()
    template = next(item for item in templates if item.id == "spedition")
    profile = {"vorname": "Erika", "nachname": "Muster", "wohnort": "Balgach"}
    job = _job()
    job.contact_name = "Herr Müller"
    _subject, body = render_mail(template, profile, job)
    assert body.startswith("Sehr geehrter Herr Müller")
    assert "Sehr geehrte Damen und Herren" not in body


def test_render_without_contact_uses_general_greeting() -> None:
    templates = load_defaults()
    template = next(item for item in templates if item.id == "spedition")
    _subject, body = render_mail(template, {"vorname": "Erika"}, _job())
    assert body.startswith("Sehr geehrte Damen und Herren")


def test_template_needs_title_hit_or_one_more_keyword() -> None:
    template = Template(
        id="x", name="X", keywords=["Produktion", "Montage"], subject="S", body="B"
    )
    job = Job(
        id="ostjob:9",
        source="ostjob",
        source_id="9",
        title="Facharbeiter",
        company="Firma AG",
        description="Produktion und Montage",
    )
    chosen, score, _ = choose_template([template], job, [], 2)
    assert chosen is None and score == 2

    job.title = "Mitarbeiter Produktion"
    chosen, score, _ = choose_template([template], job, [], 2)
    assert chosen is not None and score == 2


def test_old_templates_are_upgraded(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    payload = {
        "version": 1,
        "templates": [
            {
                "id": "lager",
                "name": "Lager",
                "keywords": ["Lager", "Produktion", "Montage", "Maschinenbedienung"],
                "subject": "S",
                "body": "Sehr geehrte Damen und Herren\n\nText",
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    loaded = load_templates(path)
    body = loaded[0].body
    assert body.startswith("{anrede}")
    assert "Produktion" not in loaded[0].keywords
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "{anrede}" in saved["templates"][0]["body"]
