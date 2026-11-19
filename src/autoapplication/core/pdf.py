"""Kontaktdaten aus einer PDF-Beilage der Stellenanzeige lesen.

Manche Anzeigen haengen die Ausschreibung als PDF an. Ansprechperson,
E-Mail-Adresse und Firmenadresse stehen dort im Klartext - auch wenn die
Anzeigenseite selbst nur einen Link darauf zeigt. Gelesen wird mit dem
PDF-Modul von Qt, das mit PySide6 ohnehin vorhanden ist; eine zusaetzliche
Abhaengigkeit braucht es dafuer nicht.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
import urllib.request
from typing import Callable

log = logging.getLogger(__name__)

# Schutzgrenze: Stellenausschreibungen sind klein; riesige Dateien sind keine.
MAX_BYTES = 8 * 1024 * 1024
TIMEOUT = 20.0
MAX_PAGES = 3
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
    ),
}
# PDF-Verweise im HTML der Anzeige und nackte Adressen im Text.
PDF_HREF_RE = re.compile(
    r"""(?:href|src)\s*=\s*["']([^"']+?\.pdf(?:\?[^"']*)?)["']""",
    re.IGNORECASE,
)
PDF_BARE_RE = re.compile(r"""https?://[^\s"'<>]+?\.pdf\b""", re.IGNORECASE)


def pdf_urls(value: str, base_url: str = "") -> list[str]:
    """PDF-Adressen aus dem HTML einer Anzeige (absolut, ohne Doppel)."""
    urls: list[str] = []
    found = PDF_HREF_RE.findall(value or "") + PDF_BARE_RE.findall(value or "")
    for candidate in found:
        url = candidate.strip()
        if url.startswith("//"):
            url = "https:" + url
        elif base_url and not url.lower().startswith(("http://", "https://")):
            url = urllib.parse.urljoin(base_url, url)
        if not url.lower().startswith(("http://", "https://")):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(MAX_BYTES + 1)


def extract_text(data: bytes) -> str:
    """Text aus einem PDF lesen; ohne Qt-PDF bleibt das Ergebnis leer."""
    if not data:
        return ""
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtPdf import QPdfDocument
    except Exception as exc:  # noqa: BLE001 - Qt ohne PDF-Modul
        log.info("PDF-Modul nicht verfuegbar: %s", exc)
        return ""
    payload = QByteArray(data)
    # Die Nutzdaten muessen am Leben bleiben, solange der Puffer sie liest.
    buffer = QBuffer(payload)
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    document = QPdfDocument()
    try:
        document.load(buffer)
        if document.status() != QPdfDocument.Status.Ready:
            return ""
        texts: list[str] = []
        for page in range(min(document.pageCount(), MAX_PAGES)):
            selection = document.getAllText(page)
            text = selection.text() if selection is not None else ""
            if text and text.strip():
                texts.append(text)
        return "\n".join(texts)
    except Exception as exc:  # noqa: BLE001 - PDF ist nur ein Zusatz
        log.info("PDF konnte nicht gelesen werden: %s", exc)
        return ""
    finally:
        buffer.close()


def text_from_html(
    value: str,
    base_url: str = "",
    *,
    fetch: Callable[[str], bytes] | None = None,
    read: Callable[[bytes], str] | None = None,
) -> str:
    """Alle PDF-Beilaen einer Anzeige lesen und den Text zurueckgeben."""
    urls = pdf_urls(value, base_url)
    if not urls:
        return ""
    fetch = fetch or _fetch
    read = read or extract_text
    texts: list[str] = []
    for url in urls:
        try:
            data = fetch(url)
        except Exception as exc:  # noqa: BLE001 - eine Beilage darf fehlen
            log.info("PDF konnte nicht geladen werden (%s): %s", url, exc)
            continue
        if not data or len(data) > MAX_BYTES:
            continue
        text = (read(data) or "").strip()
        if text:
            texts.append(text)
    return "\n".join(texts)
