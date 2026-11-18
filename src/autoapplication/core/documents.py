"""Unterlagen einsammeln und das Anschreiben als PDF erzeugen."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from .config import app_home

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
# Reihenfolge der Ordner, damit Lebenslauf und Zeugnisse zuerst kommen.
PREFERRED = ("lebenslauf", "cv", "zeugnis", "zeugnisse", "diplom", "diplome", "ausweis")

# Seitengestaltung des Anschreibens: A4 hoch, Masse in Punkt.
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 62
MARGIN_TOP = 58
PAGE_BOTTOM = 104
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
FONT_SIZE = 10.5
SMALL = 8.5
LINE_FACTOR = 1.38
ACCENT = (0.11, 0.24, 0.34)
MUTED = (0.36, 0.39, 0.43)
LIGHT = (0.66, 0.69, 0.72)
BLACK = (0.0, 0.0, 0.0)

# Zeichenbreiten von Helvetica in Tausendstel Em (Zeichen 32 bis 126).
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556,
    278, 278, 584, 584, 584, 556, 1015,
    667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667,
    778, 722, 667, 611, 722, 667, 944, 667, 667, 611,
    278, 278, 278, 469, 556, 333,
    556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556,
    556, 333, 500, 278, 556, 500, 722, 500, 500, 500,
    334, 260, 334, 584,
)


def _sort_key(path: Path, root: Path) -> tuple[int, str]:
    try:
        relative = path.relative_to(root).as_posix().lower()
    except ValueError:
        relative = path.name.lower()
    rank = len(PREFERRED)
    for index, prefix in enumerate(PREFERRED):
        if prefix in relative:
            rank = index
            break
    return rank, relative


def collect(
    folder: str | Path | None,
    *,
    enabled: bool = True,
    max_mb: float = 20,
    limit: int = 12,
) -> list[Path]:
    """Unterlagen aus dem Ordner sammeln (rekursiv, ohne Verstecktes)."""
    if not enabled or not folder:
        return []
    root = Path(folder).expanduser()
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: _sort_key(item, root)):
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.suffix.lower() not in SUPPORTED:
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        files.append(path)
        if len(files) >= limit:
            break

    # Gesamtgroesse begrenzen: der Anhang darf die Mail nicht sprengen.
    selected: list[Path] = []
    total = 0.0
    for path in files:
        size_mb = path.stat().st_size / (1024 * 1024)
        if total + size_mb > max_mb:
            log.info("Unterlage %s ausgelassen: Anhang ueber %.0f MB", path.name, max_mb)
            continue
        total += size_mb
        selected.append(path)
    return selected


def describe(paths: list[Path]) -> str:
    if not paths:
        return "keine Anhaenge"
    names = ", ".join(path.name for path in paths[:3])
    if len(paths) > 3:
        return f"{names} und {len(paths) - 3} weitere"
    return names


# ----------------------------------------------------------------------
# Anschreiben als PDF
# ----------------------------------------------------------------------
def cover_letter_folder() -> Path:
    return app_home() / "anschreiben"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _name(profile: dict[str, Any]) -> str:
    return " ".join(
        part for part in (_text(profile.get("vorname")), _text(profile.get("nachname"))) if part
    )


def _place(profile: dict[str, Any]) -> str:
    return " ".join(
        part for part in (_text(profile.get("plz")), _text(profile.get("wohnort"))) if part
    )


def _pdf_escape(value: str) -> bytes:
    raw = value.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _char_width(character: str) -> int:
    index = ord(character) - 32
    if 0 <= index < len(_HELVETICA):
        return _HELVETICA[index]
    return 556  # Umlaute und Sonderzeichen


def _text_width(text: str, size: float, bold: bool = False) -> float:
    units = sum(_char_width(character) for character in text)
    return units * size / 1000.0 * (1.04 if bold else 1.0)


def _wrap(text: str, size: float = FONT_SIZE, width: float = TEXT_WIDTH) -> list[str]:
    """Text auf die Satzbreite umbrechen - wortweise, ohne Silbentrennung."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or _text_width(candidate, size) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


@dataclass
class Text:
    """Eine Zeile im Anschreiben."""

    text: str
    size: float = FONT_SIZE
    bold: bool = False
    align: str = "left"
    gap: float = 0.0
    color: tuple[float, float, float] = BLACK

    def height(self) -> float:
        return self.size * LINE_FACTOR + self.gap


@dataclass
class Rule:
    """Eine Trennlinie über die Satzbreite."""

    gap: float = 0.0
    thickness: float = 0.8
    color: tuple[float, float, float] = ACCENT

    def height(self) -> float:
        return self.gap + self.thickness


_CLOSINGS = (
    "freundliche grüsse",
    "freundlichen grüssen",
    "freundliche grüssen",
    "freundlichem gruss",
    "mit freundlichen grüssen",
    "mit besten grüssen",
    "beste grüsse",
    "hochachtungsvoll",
)


