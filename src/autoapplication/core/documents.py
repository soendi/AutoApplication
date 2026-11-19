"""Unterlagen einsammeln und das Anschreiben als PDF erzeugen."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .config import app_home

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
# Reihenfolge der Ordner, damit Lebenslauf und Zeugnisse zuerst kommen.
PREFERRED = ("lebenslauf", "cv", "zeugnis", "zeugnisse", "diplom", "diplome", "ausweis")

# Brief auf A4 hoch, Masse in Punkt. Der Empfaengerblock liegt so, dass er in
# das Fenster eines Fenstercouverts passt (Fenster links, ab etwa 4 cm Hoehe).
PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 62  # 2,2 cm vom linken Rand
MARGIN_TOP = 56  # 2 cm vom oberen Rand (Absenderblock)
PAGE_BOTTOM = 64
TEXT_WIDTH = PAGE_WIDTH - 2 * MARGIN_X
FONT_SIZE = 10.5
LINE_FACTOR = 1.38
# Abstand zwischen Absenderblock und Empfaengerzeile: zusammen ergibt das die
# Fensterhoehe von rund 4,5 cm bis 5,5 cm.
ADDRESS_GAP = 16
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
    danach folgt (Adresse, Telefon), steht bereits im Absenderblock.
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
    street: str = "",
    zip_code: str = "",
    day: date | None = None,
) -> list[Text]:
    """Absender, Empfaenger im Couvertfenster, Datum, Betreff und Text."""
    day = day or date.today()
    name = _name(profile)
    flow: list[Text] = []

    # Absenderblock oben links: gleiche Groesse und Farbe wie der Brieftext.
    sender = [
        name,
        _text(profile.get("strasse")),
        _place(profile),
        " · ".join(
            part
            for part in (_text(profile.get("telefon")), _text(profile.get("email")))
            if part
        ),
    ]
    for line in [entry for entry in sender if entry]:
        flow.append(Text(line, FONT_SIZE, gap=1.5 if flow else 0.0))

    # Empfaengerblock: beginnt rund 4,5 cm unter dem Rand und liegt links, wo
    # das Fenster des Couverts sitzt.
    first = True
    recipient = [
        company.strip(),
        street.strip(),
        " ".join(part for part in (zip_code.strip(), city.strip()) if part),
    ]
    for line in [entry for entry in recipient if entry]:
        flow.append(Text(line, FONT_SIZE, gap=ADDRESS_GAP if first else 1.5))
        first = False
    if first:
        flow.append(Text("", FONT_SIZE, gap=ADDRESS_GAP))

    stamp = day.strftime("%d.%m.%Y")
    origin = _text(profile.get("wohnort"))
    flow.append(
        Text(f"{origin}, {stamp}" if origin else stamp, FONT_SIZE, align="right", gap=14)
    )

    subject = " ".join(part for part in ("Bewerbung als", job_title.strip()) if part).strip()
    if subject:
        flow.append(Text(subject, 11.5, bold=True, gap=22))

    paragraphs, closing = split_signature(letter)
    for index, paragraph in enumerate(paragraphs):
        text = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if not text:
            continue
        for position, line in enumerate(_wrap(text)):
            gap = (14.0 if index == 0 else 11.0) if position == 0 else 0.0
            flow.append(Text(line, FONT_SIZE, gap=gap))
    flow.append(Text(closing, FONT_SIZE, gap=16))
    if name:
        flow.append(Text(name, FONT_SIZE, gap=32))
    return flow


def _paginate(flow: list[Text]) -> list[list[tuple[Text, float]]]:
    """Satzablauf auf Seiten verteilen und die Grundlinie jeder Zeile setzen."""
    pages: list[list[tuple[Text, float]]] = []
    current: list[tuple[Text, float]] = []
    top = PAGE_HEIGHT - MARGIN_TOP
    cursor = top
    for item in flow:
        height = item.height()
        if current and cursor - height < PAGE_BOTTOM:
            pages.append(current)
            current = []
            cursor = top
        current.append((item, cursor - item.gap - item.size * 0.86))
        cursor -= height
    pages.append(current)
    return pages


def _text_commands(item: Text, baseline: float) -> bytes:
    x = MARGIN_X
    if item.align == "right":
        x = PAGE_WIDTH - MARGIN_X - _text_width(item.text, item.size, item.bold)
    font = "F2" if item.bold else "F1"
    red, green, blue = item.color
    prefix = (
        f"{red:.3f} {green:.3f} {blue:.3f} rg\n"
        f"BT /{font} {item.size:.2f} Tf "
        f"1 0 0 1 {x:.2f} {baseline:.2f} Tm ("
    ).encode("ascii")
    return prefix + _pdf_escape(item.text) + b") Tj ET"


def _page_content(items: list[tuple[Text, float]]) -> bytes:
    commands = [
        _text_commands(item, baseline) for item, baseline in items if item.text
    ]
    return b"\n".join(commands)


def build_pdf(pages: list[list[Any]]) -> bytes:
    """PDF mit Helvetica erzeugen - ohne zusaetzliche Bibliothek.

    Jede Seite ist eine Liste von Zeilen: einfache Zeichenketten oder ``Text``.
    Fuer das Anschreiben liefert ``_paginate`` bereits die Grundlinien; alle
    uebrigen Zeilen werden von oben nach unten gesetzt.
    """
    normalized: list[list[tuple[Text, float]]] = []
    for page in pages or [[]]:
        positioned: list[tuple[Text, float]] = []
        cursor = PAGE_HEIGHT - MARGIN_TOP
        for entry in page:
            if isinstance(entry, tuple):
                item, baseline = entry
            else:
                item = entry if isinstance(entry, Text) else Text(str(entry))
                baseline = cursor - item.gap - item.size * 0.86
                cursor -= item.height()
            positioned.append((item, baseline))
        normalized.append(positioned)
    if not normalized:
        normalized = [[]]

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
    for items in normalized:
        content = _page_content(items)
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
    street: str = "",
    zip_code: str = "",
    folder: Path | None = None,
    day: date | None = None,
    template: str | Path | None = None,
) -> Path:
    """Anschreiben als PDF im Benutzerordner ablegen und den Pfad liefern.

    Die Gestaltung kommt aus einer eigenen Textvorlage im Ordner
    ``briefvorlagen`` (siehe ``template_flow``); fehlt sie, gilt das
    eingebaute Standardlayout.
    """
    target = Path(folder) if folder else cover_letter_folder()
    target.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w\-. ]+", "", f"Anschreiben {company} {job_title}").strip()
    stem = re.sub(r"\s{2,}", " ", stem)[:70] or "Anschreiben"
    stamp = (day or date.today()).isoformat()
    path = target / f"{stem} {stamp}.pdf"
    flow = _flow_from_template(
        profile,
        job_title,
        company,
        letter,
        city=city,
        street=street,
        zip_code=zip_code,
        day=day,
        template=template,
    )
    path.write_bytes(build_pdf(_paginate(flow)))  # type: ignore[arg-type]
    return path


# ----------------------------------------------------------------------
# Eigene Anschreiben-Vorlagen
# ----------------------------------------------------------------------
LETTER_TEMPLATE_SUFFIXES = {".txt", ".md"}
DEFAULT_TEMPLATE_NAME = "standard.txt"

# Die Vorlage ist der ganze Brief: Absender, Empfaenger, Datum, Betreff und
# Text. Leerzeilen bestimmen die Abstände, damit der Empfaengerblock dort
# sitzt, wo das Fenster des Couverts ist. Zeilen mit # sind nur Notizen.
DEFAULT_LETTER_TEMPLATE = """# AutoApplication — Anschreiben-Vorlage (frei anpassbar)
#
# Alles, was hier steht, kommt ins PDF. Zeilen mit # am Anfang sind Notizen
# und werden nicht gedruckt. Leerzeilen bestimmen die Abstände; mehrere
# Leerzeilen am Anfang schieben den Brief nach unten.
#
# Platzhalter (werden beim Erzeugen ersetzt):
#   {vorname} {nachname} {name} {strasse} {plz} {wohnort} {telefon} {email}
#   {firma} {firma_strasse} {firma_plz_ort} {ort} {titel} {betreff}
#   {datum} {ort_datum}
#   {verfuegbar} {erfahrung} {erfahrung_spedition}
#   {text}   der ganze Brieftext; beginnt mit der Anrede und endet ohne
#            Schlussformel — die steht hier in der Vorlage
#
# Zusätze am Zeilenanfang:
#   {fett}   diese Zeile fett setzen (z. B. Betreff)
#   {rechts} diese Zeile rechtsbündig setzen (z. B. Ort und Datum)

