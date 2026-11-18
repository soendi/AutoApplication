"""Unterlagen einsammeln und das Anschreiben als PDF erzeugen."""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from .config import app_home

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
# Reihenfolge der Ordner, damit Lebenslauf und Zeugnisse zuerst kommen.
PREFERRED = ("lebenslauf", "cv", "zeugnis", "zeugnisse", "diplom", "diplome", "ausweis")

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 60
TOP_Y = 780
LINE_HEIGHT = 15
FONT_SIZE = 10.5
LINES_PER_PAGE = 44
WRAP_WIDTH = 88


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


def _pdf_escape(value: str) -> bytes:
    raw = value.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _wrap(line: str, width: int = WRAP_WIDTH) -> list[str]:
    if len(line) <= width:
        return [line]
    parts: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = word
    if current:
        parts.append(current)
    return parts


def _pages(lines: list[str]) -> list[list[str]]:
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap(line))
    if not wrapped:
        wrapped = [""]
    return [
        wrapped[start : start + LINES_PER_PAGE]
        for start in range(0, len(wrapped), LINES_PER_PAGE)
    ]


def _page_content(lines: list[str]) -> bytes:
    commands = [b"BT", f"/F1 {FONT_SIZE} Tf".encode(), f"{MARGIN_X} {TOP_Y} Td".encode()]
    commands.append(f"{LINE_HEIGHT} TL".encode())
    for line in lines:
        commands.append(b"(" + _pdf_escape(line) + b") Tj T*")
    commands.append(b"ET")
    return b"\n".join(commands)


def build_pdf(pages: list[list[str]]) -> bytes:
    """Kleines PDF mit Helvetica erzeugen - ohne zusaetzliche Bibliothek."""
    if not pages:
        pages = [[""]]
    objects: dict[int, bytes] = {
        3: (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>"
        )
    }
    kids: list[int] = []
    next_id = 4
    for lines in pages:
        content = _page_content(lines)
        content_id = next_id
        next_id += 1
        page_id = next_id
        next_id += 1
        objects[content_id] = (
            f"<< /Length {len(content)} >>\nstream\n".encode()
            + content
            + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
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


def letter_lines(
    profile: dict[str, Any],
    job_title: str,
    company: str,
    letter: str,
    *,
    day: date | None = None,
) -> list[str]:
    """Kopf, Empfaenger, Datum und Betreff um den Anschreiben-Text legen."""
    day = day or date.today()
    sender = [
        " ".join(
            part
            for part in (
                str(profile.get("vorname") or "").strip(),
                str(profile.get("nachname") or "").strip(),
            )
            if part
        ),
        str(profile.get("strasse") or "").strip(),
        " ".join(
            part
            for part in (
                str(profile.get("plz") or "").strip(),
                str(profile.get("wohnort") or "").strip(),
            )
            if part
        ),
        str(profile.get("telefon") or "").strip(),
        str(profile.get("email") or "").strip(),
    ]
    lines = [line for line in sender if line]
    lines.append("")
    if company:
        lines.extend([company.strip(), ""])
    lines.append(day.strftime("%d.%m.%Y"))
    lines.append("")
    subject = " ".join(part for part in ("Bewerbung als", job_title) if part).strip()
    if subject:
        lines.extend([subject, ""])
    lines.extend(letter.splitlines())
    return lines


def write_cover_letter(
    profile: dict[str, Any],
    job_title: str,
    company: str,
    letter: str,
    *,
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
    path.write_bytes(build_pdf(_pages(letter_lines(profile, job_title, company, letter, day=day))))
    return path
