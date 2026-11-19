from __future__ import annotations

from autoapplication.core import pdf


def test_pdf_urls_are_made_absolute() -> None:
    html = (
        '<a href="//barberry.ostjob.ch/c89.pdf">Stellenausschreibung</a>'
        '<a href="/files/stelle.pdf?x=1">PDF</a>'
        "Siehe https://example.ch/anzeige.pdf"
    )
    assert pdf.pdf_urls(html, "https://www.ostjob.ch/job/1") == [
        "https://barberry.ostjob.ch/c89.pdf",
        "https://www.ostjob.ch/files/stelle.pdf?x=1",
        "https://example.ch/anzeige.pdf",
    ]


def test_pdf_urls_ignores_other_links() -> None:
    assert pdf.pdf_urls('<a href="/kontakt">Kontakt</a>', "https://x.ch") == []
    assert pdf.pdf_urls("", "") == []


def test_text_from_html_reads_the_pdf() -> None:
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        return b"%PDF-1.7"

    text = pdf.text_from_html(
        '<a href="//host.ch/a.pdf">Ausschreibung</a>',
        "https://ostjob.ch/job/1",
        fetch=fetch,
        read=lambda data: "Herr Yves Scheliesnig, HR@optiprint.ch",
    )
    assert seen == ["https://host.ch/a.pdf"]
    assert "Yves Scheliesnig" in text


def test_text_from_html_survives_a_broken_pdf() -> None:
    def fetch(url: str) -> bytes:
        raise OSError("weg")

    assert (
        pdf.text_from_html(
            '<a href="https://host.ch/a.pdf">PDF</a>',
            fetch=fetch,
            read=lambda data: "",
        )
        == ""
    )


def test_extract_text_survives_data_that_is_no_pdf() -> None:
    assert pdf.extract_text(b"kein pdf") == ""