{vorname} {nachname}
{strasse}
{plz} {wohnort}
{telefon} · {email}

{firma}
{firma_strasse}
{firma_plz_ort}

{rechts} {ort_datum}

{fett} {betreff}

{text}

Freundliche Grüsse


{vorname} {nachname}
"""


def letter_template_folder() -> Path:
    return app_home() / "briefvorlagen"


def ensure_default_letter_template(folder: Path | None = None) -> Path:
    """Beispielvorlage anlegen, wenn der Ordner noch keine enthaelt."""
    target = Path(folder) if folder else letter_template_folder()
    target.mkdir(parents=True, exist_ok=True)
    existing = list_letter_templates(target)
    if existing:
        return existing[0]
    path = target / DEFAULT_TEMPLATE_NAME
    path.write_text(DEFAULT_LETTER_TEMPLATE, encoding="utf-8")
    return path


def list_letter_templates(folder: Path | None = None) -> list[Path]:
    """Alle Vorlagen im Ordner, alphabetisch."""
    root = Path(folder) if folder else letter_template_folder()
    if not root.is_dir():
        return []
    return sorted(
        (
            path
            for path in root.iterdir()
            if path.is_file()
            and path.suffix.lower() in LETTER_TEMPLATE_SUFFIXES
            and not path.name.startswith(".")
        ),
        key=lambda path: path.name.lower(),
    )


def read_letter_template(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def resolve_letter_template(value: str | Path | None = None) -> Path:
    """Gewaehlte Vorlage als Pfad - Dateiname im Ordner oder voller Pfad."""
    name = str(value or "").strip()
    if name:
        candidate = Path(name).expanduser()
        if candidate.is_file():
            return candidate
        in_folder = letter_template_folder() / name
        if in_folder.is_file():
            return in_folder
    return ensure_default_letter_template()


_MARK_BOLD = "{fett}"
_MARK_RIGHT = "{rechts}"
_PLACEHOLDER = re.compile(r"\{([A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df_][A-Za-z\u00c4\u00d6\u00dc\u00e4\u00f6\u00fc\u00df0-9_ ]*)\}")


def template_values(
    profile: dict[str, Any],
    job_title: str = "",
    company: str = "",
    letter: str = "",
    *,
    city: str = "",
    street: str = "",
    zip_code: str = "",
    day: date | None = None,
) -> dict[str, str]:
    """Werte fuer die Platzhalter der Vorlage."""
    day = day or date.today()
    stamp = day.strftime("%d.%m.%Y")
    place = _text(profile.get("wohnort"))
    subject = " ".join(
        part for part in ("Bewerbung als", _text(job_title)) if part
    ).strip()
    return {
        "vorname": _text(profile.get("vorname")),
        "nachname": _text(profile.get("nachname")),
        "name": _name(profile),
        "strasse": _text(profile.get("strasse")),
        "plz": _text(profile.get("plz")),
        "wohnort": place,
        "telefon": _text(profile.get("telefon")),
        "email": _text(profile.get("email")),
        "firma": _text(company),
        "firma_strasse": _text(street),
        "firma_plz_ort": " ".join(
            part for part in (_text(zip_code), _text(city)) if part
        ),
        "ort": _text(city),
        "titel": _text(job_title),
        "betreff": subject,
        "datum": stamp,
        "ort_datum": f"{place}, {stamp}" if place else stamp,
        "verfuegbar": _text(profile.get("verfuegbar")),
        "erfahrung": _text(profile.get("erfahrung_jahre")),
        "erfahrung_spedition": _text(profile.get("erfahrung_spedition")),
        "text": letter,
    }


def _fill(line: str, values: dict[str, str]) -> str:
    """Bekannte Platzhalter ersetzen, unbekannte stehen lassen."""
    return _PLACEHOLDER.sub(
        lambda match: values.get(match.group(1).strip().lower(), match.group(0)), line
    )


def _body_paragraphs(letter: str) -> list[str]:
    body, _closing = split_signature(letter)
    return [" ".join(block.split()) for block in body if block.strip()]


def missing_address_placeholders(template: str | Path | None = None) -> list[str]:
    """Anschrift-Platzhalter, die in der gewaehlten Vorlage fehlen."""
    try:
        source = read_letter_template(resolve_letter_template(template))
    except OSError as exc:
        log.warning("Anschreiben-Vorlage nicht lesbar: %s", exc)
        return []
    lowered = source.lower()
    missing: list[str] = []
    if "{firma_strasse}" not in lowered:
        missing.append("Strasse")
    if "{firma_plz_ort}" not in lowered:
        missing.append("PLZ und Ort")
    return missing


def template_flow(template: str, values: dict[str, str]) -> list[Text]:
    """Vorlage Zeile fuer Zeile in den Satzablauf des PDF uebertragen."""
    source = template or ""
    flow: list[Text] = []
    used_text = False
    # Steckt der Ort schon in {firma_plz_ort}, waere eine eigene {ort}-Zeile
    # doppelt; sie faellt weg, damit die Stadt nur einmal im Brief steht.
    drop_plain_city = "{firma_plz_ort}" in source.lower()
    for raw in source.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("#"):
            continue
        bold = line.startswith(_MARK_BOLD)
        if bold:
            line = line[len(_MARK_BOLD) :].lstrip()
        align = "left"
        if line.startswith(_MARK_RIGHT):
            align = "right"
            line = line[len(_MARK_RIGHT) :].lstrip()
        if not line.strip():
            flow.append(Text("", FONT_SIZE))
            continue
        if drop_plain_city and re.fullmatch(r"\{ort\}\s*[.,]?", line.strip()):
            continue
        if "{text}" in line:
            used_text = True
            before, _, after = line.partition("{text}")
            if before.strip():
                flow.append(
                    Text(_fill(before, values).strip(), FONT_SIZE, bold=bold, align=align)
                )
            for index, paragraph in enumerate(_body_paragraphs(values.get("text", ""))):
                for position, wrapped in enumerate(_wrap(paragraph)):
                    flow.append(
                        Text(wrapped, FONT_SIZE, gap=12.0 if position == 0 and index else 0.0)
                    )
            if after.strip():
                flow.append(
                    Text(_fill(after, values).strip(), FONT_SIZE, bold=bold, align=align)
                )
            continue
        for wrapped in _wrap(_fill(line, values), FONT_SIZE):
            flow.append(Text(wrapped, FONT_SIZE, bold=bold, align=align))
    if not used_text:
        # Vorlage ohne {text}: den Brieftext trotzdem setzen, statt ihn zu verlieren.
        log.warning("Anschreiben-Vorlage ohne Platzhalter {text}")
        for index, paragraph in enumerate(_body_paragraphs(values.get("text", ""))):
            for position, wrapped in enumerate(_wrap(paragraph)):
                flow.append(
                    Text(wrapped, FONT_SIZE, gap=12.0 if position == 0 and index else 0.0)
                )
    return flow


def _flow_from_template(
    profile: dict[str, Any],
    job_title: str,
    company: str,
    letter: str,
    *,
    city: str = "",
    street: str = "",
    zip_code: str = "",
    day: date | None = None,
    template: str | Path | None = None,
) -> list[Text]:
    """Satzablauf aus der gewaehlten Vorlage; bei Lesefehler das Standardlayout."""
    values = template_values(
        profile,
        job_title,
        company,
        letter,
        city=city,
        street=street,
        zip_code=zip_code,
        day=day,
    )
    try:
        source = read_letter_template(resolve_letter_template(template))
    except OSError as exc:
        log.warning("Anschreiben-Vorlage nicht lesbar, Standardlayout: %s", exc)
        return letter_flow(
            profile,
            job_title,
            company,
            letter,
            city=city,
            street=street,
            zip_code=zip_code,
            day=day,
        )
    return template_flow(source, values)


def write_template_preview(
    template: str | Path | None = None, folder: Path | None = None
) -> Path:
    """PDF, in dem die Platzhalter selbst an ihrem Platz stehen.

    Damit laesst sich die Vorlage gestalten: Das PDF zeigt jeden Platzhalter
    dort, wo beim echten Anschreiben der Wert steht.
    """
    source_path = resolve_letter_template(template)
    keys = (
        "vorname",
        "nachname",
        "name",
        "strasse",
        "plz",
        "wohnort",
        "telefon",
        "email",
        "firma",
        "firma_strasse",
        "firma_plz_ort",
        "ort",
        "titel",
        "betreff",
        "datum",
        "ort_datum",
        "verfuegbar",
        "erfahrung",
        "erfahrung_spedition",
    )
    values = {key: "{" + key + "}" for key in keys}
    values["text"] = "{text}"
    flow = template_flow(read_letter_template(source_path), values)
    target = Path(folder) if folder else letter_template_folder()
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"Vorschau {source_path.stem}.pdf"
    path.write_bytes(build_pdf(_paginate(flow)))  # type: ignore[arg-type]
    return path
