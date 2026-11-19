from __future__ import annotations

from autoapplication.core.text import (
    contact_name,
    contact_person,
    person_name,
    strip_html,
)


def test_commented_out_contact_is_not_used() -> None:
    page = (
        "<p>Kontakt: Claudio Zai, Teamleiter</p>"
        "<!--\nFrau Annina Sulser\nannina.sulser@sg.ch\n-->"
    )
    cleaned = strip_html(page)
    assert "Claudio Zai" in cleaned
    assert "Sulser" not in cleaned
    assert "annina.sulser@sg.ch" not in cleaned


def test_contact_name_without_salutation() -> None:
    value = (
        "Weitere Auskünfte unter: Claudio Zai,\u00a0Teamleiter RAV Heerbrugg "
        "(Tel. 058 229 97 25) sowie unter www.awa.sg.ch"
    )
    assert contact_name(value) == "Claudio Zai"
    assert contact_person(value) == ""


def test_contact_name_ignores_generic_answers() -> None:
    assert contact_name("Kontakt: Team Personal") == ""
    assert contact_name("Kontakt: RAV Heerbrugg") == ""
    assert contact_name("Ohne Kontaktangabe: Claudio Zai") == ""


def test_contact_name_reads_person_after_ansprechperson() -> None:
    value = (
        "Deine Ansprechperson\nKevin Verling\nKevin Verling\n"
        "Recruiting Consultant\n+423 375 87 02\nverling@avoris.li\n"
        "avoris Personal AG · Im alten Riet 153 · 9494 Schaan"
    )
    assert contact_name(value) == "Kevin Verling"


def test_contact_name_after_role() -> None:
    value = (
        "Trete mit uns in Kontakt - wir freuen uns dich kennenzulernen\n\n"
        "Sende unserem Personalleiter, Steven Müller, gerne deine "
        "vollständigen Bewerbungsunterlagen per E-Mail an: "
        "HR@zuendoptics.com\n"
        "Für fachliche Fragen steht dir unser Produktionsleiter, "
        "Nicolas Seitz, telefonisch unter der Nummer +41 71 737 74 07 "
        "gerne zur Verfügung."
    )
    assert contact_name(value) == "Steven Müller"


def test_salutation_options_do_not_become_a_person() -> None:
    page = (
        "<select><option>Herr</option><option>Frau</option>"
        "<option>Divers</option></select>"
        "<p>Deine Ansprechperson</p><p>Kevin Verling</p>"
    )
    cleaned = strip_html(page)
    assert "Frau Divers" not in cleaned
    assert contact_person(cleaned) == ""
    assert contact_name(cleaned) == "Kevin Verling"


def test_person_name_validation() -> None:
    assert person_name("Kevin Verling") == "Kevin Verling"
    assert person_name("Frau Annina Sulser") == "Frau Sulser"
    assert person_name("wir freuen uns") == ""
    assert person_name("Kevin") == ""
    assert person_name("Team RAV Heerbrugg") == ""
