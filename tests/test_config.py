from __future__ import annotations

import json

from autoapplication.core import config
from autoapplication.core.config import DEFAULTS, Settings


def test_defaults_are_complete() -> None:
    assert DEFAULTS["matching"]["min_score"] == 2
    assert DEFAULTS["automation"]["follow_up_days"] == 14
    assert DEFAULTS["search"]["queries"]
    # Die Stellen-API ist standardmaessig aus.
    assert DEFAULTS["search"]["api_enabled"] is False
    assert DEFAULTS["mail"]["provider"] == "outlook"


def test_old_experience_default_is_replaced(tmp_path) -> None:
    path = tmp_path / "einstellungen.json"
    path.write_text(json.dumps({"profile": {"erfahrung_jahre": "acht"}}), encoding="utf-8")
    settings = Settings(path).load()
    assert settings.text("profile.erfahrung_jahre") == DEFAULTS["profile"]["erfahrung_jahre"]
    assert DEFAULTS["profile"]["erfahrung_jahre"] == "über zwanzig"


def test_own_experience_value_is_kept(tmp_path) -> None:
    path = tmp_path / "einstellungen.json"
    path.write_text(json.dumps({"profile": {"erfahrung_jahre": "zwölf"}}), encoding="utf-8")
    assert Settings(path).load().text("profile.erfahrung_jahre") == "zwölf"


def test_interests_and_skills_are_separate(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json")
    settings.set("profile.interessen", ["Logistik", "Nachhaltigkeit"])
    settings.set("profile.faehigkeiten", "Disposition; SAP, Staplerschein")
    assert settings.interests() == ["Logistik", "Nachhaltigkeit"]
    assert settings.skills() == ["Disposition", "SAP", "Staplerschein"]
    profile = settings.profile()
    assert profile["interessen"] == "Logistik, Nachhaltigkeit"
    assert profile["faehigkeiten"] == "Disposition, SAP, Staplerschein"


def test_mail_provider_falls_back(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json")
    assert settings.mail_provider() == "outlook"
    settings.set("mail.provider", "none")
    assert settings.mail_provider() == "none"
    settings.set("mail.provider", "unbekannt")
    assert settings.mail_provider() == "outlook"

def test_dotted_access_and_roundtrip(tmp_path) -> None:
    path = tmp_path / "einstellungen.json"
    settings = Settings(path)
    settings.set("profile.vorname", "Erika")
    settings.set("search.queries", ["Spedition", "Logistik"])
    settings.set("search.workload_min", 70)
    settings.save()

    loaded = Settings(path).load()
    assert loaded.text("profile.vorname") == "Erika"
    assert loaded.search_terms() == ["Spedition", "Logistik"]
    assert loaded.number("search.workload_min") == 70
    assert loaded.text("profil.gibt.es.nicht", "leer") == "leer"


def test_partial_file_keeps_defaults(tmp_path) -> None:
    path = tmp_path / "einstellungen.json"
    path.write_text(json.dumps({"search": {"radius_km": 10}}), encoding="utf-8")
    settings = Settings(path).load()
    assert settings.number("search.radius_km") == 10
    assert settings.number("search.max_commute_km") == DEFAULTS["search"]["max_commute_km"]
    assert settings.text("ai.base_url")


def test_broken_file_falls_back(tmp_path) -> None:
    path = tmp_path / "einstellungen.json"
    path.write_text("{kaputt", encoding="utf-8")
    settings = Settings(path).load()
    assert settings.text("ai.model")


def test_ai_key_from_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AUTOAPPLICATION_AI_KEY", "abc123")
    settings = Settings(tmp_path / "einstellungen.json")
    assert settings.ai_key() == "abc123"
    settings.set("ai.api_key", "eigener")
    assert settings.ai_key() == "eigener"


def test_groq_key_from_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AUTOAPPLICATION_AI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    settings = Settings(tmp_path / "einstellungen.json")
    assert settings.ai_key() == "gsk_test"


def test_home_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOAPPLICATION_HOME", str(tmp_path / "zuhause"))
    assert config.app_home() == tmp_path / "zuhause"
    assert config.database_path().name == "daten.db"


def test_job_brokers_are_unique_and_clean(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json")
    settings.set(
        "search.job_brokers",
        ["  Müller  AG ", "müller ag", "", "Meier GmbH", "MEIER GMBH"],
    )
    assert settings.job_brokers() == ["Müller AG", "Meier GmbH"]
    settings.set("search.job_brokers", "Müller AG; Meier GmbH")
    assert settings.job_brokers() == ["Müller AG", "Meier GmbH"]
    assert DEFAULTS["search"]["hide_job_brokers"] is False


def test_excluded_and_cantons(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json")
    settings.set("search.exclude", "Lehre, Praktikum,  KV ")
    assert settings.excluded_terms() == ["Lehre", "Praktikum", "KV"]
    settings.set("search.cantons", "St. Gallen, Thurgau")
    assert settings.canton_filter() == ["St. Gallen", "Thurgau"]


def test_profile_has_a_werdegang_with_stations(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json").load()
    werdegang = settings.text("profile.werdegang")
    assert "Keller & Dürr Kassensysteme AG" in werdegang
    assert "Escatec Switzerland AG" in werdegang
    assert "Schenker Schweiz AG" in werdegang
    assert werdegang.count("\n") >= 4