def _is_closing(line: str) -> bool:
    lowered = re.sub(r"\s+", " ", line).strip().lower()
    return any(lowered.startswith(opening) for opening in _CLOSINGS)


def split_signature(letter: str) -> tuple[list[str], str]:
    """Absätze, Schlussformel und Namenszeile des Anschreibens trennen.

    Die Schlussformel und der Name werden im PDF eigens gesetzt; alles, was
    danach folgt (Adresse, Telefon), steht bereits im Briefkopf.
    """
    paragraphs = [
        block.strip()
        for block in re.split(r"\n\s*\n", (letter or "").strip())
        if block.strip()
    ]
    body: list[str] = []
    closing = ""
    for paragraph in paragraphs:
        lines = paragraph.splitlines()
        position = next(
            (index for index, line in enumerate(lines) if _is_closing(line)), None
        )
        if position is None:
            body.append(paragraph)
            continue
        preceding = "\n".join(lines[:position]).strip()
        if preceding:
            body.append(preceding)
        closing = lines[position].strip()
        break
    return body, closing or "Freundliche Grüsse"


def letter_flow(
    profile: dict[str, Any],
    job_title: str,
    company: str,
    letter: str,
    *,
    city: str = "",
    day: date | None = None,
) -> list[Text | Rule]:
    """Briefkopf, Empfänger, Betreff, Text und Grussformel als Satzablauf."""
    day = day or date.today()
    name = _name(profile)
    flow: list[Text | Rule] = []
    if name:
        flow.append(Text(name, 15, bold=True))
    address = _text(profile.get("strasse"))
    if address:
        flow.append(Text(address, SMALL, gap=3, color=MUTED))
    place = _place(profile)
    if place:
        flow.append(Text(place, SMALL, gap=1.5, color=MUTED))
    contact = " · ".join(
        part for part in (_text(profile.get("telefon")), _text(profile.get("email"))) if part
    )
    if contact:
        flow.append(Text(contact, SMALL, gap=1.5, color=MUTED))
    flow.append(Rule(gap=9, thickness=1.4, color=ACCENT))

    stamp = day.strftime("%d.%m.%Y")
    origin = _text(profile.get("wohnort"))
    flow.append(
        Text(f"{origin}, {stamp}" if origin else stamp, 9.5, align="right", gap=12, color=MUTED)
    )

    if company.strip():
        flow.append(Text(company.strip(), FONT_SIZE, gap=26))
        if city.strip():
            flow.append(Text(city.strip(), FONT_SIZE, gap=1.5))
    else:
        flow.append(Text("", FONT_SIZE, gap=20))

    subject = " ".join(part for part in ("Bewerbung als", job_title.strip()) if part).strip()
    if subject:
        flow.append(Text(subject, 11.5, bold=True, gap=24))

    paragraphs, closing = split_signature(letter)
    for index, paragraph in enumerate(paragraphs):
        text = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if not text:
            continue
        for position, line in enumerate(_wrap(text)):
            gap = (16.0 if index == 0 else 12.0) if position == 0 else 0.0
            flow.append(Text(line, FONT_SIZE, gap=gap))
    flow.append(Text(closing, FONT_SIZE, gap=16))
    if name:
        flow.append(Text(name, FONT_SIZE, bold=True, gap=36))
    return flow


def _paginate(flow: list[Text | Rule]) -> list[list[tuple[Text | Rule, float]]]:
    """Satzablauf auf Seiten verteilen und die Grundlinie jeder Zeile setzen."""
    pages: list[list[tuple[Text | Rule, float]]] = []
    current: list[tuple[Text | Rule, float]] = []
    top = PAGE_HEIGHT - MARGIN_TOP
    cursor = top
    for item in flow:
        height = item.height()
        if current and cursor - height < PAGE_BOTTOM:
            pages.append(current)
            current = []
            cursor = top
        offset = item.gap + (0.0 if isinstance(item, Rule) else item.size * 0.86)
        current.append((item, cursor - offset))
        cursor -= height
    pages.append(current)
    return pages


def _text_commands(
    text: str,
    size: float,
    x: float,
    baseline: float,
    color: tuple[float, float, float],
    *,
    bold: bool = False,
) -> list[bytes]:
    font = b"F2" if bold else b"F1"
    red, green, blue = color
    prefix = (
        f"{red:.3f} {green:.3f} {blue:.3f} rg\n"
        f"BT /{font.decode()} {size:.2f} Tf "
        f"1 0 0 1 {x:.2f} {baseline:.2f} Tm ("
    ).encode("ascii")
    return [prefix + _pdf_escape(text) + b") Tj ET"]


def _rule_commands(
    baseline: float, thickness: float, color: tuple[float, float, float]
) -> list[bytes]:
    red, green, blue = color
    return [
        (
            f"{red:.3f} {green:.3f} {blue:.3f} RG {thickness:.2f} w\n"
            f"{MARGIN_X} {baseline:.2f} m {PAGE_WIDTH - MARGIN_X} {baseline:.2f} l S"
        ).encode("ascii")
    ]


