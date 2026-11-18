from __future__ import annotations

import json

from autoapplication.core import config
from autoapplication.core.config import DEFAULTS, Settings


def test_defaults_are_complete() -> None:
    assert DEFAULTS["matching"]["min_score"] == 2
    assert DEFAULTS["automation"]["follow_up_days"] == 14
    assert DEFAULTS["search"]["queries"]


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


def test_home_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AUTOAPPLICATION_HOME", str(tmp_path / "zuhause"))
    assert config.app_home() == tmp_path / "zuhause"
    assert config.database_path().name == "daten.db"


def test_excluded_and_cantons(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json")
    settings.set("search.exclude", "Lehre, Praktikum,  KV ")
    assert settings.excluded_terms() == ["Lehre", "Praktikum", "KV"]
    settings.set("search.cantons", "St. Gallen, Thurgau")
    assert settings.canton_filter() == ["St. Gallen", "Thurgau"]
