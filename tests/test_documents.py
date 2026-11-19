from __future__ import annotations

from datetime import date

from autoapplication.core.documents import (
    collect,
    describe,
    ensure_default_letter_template,
    list_letter_templates,
    template_flow,
    write_cover_letter,
    write_template_preview,
)
from autoapplication.core.text import format_workload, haversine_km, parse_date


def test_collect_sorts_cv_first_and_skips_other_files(tmp_path) -> None:
    (tmp_path / "zeugnisse").mkdir()
    (tmp_path / "zeugnisse" / "zeugnis_2024.pdf").write_bytes(b"x")
    (tmp_path / "lebenslauf.pdf").write_bytes(b"x")
    (tmp_path / "notiz.txt").write_bytes(b"x")
    (tmp_path / ".versteckt.pdf").write_bytes(b"x")
    files = collect(tmp_path)
    names = [path.name for path in files]
    assert names[0] == "lebenslauf.pdf"
    assert "zeugnis_2024.pdf" in names
    assert "notiz.txt" not in names
    assert ".versteckt.pdf" not in names


def test_collect_limits_total_size(tmp_path) -> None:
    (tmp_path / "gross.pdf").write_bytes(b"0" * (2 * 1024 * 1024))
    (tmp_path / "klein.pdf").write_bytes(b"0" * 1024)
    files = collect(tmp_path, max_mb=1)
    # Die zu grosse Datei faellt weg, die kleine bleibt.
    assert [path.name for path in files] == ["klein.pdf"]


def test_collect_disabled_or_missing(tmp_path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"x")
    assert collect(tmp_path, enabled=False) == []
    assert collect(tmp_path / "gibt-es-nicht") == []
    assert collect("") == []


def test_describe() -> None:
    assert describe([]) == "keine Anhaenge"
    from pathlib import Path

    assert "a.pdf" in describe([Path("a.pdf"), Path("b.pdf")])


def test_format_workload() -> None:
    assert format_workload(100, 100) == "100 %"
    assert format_workload(80, 100) == "80-100 %"
    assert format_workload(0, 0) == ""
    assert format_workload(100, 80) == "80-100 %"


def test_haversine() -> None:
    distance = haversine_km(47.4055, 9.6087, 47.4912, 9.5555)
    assert distance is not None
    assert 8 < distance < 12
    assert haversine_km("x", 9.6, 47.4, 9.6) is None


def test_letter_template_places_placeholders(tmp_path) -> None:
    template = tmp_path / "eigene.txt"
    template.write_text(
        "{vorname} {nachname}\n{strasse}\n\n{firma}\n{ort}\n\n"
        "{rechts} {ort_datum}\n\n{fett} {betreff}\n\n{text}\n\n"
        "Freundliche Grüsse\n\n\n{vorname} {nachname}\n",
        encoding="utf-8",
    )
    profile = {
        "vorname": "Max",
        "nachname": "Muster",
        "strasse": "Dorfstrasse 1",
        "plz": "9436",
        "wohnort": "Balgach",
        "verfuegbar": "sofort",
    }
    path = write_cover_letter(
        profile,
        "Lagermitarbeiter",
        "Muster AG",
        "Sehr geehrte Damen und Herren\n\nIch bewerbe mich.\n\n"
        "Freundliche Grüsse\nMax Muster",
        city="St. Gallen",
        folder=tmp_path / "out",
        day=date(2026, 11, 19),
        template=template,
    )
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"Bewerbung als Lagermitarbeiter" in data
    assert b"Muster AG" in data
    assert b"Ich bewerbe mich." in data
    # Schlussformel und Name kommen aus der Vorlage, nicht doppelt aus dem Text:
    # einmal Absenderblock oben, einmal als Unterschrift.
    assert data.count(b"Freundliche Gr\xfcsse") == 1
    assert data.count(b"Max Muster") == 2


def test_template_preview_shows_placeholders(tmp_path) -> None:
    template = tmp_path / "vorlage.txt"
    template.write_text(
        "{vorname} {nachname}\n{firma}\n\n{fett} {betreff}\n\n{text}\n",
        encoding="utf-8",
    )
    path = write_template_preview(template, folder=tmp_path / "vorschau")
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    assert b"{vorname}" in data
    assert b"{firma}" in data
    assert b"{betreff}" in data
    assert b"{text}" in data


def test_letter_templates_are_listed_and_default_created(tmp_path) -> None:
    folder = tmp_path / "briefvorlagen"
    first = ensure_default_letter_template(folder)
    assert first.name == "standard.txt"
    (folder / "zweite.txt").write_text("{text}", encoding="utf-8")
    (folder / "notiz.pdf").write_bytes(b"x")
    names = [path.name for path in list_letter_templates(folder)]
    assert names == ["standard.txt", "zweite.txt"]
    # Ein vorhandener Bestand bleibt unangetastet.
    assert ensure_default_letter_template(folder) == first