def _page_content(items: list[tuple[Text | Rule, float]]) -> bytes:
    commands: list[bytes] = []
    for item, baseline in items:
        if isinstance(item, Rule):
            commands.extend(_rule_commands(baseline, item.thickness, item.color))
            continue
        if not item.text:
            continue
        x = MARGIN_X
        if item.align == "right":
            x = PAGE_WIDTH - MARGIN_X - _text_width(item.text, item.size, item.bold)
        commands.extend(
            _text_commands(item.text, item.size, x, baseline, item.color, bold=item.bold)
        )
    return b"\n".join(commands)


def footer_commands(profile: dict[str, Any], page: int, total: int) -> list[bytes]:
    """Fusszeile mit Kontaktzeile links und Seitenzahl rechts."""
    summary = " · ".join(
        part
        for part in (_name(profile), _text(profile.get("strasse")), _place(profile))
        if part
    )
    commands = _rule_commands(PAGE_BOTTOM - 24, 0.4, LIGHT)
    if summary:
        commands.extend(_text_commands(summary, 7.5, MARGIN_X, PAGE_BOTTOM - 36, LIGHT))
    label = f"Seite {page} von {total}"
    commands.extend(
        _text_commands(
            label,
            7.5,
            PAGE_WIDTH - MARGIN_X - _text_width(label, 7.5),
            PAGE_BOTTOM - 36,
            LIGHT,
        )
    )
    return commands


def build_pdf(
    pages: list[list[Any]],
    *,
    footer: Callable[[int, int], list[bytes]] | None = None,
) -> bytes:
    """PDF mit Helvetica erzeugen - ohne zusaetzliche Bibliothek.

    Jede Seite ist eine Liste von Zeilen: einfache Zeichenketten, ``Text``
    oder ``Rule``. Fuer das Anschreiben liefert ``_paginate`` bereits die
    Grundlinien; alle uebrigen Zeilen werden von oben nach unten gesetzt.
    """
    normalized: list[list[tuple[Text | Rule, float]]] = []
    for page in pages or [[]]:
        positioned: list[tuple[Text | Rule, float]] = []
        cursor = PAGE_HEIGHT - MARGIN_TOP
        for entry in page:
            if isinstance(entry, tuple):
                item, baseline = entry
            else:
                item = entry if isinstance(entry, (Text, Rule)) else Text(str(entry))
                offset = item.gap + (0.0 if isinstance(item, Rule) else item.size * 0.86)
                baseline = cursor - offset
                cursor -= item.height()
            positioned.append((item, baseline))
        normalized.append(positioned)
    if not normalized:
        normalized = [[]]

    total = len(normalized)
    objects: dict[int, bytes] = {
        3: (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        ),
        4: (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
            b"/Encoding /WinAnsiEncoding >>"
        ),
    }
    kids: list[int] = []
    next_id = 5
    for index, items in enumerate(normalized, start=1):
        content = _page_content(items)
        if footer is not None:
            extra = b"\n".join(footer(index, total))
            if extra:
                content = content + b"\n" + extra
        content_id = next_id
        next_id += 1
        page_id = next_id
        next_id += 1
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode()
        kids.append(page_id)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = (
        "<< /Type /Pages /Kids ["
        + " ".join(f"{kid} 0 R" for kid in kids)
        + f"] /Count {len(kids)} >>"
    ).encode()

    highest = max(objects)
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(output)
        output += f"{number} 0 obj\n".encode()
        output += objects[number]
        output += b"\nendobj\n"
    startxref = len(output)
    output += f"xref\n0 {highest + 1}\n".encode()
    output += b"0000000000 65535 f \n"
    for number in range(1, highest + 1):
        output += f"{offsets.get(number, 0):010d} 00000 n \n".encode()
    output += (
        f"trailer\n<< /Size {highest + 1} /Root 1 0 R >>\n"
        f"startxref\n{startxref}\n%%EOF\n"
    ).encode()
    return bytes(output)


def write_cover_letter(
    profile: dict[str, Any],
    job_title: str,
    company: str,
    letter: str,
    *,
    city: str = "",
    folder: Path | None = None,
    day: date | None = None,
) -> Path:
    """Anschreiben als PDF im Benutzerordner ablegen und den Pfad liefern."""
    target = Path(folder) if folder else cover_letter_folder()
    target.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-. ]+", "", f"Anschreiben {company} {job_title}").strip()
    stem = re.sub(r"\s{2,}", " ", stem)[:70] or "Anschreiben"
    stamp = (day or date.today()).isoformat()
    path = target / f"{stem} {stamp}.pdf"
    flow = letter_flow(profile, job_title, company, letter, city=city, day=day)
    pages = _paginate(flow)
    path.write_bytes(
        build_pdf(
            pages,  # type: ignore[arg-type]
            footer=lambda index, total: footer_commands(profile, index, total),
        )
    )
    return path
