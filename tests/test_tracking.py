"""Tests fuer die einmalige Kennung, die in der Mail mitreist."""

from __future__ import annotations

from autoapplication.core.tracking import ALPHABET, find_code, html_body, new_code


def test_code_has_fixed_shape() -> None:
    code = new_code()
    assert code.startswith("AA-")
    assert len(code) == 17  # AA- plus drei Gruppen zu vier Zeichen
    assert all(character in ALPHABET or character == "-" for character in code.replace("AA-", "", 1))
    assert find_code(code) == code


def test_codes_are_distinct() -> None:
    codes = {new_code() for _ in range(200)}
    assert len(codes) == 200


def test_taken_code_is_avoided() -> None:
    first = new_code()
    second = new_code(lambda value: value == first)
    assert second != first


def test_find_code_reads_quoted_mail() -> None:
    quoted = (
        "<blockquote><div style=\"font-size:0;color:#ffffff\">"
        "AutoApplication-Referenz aa-7k4p-q9xm-3trz</div></blockquote>"
    )
    assert find_code(quoted) == "AA-7K4P-Q9XM-3TRZ"
    assert find_code("Ohne Kennung") == ""
    assert find_code(None) == ""


def test_html_body_hides_code_at_the_end() -> None:
    code = "AA-7K4P-Q9XM-3TRZ"
    html = html_body(
        "Sehr geehrte Frau Meier,\n\nZeile eins\nZeile zwei\n\nFreundliche Grüsse", code
    )
    assert html.count("<p style=") == 3
    assert "Zeile eins<br>Zeile zwei" in html
    assert "Sehr geehrte Frau Meier" in html
    assert code in html
    assert "font-size:0" in html and "color:#ffffff" in html
    assert html.rstrip().endswith(f"<!-- AutoApplication-Referenz {code} -->")
