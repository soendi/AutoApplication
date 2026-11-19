from __future__ import annotations

from autoapplication.core.names import (
    gender_of,
    is_first_name,
    is_last_name,
    split_person_name,
)
from autoapplication.core.text import salutation


def test_gender_of_common_swiss_first_names() -> None:
    assert gender_of("Steven") == "m"
    assert gender_of("Annina") == "f"
    assert gender_of("Claudio") == "m"
    assert gender_of("Sandra") == "f"
    assert gender_of("steven") == "m"


def test_gender_of_ambiguous_names_stays_empty() -> None:
    # Andrea und Simone werden in der Schweiz beiden Geschlechtern gegeben.
    assert gender_of("Andrea") == ""
    assert gender_of("Simone") == ""
    assert gender_of("Unbekannt") == ""


def test_name_lists_are_loaded() -> None:
    assert is_first_name("Steven")
    assert is_last_name("Müller")
    assert not is_first_name("Müller")
    assert not is_last_name("Qwertzuiop")


def test_split_plain_name() -> None:
    person = split_person_name("Steven Müller")
    assert (person.first, person.last, person.gender) == ("Steven", "Müller", "m")


def test_split_comma_name() -> None:
    person = split_person_name("Müller, Steven")
    assert (person.first, person.last, person.gender) == ("Steven", "Müller", "m")


def test_split_name_with_title_and_particles() -> None:
    person = split_person_name("Dr. Jan van der Berg")
    assert (person.first, person.last) == ("Jan", "van der Berg")


def test_split_multiple_given_names() -> None:
    person = split_person_name("Anna Maria Müller")
    assert (person.first, person.last, person.gender) == ("Anna Maria", "Müller", "f")


def test_salutation_from_name_without_title() -> None:
    assert salutation("Steven Müller") == "Sehr geehrter Herr Müller"
    assert salutation("Annina Sulser") == "Sehr geehrte Frau Sulser"


def test_salutation_keeps_general_for_ambiguous_names() -> None:
    assert salutation("Andrea Meier") == "Sehr geehrte Damen und Herren"
    assert salutation("Müller") == "Sehr geehrte Damen und Herren"
    assert salutation("") == "Sehr geehrte Damen und Herren"


def test_addresses_and_numbers_are_not_names() -> None:
    assert salutation("info@firma.ch") == "Sehr geehrte Damen und Herren"
    assert salutation("Steven Müller 2024") == "Sehr geehrte Damen und Herren"


def test_salutation_keeps_explicit_title() -> None:
    assert salutation("Herr Müller") == "Sehr geehrter Herr Müller"
    assert salutation("Frau Meier") == "Sehr geehrte Frau Meier"
