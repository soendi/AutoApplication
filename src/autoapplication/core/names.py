"""Vor- und Nachnamen aus der amtlichen Schweizer Namensstatistik.

Die Listen stammen vom Bundesamt fuer Statistik (BFS): Vornamen der
Bevoelkerung nach Geschlecht und Nachnamen der staendigen Wohnbevoelkerung,
Schweiz 2025 (OPEN-BY, Quellenangabe Pflicht). Sie liegen als CSV im
Datenordner und werden beim ersten Gebrauch gelesen.

Damit laesst sich ein Name ohne Anrede einordnen: welcher Teil der Vorname
und welcher der Nachname ist, und - bei eindeutiger Verteilung - ob die
Person mit Herr oder Frau anzusprechen ist. Geraten wird nichts: Ist ein
Vorname beiden Geschlechtern zugeordnet (etwa Andrea oder Simone), bleibt
das Geschlecht leer und die Anrede allgemein.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

FIRST_NAMES_FILE = "vornamen.csv"
LAST_NAMES_FILE = "nachnamen.csv"

# Anteil einer Seite, ab dem die Zuordnung als eindeutig gilt. Bei 95 Prozent
# bleibt fuer den anderen Fall hoechstens jeder zwanzigste Namenstraeger.
MIN_SHARE = 0.95
MIN_COUNT = 5

_TITLES = {
    "dr",
    "prof",
    "dipl",
    "lic",
    "iur",
    "ing",
    "med",
    "phil",
    "rer",
    "nat",
    "hc",
    "mba",
    "msc",
    "bsc",
}

# Namenszusätze, die zum Nachnamen gehören ("van der Berg", "de la Cruz").
_PARTICLES = {
    "von",
    "van",
    "de",
    "der",
    "den",
    "dem",
    "des",
    "di",
    "da",
    "del",
    "della",
    "dei",
    "dos",
    "das",
    "du",
    "la",
    "le",
    "zu",
    "zur",
    "ten",
    "ter",
    "te",
    "bin",
    "al",
}


@dataclass(frozen=True)
class PersonName:
    """Zerlegter Name: Vorname, Nachname und Geschlecht ("m", "f" oder "")."""

    first: str = ""
    last: str = ""
    gender: str = ""

    def __bool__(self) -> bool:
        return bool(self.first or self.last)


def data_directory() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


_first_names: dict[str, tuple[int, int]] | None = None
_last_names: set[str] | None = None


def _rows(path: Path) -> Iterator[list[str]]:
    """Zeilen einer Liste lesen; Kommentarzeilen mit der Quelle entfallen."""
    with path.open(encoding="utf-8", newline="") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip() or line.startswith("#"):
                continue
            yield line.split(";")


def _load_first_names() -> dict[str, tuple[int, int]]:
    global _first_names
    if _first_names is None:
        table: dict[str, tuple[int, int]] = {}
        try:
            rows = _rows(data_directory() / FIRST_NAMES_FILE)
            next(rows, None)  # Kopfzeile
            for row in rows:
                if len(row) < 3:
                    continue
                try:
                    table[row[0].strip().casefold()] = (int(row[1]), int(row[2]))
                except ValueError:
                    continue
        except OSError:
            # Ohne Liste bleibt die Einordnung leer; die App laeuft weiter.
            table = {}
        _first_names = table
    return _first_names


def _load_last_names() -> set[str]:
    global _last_names
    if _last_names is None:
        names: set[str] = set()
        try:
            rows = _rows(data_directory() / LAST_NAMES_FILE)
            next(rows, None)  # Kopfzeile
            for row in rows:
                if row and row[0].strip():
                    names.add(row[0].strip().casefold())
        except OSError:
            names = set()
        _last_names = names
    return _last_names


def gender_of(first_name: str | None) -> str:
    """Geschlecht eines Vornamens: "m", "f" oder "" bei unklarer Lage."""
    key = re.sub(r"\s+", " ", str(first_name or "")).strip().casefold()
    if not key:
        return ""
    counts = _load_first_names().get(key)
    if not counts:
        return ""
    male, female = counts
    total = male + female
    if total < MIN_COUNT:
        return ""
    if male / total >= MIN_SHARE:
        return "m"
    if female / total >= MIN_SHARE:
        return "f"
    return ""


def is_first_name(value: str | None) -> bool:
    key = str(value or "").strip().casefold()
    return bool(key) and key in _load_first_names()


def is_last_name(value: str | None) -> bool:
    key = str(value or "").strip().casefold()
    return bool(key) and key in _load_last_names()


def _strip_titles(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens) - 1 and tokens[index].rstrip(".").casefold() in _TITLES:
        index += 1
    return tokens[index:]


def split_person_name(value: str | None) -> PersonName:
    """Einen Namen in Vorname und Nachname teilen.

    Versteht "Steven Müller", "Müller, Steven", akademische Titel und
    Namenszusätze wie "van der Berg". Das Geschlecht stammt aus der
    Vornamensliste und bleibt leer, wenn der Vorname fehlt oder nicht
    eindeutig ist.
    """
    text = re.sub(r"\s+", " ", str(value or "")).strip(" .,;:–-")
    # Adressen, Nummern und Kennungen sind keine Namen.
    if not text or "@" in text or any(char.isdigit() for char in text):
        return PersonName()

    if "," in text:
        left, right = text.split(",", 1)
        last = " ".join(_strip_titles(left.split()))
        first = " ".join(_strip_titles(right.split()))
        if not (first and last):
            return PersonName()
        return PersonName(first=first, last=last, gender=gender_of(first.split()[0]))

    tokens = _strip_titles(text.split())
    if not tokens or len(tokens) > 6:
        return PersonName()
    if len(tokens) == 1:
        token = tokens[0]
        if is_first_name(token):
            return PersonName(first=token)
        if is_last_name(token):
            return PersonName(last=token)
        return PersonName()

    index = len(tokens) - 1
    while index - 1 > 0 and tokens[index - 1].casefold() in _PARTICLES:
        index -= 1
    last = " ".join(tokens[index:])
    first = " ".join(tokens[:index])
    if not last:
        return PersonName()
    return PersonName(first=first, last=last, gender=gender_of(first.split()[0]))
