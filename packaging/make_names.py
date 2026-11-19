"""Erzeugt die Namenslisten aus der amtlichen Schweizer Statistik.

Quelle: Bundesamt für Statistik (BFS), Vornamen und Nachnamen der
ständigen Wohnbevölkerung, 2025. Lizenz OPEN-BY: freie Nutzung,
Quellenangabe ist Pflicht.

Aufruf (Entwicklungsrechner, braucht Netzzugang):

    python packaging/make_names.py

Die Rohdateien sind Langformat (ein Wert je Name und Jahrgang bzw.
Sprachregion). Geschrieben werden zwei kompakte CSV-Dateien im Datenordner
des Programms:

* ``vornamen.csv``  - ``Name;maennlich;weiblich``
* ``nachnamen.csv`` - ``Name;Anzahl``

Seltene Namen fallen weg: Bei Vornamen unter fünf, bei Nachnamen unter zehn
Personen ist die Zuordnung ohnehin nicht belastbar.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "autoapplication" / "data"

BASE = "https://dam-api.bfs.admin.ch/hub/api/dam/assets"
SOURCES = {
    "male": f"{BASE}/36752513/master",  # Männliche Vornamen nach Jahrgang 2025
    "female": f"{BASE}/36752506/master",  # Weibliche Vornamen nach Jahrgang 2025
    "last": f"{BASE}/36752522/master",  # Nachnamen nach Sprachregion 2025
}
PAGES = {
    "male": "https://www.bfs.admin.ch/asset/de/ts-x-01.04.00.11",
    "female": "https://www.bfs.admin.ch/asset/de/ts-x-01.04.00.10",
    "last": "https://www.bfs.admin.ch/asset/de/ts-x-01.04.00.16",
}

FIRST_MIN = 5
LAST_MIN = 10


def read_rows(url: str) -> list[dict[str, str]]:
    with urllib.request.urlopen(url, timeout=120) as response:
        raw = response.read().decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))


def sum_by(rows: list[dict[str, str]], key: str) -> Counter[str]:
    totals: Counter[str] = Counter()
    for row in rows:
        name = (row.get(key) or "").strip()
        if not name:
            continue
        try:
            totals[name] += int(float(row.get("VALUE") or 0))
        except ValueError:
            continue
    return totals


def write_first_names(male: Counter[str], female: Counter[str]) -> int:
    names = sorted(
        name
        for name in set(male) | set(female)
        if male[name] + female[name] >= FIRST_MIN
    )
    path = DATA / "vornamen.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# Quelle: Bundesamt fuer Statistik (BFS), Vornamen der Bevoelkerung\n")
        handle.write("# nach Geschlecht, Schweiz, 2025 (OPEN-BY, Quellenangabe Pflicht).\n")
        handle.write(f"# {PAGES['male']}\n# {PAGES['female']}\n")
        handle.write("# Name;maennlich;weiblich\n")
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        for name in names:
            writer.writerow([name, male[name], female[name]])
    return len(names)


def write_last_names(totals: Counter[str]) -> int:
    names = sorted(name for name, count in totals.items() if count >= LAST_MIN)
    path = DATA / "nachnamen.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# Quelle: Bundesamt fuer Statistik (BFS), Nachnamen der staendigen\n")
        handle.write("# Wohnbevoelkerung nach Sprachregion, Schweiz, 2025 (OPEN-BY).\n")
        handle.write(f"# {PAGES['last']}\n")
        handle.write("# Name;Anzahl\n")
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        for name in names:
            writer.writerow([name, totals[name]])
    return len(names)


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    male = sum_by(read_rows(SOURCES["male"]), "firstname")
    female = sum_by(read_rows(SOURCES["female"]), "firstname")
    last = sum_by(read_rows(SOURCES["last"]), "LASTNAME")
    print(f"Vornamen: {write_first_names(male, female)}")
    print(f"Nachnamen: {write_last_names(last)}")


if __name__ == "__main__":
    main()
