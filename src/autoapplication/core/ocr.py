"""Texterkennung fuer Stellenanzeigen, die den Kontakt nur als Bild zeigen.

Manche Anzeigen nennen die Ansprechperson und die Bewerbungsadresse nur in
einem Bild. Dieses Modul holt solche Bilder aus der Anzeige und liest den
Text mit der unter Windows eingebauten OCR (``winrt``/``winsdk``). Fehlt die
Texterkennung, bleibt das Ergebnis leer - die Oberflaeche fragt die Angaben
dann von Hand ab.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# Schutzgrenze gegen endlos lange Seiten; Kontaktbilder stehen weit vorne.
MAX_IMAGES = 60
MAX_BYTES = 4 * 1024 * 1024
TIMEOUT = 20.0
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
    ),
}
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
SRC_RE = re.compile(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
# alt/title/class verraten Logos auch dann, wenn die Adresse nichts sagt.
HINT_RE = re.compile(
    r"\b(?:alt|title|class)\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE
)
# Nicht lesbare Formate: Vektor- und Icon-Dateien enthalten keinen Fliesstext.
SKIP_SUFFIXES = (".svg", ".svgz", ".ico")
# Logo- und Social-Adressen: solche Bilder zeigen keine Kontaktdaten.
SKIP_WORDS = (
    "logo",
    "logotype",
    "icon",
    "favicon",
    "sprite",
    "svg",
    "social",
    "badge",
    "facebook",
    "linkedin",
    "instagram",
    "twitter",
    "xing",
    "youtube",
    "whatsapp",
    "tiktok",
    "pinterest",
)
SKIP_RE = re.compile(
    r"(?:^|[^a-z])(?:" + "|".join(SKIP_WORDS) + r")(?:[^a-z]|$)",
    re.IGNORECASE,
)

# Testbild mit Kontaktdaten: zeigt, ob die Texterkennung wirklich liest.
TEST_EMAIL = "anna.muster@example.ch"
TEST_NAME = "Anna Muster"


def is_icon_url(url: str) -> bool:
    """Zeigt die Adresse auf ein Logo, ein Icon oder ein Vektorbild?"""
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.unquote(parts.path).lower()
    if path.endswith(SKIP_SUFFIXES):
        return True
    return bool(SKIP_RE.search(path) or SKIP_RE.search(parts.query))


def is_icon_hint(value: str) -> bool:
    """Beschreibt alt/title/class das Bild als Logo, Icon oder Social-Bild?"""
    return bool(SKIP_RE.search(value or ""))


def image_urls(value: str, base_url: str = "") -> list[str]:
    """Bildadressen aus dem HTML einer Anzeige (absolut, ohne Doppel).

    Logos, Icons und SVG-Dateien fallen weg - erkennbar an der Adresse oder
    an ``alt``/``title``/``class`` - damit die Texterkennung nicht an
    Dekoration haengen bleibt. Alle uebrigen Bilder kommen mit, nicht nur
    die ersten drei.
    """
    urls: list[str] = []
    for tag in IMG_TAG_RE.findall(value or ""):
        match = SRC_RE.search(tag)
        if match is None:
            continue
        url = match.group(1).strip()
        if url.startswith("//"):
            url = "https:" + url
        elif base_url and not url.lower().startswith(("http://", "https://")):
            url = urllib.parse.urljoin(base_url, url)
        if not url.lower().startswith(("http://", "https://")):
            continue
        if is_icon_url(url):
            continue
        if any(is_icon_hint(hint) for hint in HINT_RE.findall(tag)):
            continue
        if url not in urls:
            urls.append(url)
    return urls[:MAX_IMAGES]


def test_image_path() -> Path:
    """Testbild mit bekannter Adresse (liegt neben den Vorlagen)."""
    return Path(__file__).resolve().parent.parent / "data" / "ocr-test.png"


def backend_name() -> str:
    """Name der gefundenen Texterkennung (``winrt``, ``winsdk`` oder leer)."""
    for package in ("winrt", "winsdk"):
        try:
            __import__(f"{package}.windows.media.ocr")
        except Exception:  # noqa: BLE001 - fehlende Pakete sind der Normalfall
            continue
        return package
    return ""


def available() -> bool:
    """Ist eine Texterkennung auf diesem Rechner vorhanden?"""
    for package in ("winrt", "winsdk"):
        try:
            __import__(f"{package}.windows.media.ocr")
        except Exception:  # noqa: BLE001 - fehlende Pakete sind der Normalfall
            continue
        return True
    return False


async def _recognize(
    data: bytes,
    engine_class: object,
    decoder_class: object,
    writer_class: object,
    stream_class: object,
    language_class: object,
) -> str:
    stream = stream_class()
    writer = writer_class(stream.get_output_stream_at(0))
    writer.write_bytes(data)
    await writer.store_async()
    await writer.flush_async()
    stream.seek(0)
    decoder = await decoder_class.create_async(stream)
    bitmap = await decoder.get_software_bitmap_async()

    engine = None
    for code in ("de-DE", "de-CH", "en-US"):
        try:
            engine = engine_class.try_create_from_language(language_class(code))
        except Exception:  # noqa: BLE001 - Sprache nicht installiert
            engine = None
        if engine is not None:
            break
    if engine is None:
        engine = engine_class.try_create_from_user_profile_languages()
    if engine is None:
        return ""
    result = await engine.recognize_async(bitmap)
    return str(getattr(result, "text", "") or "")


async def _winrt_ocr(data: bytes) -> str:
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    return await _recognize(
        data,
        OcrEngine,
        BitmapDecoder,
        DataWriter,
        InMemoryRandomAccessStream,
        Language,
    )


async def _winsdk_ocr(data: bytes) -> str:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    return await _recognize(
        data,
        OcrEngine,
        BitmapDecoder,
        DataWriter,
        InMemoryRandomAccessStream,
        Language,
    )


def _backend() -> Callable[[bytes], object] | None:
    try:
        __import__("winrt.windows.media.ocr")
        return _winrt_ocr
    except Exception:  # noqa: BLE001 - naechster Versuch
        pass
    try:
        __import__("winsdk.windows.media.ocr")
        return _winsdk_ocr
    except Exception:  # noqa: BLE001 - keine Texterkennung vorhanden
        return None


def extract_text(data: bytes) -> str:
    """Text aus einem Bild lesen; ohne Texterkennung bleibt das Ergebnis leer."""
    if not data:
        return ""
    backend = _backend()
    if backend is None:
        return ""
    loop = asyncio.new_event_loop()
    try:
        return str(loop.run_until_complete(backend(data)) or "")
    except Exception as exc:  # noqa: BLE001 - Texterkennung ist ein Zusatz
        log.info("Texterkennung fehlgeschlagen: %s", exc)
        return ""
    finally:
        loop.close()


def diagnose(
    recognize: Callable[[bytes], str] | None = None,
    backend: str | None = None,
) -> dict[str, object]:
    """Texterkennung pruefen: vorhanden, und liest sie ein Testbild?"""
    name = backend_name() if backend is None else backend
    reader = recognize or extract_text
    try:
        data = test_image_path().read_bytes()
    except OSError as exc:
        return {
            "backend": name,
            "available": bool(name),
            "text": "",
            "ok": False,
            "note": f"Testbild fehlt ({exc})",
        }
    if reader is extract_text and not name:
        return {
            "backend": "",
            "available": False,
            "text": "",
            "ok": False,
            "note": "keine Windows-Texterkennung",
        }
    try:
        text = str(reader(data) or "").strip()
    except Exception as exc:  # noqa: BLE001 - Diagnose darf nichts stoppen
        return {
            "backend": name,
            "available": True,
            "text": "",
            "ok": False,
            "note": f"Fehler beim Lesen ({exc})",
        }
    # Leerzeichen zaehlen nicht: manche Erkenner trennen Woerter nicht.
    glued = re.sub(r"\s+", "", text).lower()
    ok = TEST_EMAIL in glued
    return {
        "backend": name,
        "available": True,
        "text": text,
        "ok": ok,
        "note": "" if ok else "Testbild nicht gelesen",
    }


def status_line(info: dict[str, object] | None = None) -> str:
    """Kurztext fuer Selbsttest und Protokoll."""
    info = info if info is not None else diagnose()
    engine = (
        f"Windows-Texterkennung ({info['backend']})"
        if info["available"]
        else "keine Windows-Texterkennung"
    )
    if not info["available"]:
        return f"{engine}: Kontakte aus Bildern werden übersprungen."
    if info["ok"]:
        return f"{engine} liest das Testbild, Adresse {TEST_EMAIL} erkannt."
    text = " ".join(str(info.get("text") or "").split())[:80]
    note = str(info.get("note") or "Testbild nicht gelesen")
    return f"{engine} vorhanden, aber {note}: «{text or '–'}»"


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(MAX_BYTES + 1)


def text_from_html(
    value: str,
    base_url: str = "",
    *,
    fetch: Callable[[str], bytes] | None = None,
    recognize: Callable[[bytes], str] | None = None,
) -> str:
    """Alle Bilder einer Anzeige lesen und den erkannten Text zurueckgeben."""
    urls = image_urls(value, base_url)
    if not urls:
        return ""
    fetch = fetch or _fetch
    recognize = recognize or extract_text
    if recognize is extract_text and not available():
        return ""
    texts: list[str] = []
    for url in urls:
        try:
            data = fetch(url)
        except Exception as exc:  # noqa: BLE001 - ein Bild darf fehlen
            log.info("Bild konnte nicht geladen werden (%s): %s", url, exc)
            continue
        if not data or len(data) > MAX_BYTES:
            continue
        try:
            text = recognize(data)
        except Exception as exc:  # noqa: BLE001 - ein Bild darf fehlen
            log.info("Texterkennung fuer %s fehlgeschlagen: %s", url, exc)
            continue
        text = (text or "").strip()
        if text:
            texts.append(text)
    return "\n".join(texts)
