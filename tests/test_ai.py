from __future__ import annotations

import urllib.error

from autoapplication.core.ai import (
    ABSAGE,
    EINLADUNG,
    INFO,
    ZUSAGE,
    AiClient,
    classify_local,
    local_keywords,
)
from autoapplication.core.config import Settings
from autoapplication.core.models import Job


def _job() -> Job:
    return Job(
        id="ostjob:1",
        source="ostjob",
        source_id="1",
        title="Speditionskaufmann Disposition",
        company="Muster AG",
        description="Transport, Zoll und Lager",
        keywords=["Spedition", "Transport"],
    )


def _settings(tmp_path, enabled: bool = True) -> Settings:
    settings = Settings(tmp_path / "e.json")
    settings.set("ai.enabled", enabled)
    settings.set("ai.base_url", "https://api.example/v1")
    settings.set("ai.model", "test-model")
    settings.set("ai.api_key", "key")
    return settings


def _groq_transport(calls: list) -> object:
    def send(url, payload, headers, timeout):
        calls.append((url, payload))
        return {"choices": [{"message": {"content": '{"stichworte": ["Spedition"]}'}}]}

    return send


def test_groq_defaults_and_profile_hints(tmp_path) -> None:
    settings = Settings(tmp_path / "e.json")
    settings.set("ai.enabled", True)
    settings.set("ai.provider", "groq")
    settings.set("ai.base_url", "")
    settings.set("ai.model", "")
    settings.set("ai.api_key", "gsk_test")
    settings.set("profile.interessen", ["Nachhaltigkeit"])
    settings.set("profile.faehigkeiten", ["Disposition"])
    calls: list = []
    client = AiClient(settings, transport=_groq_transport(calls))
    assert client.available() is True
    assert client.keywords(_job(), []) == ["Spedition"]
    url, payload = calls[0]
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert payload["model"] == "llama-3.3-70b-versatile"
    user = payload["messages"][1]["content"]
    assert "Nachhaltigkeit" in user
    assert "Disposition" in user


def test_openai_keeps_stored_base_url(tmp_path) -> None:
    settings = _settings(tmp_path)
    client = AiClient(settings)
    assert client.base_url() == "https://api.example/v1"
    assert client.model() == "test-model"


def test_classify_rejection() -> None:
    assert (
        classify_local(
            "Ihre Bewerbung als Speditionskaufmann",
            "Leider müssen wir Ihnen mitteilen, dass wir einen anderen Bewerber "
            "bevorzugen. Wir wünschen Ihnen alles Gute.",
        )
        == ABSAGE
    )


def test_classify_acceptance() -> None:
    assert (
        classify_local(
            "Ihre Bewerbung",
            "Herzlichen Glückwunsch! Wir freuen uns, Ihnen mitzuteilen, dass wir "
            "Ihnen eine Stelle anbieten.",
        )
        == ZUSAGE
    )


def test_classify_invitation() -> None:
    assert (
        classify_local(
            "Einladung zum Vorstellungsgespräch",
            "Gerne möchten wir Sie zu einem Gespräch einladen und kennenlernen.",
        )
        == EINLADUNG
    )


def test_classify_generic() -> None:
    assert classify_local("Ihre Bewerbung", "Vielen Dank für Ihre Unterlagen.") == INFO
    assert classify_local("Werbung", "Jetzt 20% Rabatt") == INFO


def test_local_keywords_from_portal_and_vocabulary() -> None:
    keywords = local_keywords(_job(), ["Spedition", "Disposition", "Kundendienst"])
    assert "Spedition" in keywords
    assert "Disposition" in keywords
    assert "Kundendienst" not in keywords


def _transport(answer: str):
    def call(url, payload, headers, timeout):
        assert url.endswith("/chat/completions")
        assert payload["model"] == "test-model"
        return {"choices": [{"message": {"content": answer}}]}

    return call


def test_ai_keywords_parses_json_in_fence(tmp_path) -> None:
    client = AiClient(
        _settings(tmp_path),
        transport=_transport('```json\n{"stichworte": ["Spedition", "Zoll"]}\n```'),
    )
    assert client.available() is True
    assert client.keywords(_job(), []) == ["Spedition", "Zoll"]


def test_ai_keywords_falls_back_on_error(tmp_path) -> None:
    def broken(*_args, **_kwargs):
        raise urllib.error.URLError("kein Netz")

    client = AiClient(_settings(tmp_path), transport=broken)
    keywords = client.keywords(_job(), ["Disposition"])
    assert "Spedition" in keywords
    assert "Disposition" in keywords


