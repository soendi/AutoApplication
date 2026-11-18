from __future__ import annotations

from autoapplication.core.text import clean_job_text, clean_job_title, masculine_form


def test_gender_markers_are_removed() -> None:
    assert clean_job_title("Speditionskaufmann (m/w/d)") == "Speditionskaufmann"
    assert clean_job_title("Lagermitarbeiter (gn*)") == "Lagermitarbeiter"
    assert clean_job_title("Sachbearbeiterin (w/m/d)") == "Sachbearbeiter"
    assert clean_job_title("Mitarbeiter*in Logistik") == "Mitarbeiter Logistik"
    assert clean_job_title("Kauffrau (all genders)") == "Kaufmann"
    assert clean_job_title("Disponent m/w/d") == "Disponent"


def test_provider_ids_are_removed() -> None:
    assert clean_job_title("Disponent (Job-ID: 123456)") == "Disponent"
    assert clean_job_title("Verkäufer #987654") == "Verkäufer"
    assert clean_job_title("Buchhalterin (Ref. 445566)") == "Buchhalter"
    assert clean_job_title("Lagerist (2024-998877)") == "Lagerist"


def test_masculine_forms() -> None:
    assert masculine_form("Geschäftsführerin") == "Geschäftsführer"
    assert masculine_form("Köchin") == "Koch"
    assert masculine_form("Ärztin") == "Arzt"
    assert masculine_form("Speditionskauffrau") == "Speditionskaufmann"
    assert masculine_form("Mitarbeiterinnen") == "Mitarbeiter"
    assert masculine_form("Berlin") == "Berlin"


def test_description_is_cleaned() -> None:
    text = clean_job_text(
        "Wir suchen eine Lagermitarbeiterin (m/w/d).\n"
        "Referenz: 123456\n"
        "Gute Arbeit und Teamgeist."
    )
    assert "m/w/d" not in text
    assert "123456" not in text
    assert "Lagermitarbeiter" in text
    assert "Gute Arbeit" in text