def test_template_without_text_placeholder_keeps_the_letter_body() -> None:
    flow = template_flow(
        "Hallo\n{firma}\n",
        {
            "firma": "Muster AG",
            "text": "Sehr geehrte Damen und Herren\n\nIch bewerbe mich.\n\n"
            "Freundliche Grüsse\nMax Muster",
        },
    )
    joined = " ".join(item.text for item in flow)
    assert "Muster AG" in joined
    assert "Ich bewerbe mich." in joined
    assert "Freundliche Grüsse" not in joined


def test_parse_date_variants() -> None:
    assert parse_date("2026-11-18").isoformat() == "2026-11-18"
    assert parse_date("18.11.2026").isoformat() == "2026-11-18"
    assert parse_date("2026-07-30T15:06:55.000+02:00").isoformat() == "2026-07-30"
    assert parse_date("2026-11-06 15:06:55.000000+0200").isoformat() == "2026-11-06"
    assert parse_date("") is None
    assert parse_date("kein Datum") is None


def test_cover_letter_prints_recipient_street_and_postcode(tmp_path) -> None:
    from autoapplication.core.documents import DEFAULT_LETTER_TEMPLATE

    template = tmp_path / "standard.txt"
    template.write_text(DEFAULT_LETTER_TEMPLATE, encoding="utf-8")
    path = write_cover_letter(
        {"vorname": "Max", "nachname": "Muster", "wohnort": "Balgach"},
        "Lagermitarbeiter",
        "Muster Logistik AG",
        "Sehr geehrte Damen und Herren\n\nIch bewerbe mich.\n\n"
        "Freundliche Grüsse\nMax Muster",
        city="Balgach",
        street="Bahnhofstrasse 12",
        zip_code="9436",
        folder=tmp_path / "out",
        day=date(2026, 11, 19),
        template=template,
    )
    data = path.read_bytes()
    assert b"Muster Logistik AG" in data
    assert b"Bahnhofstrasse 12" in data
    assert b"9436 Balgach" in data


def test_cover_letter_without_street_leaves_the_line_out(tmp_path) -> None:
    from autoapplication.core.documents import DEFAULT_LETTER_TEMPLATE

    template = tmp_path / "standard.txt"
    template.write_text(DEFAULT_LETTER_TEMPLATE, encoding="utf-8")
    path = write_cover_letter(
        {"vorname": "Max", "nachname": "Muster", "wohnort": "Balgach"},
        "Lagermitarbeiter",
        "Muster Logistik AG",
        "Sehr geehrte Damen und Herren\n\nText.\n\nFreundliche Grüsse\nMax Muster",
        city="Balgach",
        folder=tmp_path / "out",
        day=date(2026, 11, 19),
        template=template,
    )
    # Keine Strasse, keine leere Zeile mitten im Empfaengerblock.
    assert b"Muster Logistik AG" in path.read_bytes()


def test_template_prints_city_only_once() -> None:
    flow = template_flow(
        "{firma}\n{firma_plz_ort}\n{ort}\n\n{text}\n",
        {
            "firma": "Muster AG",
            "firma_plz_ort": "9436 Balgach",
            "ort": "Balgach",
            "text": "Text",
        },
    )
    texts = [item.text for item in flow if item.text]
    assert sum("Balgach" in text for text in texts) == 1
    # Ohne {firma_plz_ort} bleibt die eigene Ortszeile stehen.
    flow = template_flow(
        "{firma}\n{ort}\n",
        {"firma": "Muster AG", "ort": "Balgach", "text": ""},
    )
    assert [item.text for item in flow if item.text] == ["Muster AG", "Balgach"]


def test_missing_address_placeholders_are_reported(tmp_path) -> None:
    from autoapplication.core.documents import missing_address_placeholders

    old = tmp_path / "alt.txt"
    old.write_text("{firma}\n{ort}\n\n{text}\n", encoding="utf-8")
    assert missing_address_placeholders(old) == ["Strasse", "PLZ und Ort"]

    only_street = tmp_path / "teil.txt"
    only_street.write_text("{firma}\n{firma_strasse}\n{ort}\n", encoding="utf-8")
    assert missing_address_placeholders(only_street) == ["PLZ und Ort"]

    full = tmp_path / "neu.txt"
    full.write_text("{firma}\n{firma_strasse}\n{firma_plz_ort}\n", encoding="utf-8")
    assert missing_address_placeholders(full) == []
