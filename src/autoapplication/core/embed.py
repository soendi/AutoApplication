"""Eingebettete Seiten (iframes) einer Stellenanzeige finden.

Viele Portale zeigen die eigentliche Ausschreibung in einem eingebetteten
Rahmen - etwa bei umantis. Ansprechperson, E-Mail und Adresse stehen dann
nur in diesem Rahmen, nicht auf der Portalseite selbst.
"""

from __future__ import annotations

import re
import urllib.parse

IFRAME_RE = re.compile(r"<iframe\b[^>]*>", re.IGNORECASE)
SRC_RE = re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
# Werbung, Karten und Videos enthalten keine Stellenausschreibung.
SKIP_WORDS = (
    "youtube",
    "youtu.be",
    "vimeo",
    "google.",
    "doubleclick",
    "googletagmanager",
    "facebook",
    "linkedin",
    "instagram",
    "twitter",
    "xing",
    "recaptcha",
    "openstreetmap",
    "maps.",
)
MAX_FRAMES = 3


def frame_urls(value: str, base_url: str = "") -> list[str]:
    """Adressen eingebetteter Rahmen (absolut, ohne Doppel, ohne Werbung)."""
    urls: list[str] = []
    for tag in IFRAME_RE.findall(value or ""):
        match = SRC_RE.search(tag)
        if match is None:
            continue
        url = match.group(1).strip()
        if not url or url.startswith(("javascript:", "about:", "data:")):
            continue
        if url.startswith("//"):
            url = "https:" + url
        elif base_url and not url.lower().startswith(("http://", "https://")):
            url = urllib.parse.urljoin(base_url, url)
        if not url.lower().startswith(("http://", "https://")):
            continue
        host = urllib.parse.urlsplit(url).netloc.lower()
        if any(word in host for word in SKIP_WORDS):
            continue
        if url not in urls:
            urls.append(url)
    return urls[:MAX_FRAMES]
