from __future__ import annotations

import json

from autoapplication.core.config import Settings
from autoapplication.core.models import Job
from autoapplication.core.templates import (
    Template,
    choose_template,
    fallback_template,
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
    assert {
        "spedition",
        "export_zoll",
        "lager",
        "technik_service",
        "it_support",
        "kundenbetreuung",
        "tapetenwechsel",
        "nachfassen",
        "produktion",
        "montage",
        "maschinenbedienung",
        "qualitaet",
        "einkauf",
        "buchhaltung",
        "personal",
        "empfang",
        "kundenservice",
        "chauffeur",
        "handwerk",
        "bau",
        "reinigung",
        "sicherheit",
        "gastronomie",
        "hotellerie",
        "landwirtschaft",
        "gesundheit",
        "soziales",
        "bildung",
        "ausbildung",
        "marketing",
        "allgemein",
    } <= ids
    application_templates = [
        template for template in templates if not template.follow_up and not template.fallback
    ]
    assert len(application_templates) >= 20
    assert fallback_template(templates) is not None
    assert fallback_template(templates).keywords == []
    assert all(template.revision > 0 for template in templates)
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


def test_no_matching_keywords_uses_general_template() -> None:
    templates = load_defaults()
    job = Job(
        id="ostjob:9",
        source="ostjob",
        source_id="9",
        title="Augenoptiker",
        company="Optik AG",
        description="Brillen, Sehtests und Kontaktlinsen",
    )
    template, score, _ = choose_template(templates, job, [], 2)
    assert template is not None and template.id == "allgemein"
    assert score == 0


def test_general_template_only_when_nothing_else_fits() -> None:
    templates = load_defaults()
    template, score, matches = choose_template(templates, _job(), ["Spedition"], 2)
    assert template is not None and template.id == "spedition"
    assert score >= 2 and matches
    lager_job = Job(
        id="ostjob:10",
        source="ostjob",
        source_id="10",
        title="Lagermitarbeiter",
        company="Muster AG",
        description="Kommissionierung und Warenannahme",
    )
    template, _score, _ = choose_template(templates, lager_job, [], 2)
    assert template is not None and template.id == "lager"


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
    assert loaded[1].follow_up is True and loaded[1].fallback is False


def test_first_load_seeds_file(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    assert not path.exists()
    loaded = load_templates(path)
    assert path.exists()
    assert loaded
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 5


def test_broken_file_uses_defaults(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    path.write_text("{kaputt", encoding="utf-8")
    loaded = load_templates(path)
    assert loaded == load_defaults()


def test_defaults_name_the_real_stations() -> None:
    templates = load_defaults()
    bodies = " ".join(template.body for template in templates)
    assert "Keller & Dürr" in bodies
    assert "Escatec" in bodies
    assert "zuletzt als Shipping Officer" not in bodies
    assert "{erfahrung}" in bodies


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
    # Die neuen Standardvorlagen kommen beim Nachziehen dazu.
    assert {"spedition", "export_zoll", "it_support"} <= {
        item["id"] for item in saved["templates"]
    }


def test_edited_default_template_is_kept(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    templates = load_defaults()
    template = next(item for item in templates if item.id == "spedition")
    template.body = "{anrede}\n\nEigener Text"
    save_templates(path, templates)
    loaded = load_templates(path)
    kept = next(item for item in loaded if item.id == "spedition")
    assert kept.body == "{anrede}\n\nEigener Text"


def test_spedition_templates_use_the_logistics_years(tmp_path) -> None:
    profile = Settings(tmp_path / "einstellungen.json").profile()
    templates = {item.id: item for item in load_defaults()}
    for key in ("spedition", "export_zoll"):
        _subject, body = render_mail(templates[key], profile, _job())
        assert "fast neunzehn" in body
        assert "über zwanzig" not in body
    # Wo die Gesamterfahrung gemeint ist, bleibt "über zwanzig" stehen.
    _subject, body = render_mail(templates["tapetenwechsel"], profile, _job())
    assert "über zwanzig" in body


def test_own_years_are_used_for_spedition(tmp_path) -> None:
    profile = {"erfahrung_jahre": "zwölf", "erfahrung_spedition": "sechs"}
    template = next(item for item in load_defaults() if item.id == "spedition")
    _subject, body = render_mail(template, profile, _job())
    assert "Seit sechs Jahren" in body


def test_old_spedition_template_gets_the_corrected_years(tmp_path) -> None:
    path = tmp_path / "vorlagen.json"
    payload = {
        "version": 3,
        "templates": [
            {
                "id": "spedition",
                "name": "Spedition und Logistik",
                "keywords": ["Spedition"],
                "subject": "S",
                "body": "{anrede}\n\nSeit {erfahrung} Jahren arbeite ich in Logistik.",
                "revision": 3,
            }
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    loaded = next(item for item in load_templates(path) if item.id == "spedition")
    assert "{erfahrung_spedition}" in loaded.body
    assert loaded.revision == 4
