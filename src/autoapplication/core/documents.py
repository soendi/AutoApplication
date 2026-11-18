"""Unterlagen einsammeln, die an eine Bewerbung gehaengen werden."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

SUPPORTED = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png"}
# Reihenfolge der Ordner, damit Lebenslauf und Zeugnisse zuerst kommen.
PREFERRED = ("lebenslauf", "cv", "zeugnis", "zeugnisse", "diplom", "diplome", "ausweis")


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
