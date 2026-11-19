from __future__ import annotations

from autoapplication.core.text import contact_name, contact_person, strip_html


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
