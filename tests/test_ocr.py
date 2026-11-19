from __future__ import annotations

import pytest

from autoapplication.core import ocr
from autoapplication.core.store import Store


def test_test_image_ships_with_the_program() -> None:
    data = ocr.test_image_path().read_bytes()
    assert data.startswith(b"\x89PNG")
    assert len(data) > 1000


def test_missing_engine_is_reported() -> None:
    info = ocr.diagnose(backend="")
    assert info["available"] is False and info["ok"] is False
    line = ocr.status_line(info)
    assert "keine Windows-Texterkennung" in line
    assert "übersprungen" in line


def test_engine_reads_the_test_image() -> None:
    info = ocr.diagnose(
        recognize=lambda data: "Kontakt: Anna Muster\nanna.muster@example.ch",
        backend="winrt",
    )
    assert info["available"] is True
    assert info["ok"] is True
    assert info["backend"] == "winrt"
    assert ocr.TEST_EMAIL in ocr.status_line(info)


def test_engine_without_result_is_reported() -> None:
    info = ocr.diagnose(recognize=lambda data: "nur wirres zeug", backend="winsdk")
    assert info["ok"] is False
    line = ocr.status_line(info)
    assert "vorhanden, aber" in line
    assert "Testbild nicht gelesen" in line


def test_reading_error_is_reported() -> None:
    def kaputt(data: bytes) -> str:
        raise RuntimeError("Erkenner abgestürzt")

    info = ocr.diagnose(recognize=kaputt, backend="winrt")
    assert info["ok"] is False
    assert "Fehler beim Lesen" in ocr.status_line(info)


def test_address_counts_even_without_spaces() -> None:
    info = ocr.diagnose(recognize=lambda data: "anna.muster@exa mple.ch", backend="winrt")
    assert info["ok"] is True


def test_recognizer_reads_the_shipped_image() -> None:
    engine_module = pytest.importorskip("rapidocr_onnxruntime")
    engine = engine_module.RapidOCR()

    def recognize(data: bytes) -> str:
        result, _ = engine(data)
        return "\n".join(str(line[1]) for line in (result or []))

    info = ocr.diagnose(recognize=recognize, backend="winrt")
    assert info["ok"] is True, info["text"]


def test_ocr_status_goes_into_the_log_once(tmp_path) -> None:
    from autoapplication.app import _log_ocr_status

    store = Store(tmp_path / "daten.db")
    message = _log_ocr_status(store)
    assert "Texterkennung" in message
    entries = [row for row in store.events() if row["kind"] == "ocr"]
    assert len(entries) == 1
    assert entries[0]["message"] == message
    _log_ocr_status(store)
    assert len([row for row in store.events() if row["kind"] == "ocr"]) == 1


def test_svg_and_icons_are_skipped() -> None:
    html = (
        '<img src="/logo.png">'
        '<img src="/bilder/social-facebook.svg">'
        '<img src="/img/icons/linkedin.png">'
        '<img src="/favicon.ico">'
        '<img src="/img/kontakt.png">'
    )
    assert ocr.image_urls(html, "https://www.ostjob.ch/job/1") == [
        "https://www.ostjob.ch/img/kontakt.png"
    ]


def test_all_images_of_the_ad_are_used() -> None:
    html = "".join(f'<img src="/bilder/{number}.png">' for number in range(1, 7))
    urls = ocr.image_urls(html, "https://www.ostjob.ch/job/1")
    assert len(urls) == 6
    assert urls[3] == "https://www.ostjob.ch/bilder/4.png"


def test_real_image_names_are_kept() -> None:
    html = (
        '<img src="/bilder/teamfoto.jpg">'
        '<img src="/bilder/silicon-valley.jpg">'
        '<img src="/bilder/logo-2024.png">'
        '<img src="/bilder/bild.jpg?format=svg">'
    )
    assert ocr.image_urls(html, "https://www.ostjob.ch/job/1") == [
        "https://www.ostjob.ch/bilder/teamfoto.jpg",
        "https://www.ostjob.ch/bilder/silicon-valley.jpg",
    ]


def test_text_from_html_reads_the_fourth_image() -> None:
    seen: list[str] = []
    html = (
        '<img src="https://cdn.example/logo.png">'
        '<img src="https://cdn.example/icon-mail.png">'
        '<img src="https://cdn.example/social/xing.png">'
        '<img src="https://cdn.example/kontakt.png">'
    )

    def fetch(url: str) -> bytes:
        seen.append(url)
        return b"bild"

    result = ocr.text_from_html(
        html,
        fetch=fetch,
        recognize=lambda data: "Frau Meier, personal@muster-logistik.ch",
    )
    assert seen == ["https://cdn.example/kontakt.png"]
    assert result == "Frau Meier, personal@muster-logistik.ch"


def test_text_from_html_reads_past_the_first_three_images() -> None:
    seen: list[str] = []
    html = "".join(
        f'<img src="https://cdn.example/bild-{number}.png">' for number in range(1, 6)
    )

    def fetch(url: str) -> bytes:
        seen.append(url)
        return b"kontakt" if url.endswith("bild-5.png") else b"leer"

    def recognize(data: bytes) -> str:
        return "Kontakt: personal@muster-logistik.ch" if data == b"kontakt" else ""

    result = ocr.text_from_html(html, fetch=fetch, recognize=recognize)
    assert len(seen) == 5
    assert "personal@muster-logistik.ch" in result


def test_logo_and_social_icons_are_skipped_by_alt_text() -> None:
    html = (
        '<img src="https://file.example/bild-1" alt="stürmsfs Logo">'
        '<img src="https://file.example/bild-2" alt="stürmsfs auf LinkedIn">'
        '<img src="https://file.example/bild-3" '
        'alt="Ansprechpartnerin Anna Muster">'
    )
    assert ocr.image_urls(html) == ["https://file.example/bild-3"]


def test_icon_class_is_skipped() -> None:
    html = (
        '<img class="social-icon" src="https://file.example/bild-1">'
        '<img src="https://file.example/bild-2">'
    )
    assert ocr.image_urls(html) == ["https://file.example/bild-2"]