def test_ai_classify(tmp_path) -> None:
    client = AiClient(_settings(tmp_path), transport=_transport('{"art": "absage"}'))
    assert client.classify("Bewerbung", "Text") == ABSAGE


def test_ai_classify_falls_back_on_error(tmp_path) -> None:
    def broken(*_args, **_kwargs):
        raise urllib.error.URLError("kein Netz")

    client = AiClient(_settings(tmp_path), transport=broken)
    assert client.classify("Ihre Bewerbung", "Leider eine Absage.") == ABSAGE
    assert client.classify("Ihre Bewerbung", "Vielen Dank.") == INFO


def test_ai_disabled_never_calls_transport(tmp_path) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("darf nicht aufgerufen werden")

    client = AiClient(_settings(tmp_path, enabled=False), transport=fail)
    assert client.available() is False
    assert client.keywords(_job(), []) == ["Spedition", "Transport", "Speditionskaufmann", "Disposition"]


def test_ai_classify_sees_the_whole_reply_and_the_job(tmp_path) -> None:
    calls: list = []

    def transport(url, payload, headers, timeout):
        calls.append(payload)
        return {"choices": [{"message": {"content": '{"art": "einladung"}'}}]}

    client = AiClient(_settings(tmp_path), transport=transport)
    reply = (
        "Gerne laden wir Sie zu einem Vorstellungsgespräch ein. Passt Ihnen "
        "Dienstag, 24. November, um 14 Uhr? Bitte bestätigen Sie den Termin."
    )
    kind = client.classify(
        "Ihre Bewerbung als Speditionskaufmann",
        reply,
        "hr@muster.ch",
        "Bewerbung als Speditionskaufmann bei Muster AG",
    )
    assert kind == EINLADUNG
    prompt = calls[0]["messages"]
    system = prompt[0]["content"]
    content = prompt[1]["content"]
    assert "Arbeitsvertrag" in system
    assert "Vorstellungsgespraech" in system
    assert "Zusage zum" in system
    assert reply in content
    assert "Bewerbung als Speditionskaufmann bei Muster AG" in content


def test_ai_classify_sends_a_long_reply_completely(tmp_path) -> None:
    calls: list = []

    def transport(url, payload, headers, timeout):
        calls.append(payload)
        return {"choices": [{"message": {"content": '{"art": "info"}'}}]}

    client = AiClient(_settings(tmp_path), transport=transport)
    reply = "Satz mit Inhalt. " * 500  # rund 8500 Zeichen
    client.classify("Betreff", reply)
    content = calls[0]["messages"][1]["content"]
    assert content.count("Satz mit Inhalt.") >= 300
    assert 5000 < len(content) < 6200  # gekappt bei 6000 Zeichen Antworttext


def test_local_classifier_separates_offer_from_invitation() -> None:
    assert (
        classify_local(
            "Ihre Bewerbung",
            "Gerne laden wir Sie zu einem Vorstellungsgespräch ein.",
        )
        == EINLADUNG
    )
    # "Zusage" im Termin-Kontext ist eine Einladung, keine Stellenzusage.
    assert (
        classify_local(
            "Ihre Bewerbung",
            "Vielen Dank für Ihre Zusage zum Vorstellungsgespräch am 3. Dezember.",
        )
        == EINLADUNG
    )
    assert (
        classify_local(
            "Ihre Bewerbung",
            "Wir freuen uns, Ihnen mitzuteilen, dass Sie die Stelle erhalten. "
            "Den Arbeitsvertrag finden Sie im Anhang.",
        )
        == ZUSAGE
    )
    assert classify_local("Ihre Bewerbung", "Im Anhang der Vertragsentwurf.") == ZUSAGE
    # Betreff "Zusage", im Text aber nur ein Termin: Einladung.
    assert (
        classify_local("Zusage", "Gerne bestätigen wir Ihnen den Termin am Montag.")
        == EINLADUNG
    )
    # Eine Einladung mit Terminvorschlag bleibt eine Einladung, auch wenn sie
    # den Vertrag nur erwähnt.
    assert (
        classify_local(
            "Kennenlernen",
            "Wir möchten Sie gerne kennenlernen und laden Sie zu einem Gespräch ein.",
        )
        == EINLADUNG
    )
