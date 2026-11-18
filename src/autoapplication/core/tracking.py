"""Einmalige Kennung je Bewerbung - unsichtbar in der Mail, lesbar in der Antwort.

Jede Bewerbung bekommt eine zufaellige Kennung der Form ``AA-7K4P-Q9XM-3TRZ``.
Sie steht im HTML-Teil der Mail ganz unten als weisser Text in Schriftgroesse 0,
zusaetzlich als HTML-Kommentar und im Mailkopf ``X-AutoApplication-Ref``. Beim
Zitieren der Mail reist sie in der Antwort mit - damit laesst sich eine Antwort
auch dann sicher zuordnen, wenn Betreff, Absender und Unterhaltung nichts
hergeben.
"""

from __future__ import annotations

import re
import secrets
from html import escape
from typing import Callable

PREFIX = "AA"
GROUPS = (4, 4, 4)
# Ohne I, O, 0 und 1 - die verwechselt man beim Abtippen.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

CODE_PATTERN = re.compile(
    r"\bAA-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}\b", re.IGNORECASE
)


def new_code(taken: Callable[[str], bool] | None = None) -> str:
    """Zufaellige, einmalige Kennung; ``taken`` weist vergebene zurueck."""
    for _ in range(50):
        groups = [
            "".join(secrets.choice(ALPHABET) for _ in range(size)) for size in GROUPS
        ]
        code = "-".join((PREFIX, *groups))
        if taken is None or not taken(code):
            return code
    raise RuntimeError("Keine freie Kennung gefunden.")  # pragma: no cover


def find_code(text: str | None) -> str:
    """Erste Kennung im Text (auch in zitierten Mails); leer, wenn keine."""
    match = CODE_PATTERN.search(text or "")
    return match.group(0).upper() if match else ""


def hidden_block(code: str) -> str:
    """Unsichtbarer Absatz mit der Kennung, inklusive HTML-Kommentar."""
    return (
        '<div style="font-size:0;line-height:0;color:#ffffff;'
        'background-color:#ffffff;max-height:0;overflow:hidden;'
        'mso-hide:all" aria-hidden="true">'
        f"AutoApplication-Referenz {code}</div>\n"
        f"<!-- AutoApplication-Referenz {code} -->"
    )


def html_body(body: str, code: str = "") -> str:
    """Mailtext als einfaches HTML mit unsichtbarer Kennung am Ende."""
    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n", (body or "").strip())
        if block.strip()
    ]
    paragraphs: list[str] = []
    for block in blocks:
        lines = "<br>".join(escape(line) for line in block.splitlines())
        paragraphs.append(f'<p style="margin:0 0 12px 0">{lines}</p>')
    html = (
        '<div style="font-family:Calibri,Helvetica,Arial,sans-serif;'
        'font-size:11pt;color:#1a1a1a">' + "".join(paragraphs) + "</div>"
    )
    if code:
        html += hidden_block(code)
    return html


__all__ = ["ALPHABET", "find_code", "hidden_block", "html_body", "new_code"]
