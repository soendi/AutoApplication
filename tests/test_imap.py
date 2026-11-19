"""Tests fuer die Gmail-Anbindung per IMAP und SMTP."""

from __future__ import annotations

import imaplib
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate

import pytest

from autoapplication.core.imap_mail import GmailImapClient, ImapError

DRAFTS = b'(\\HasNoChildren \\Drafts) "/" "[Gmail]/Drafts"'
SENT = b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"'
INBOX = b'(\\HasNoChildren) "/" "INBOX"'


class FakeImap:
    """Minimaler IMAP-Ersatz fuer Anmeldung, Ordner, Suche und Fetch."""

    def __init__(self, password: str = "apppasswort", inbox=None, sent=None) -> None:
        self.password = password
        self.inbox = list(inbox or [])
        self.sent = list(sent or [])
        self.selected = b""
        self.appended: list[tuple[bytes, bytes, bytes]] = []
        self.searches: list[tuple[bytes, ...]] = []
        self.fetched: list[str] = []
        self.logged_out = False

    def login(self, user: str, password: str):
        if password != self.password:
            raise imaplib.IMAP4.error("b'[AUTHENTICATIONFAILED] Invalid credentials'")
        self.user = user
        return "OK", [b"logged in"]

    def list(self):
        return "OK", [DRAFTS, SENT, INBOX]

    def select(self, name, readonly: bool = False):
        self.selected = name
        return "OK", [b"1"]

    def append(self, folder, flags, date_time, message):
        self.appended.append((folder, flags.encode() if isinstance(flags, str) else flags, message))
        return "OK", [b"[APPENDUID 1 5]"]

    def search(self, charset, *criteria):
        self.searches.append(criteria)
        if self.selected == b"[Gmail]/Sent Mail":
            return "OK", [b"1"] if self.sent else [b""]
        numbers = b" ".join(str(i + 1).encode() for i in range(len(self.inbox)))
        return "OK", [numbers]

    def fetch(self, number, parts):
        index = int(number) - 1
        pool = self.sent if self.selected == b"[Gmail]/Sent Mail" else self.inbox
        raw = pool[index]
        self.fetched.append(str(parts))
        if "HEADER" in str(parts):
            head = raw.split(b"\n\n", 1)[0] + b"\n\n"
            return "OK", [(b"1 (BODY[HEADER] {%d}" % len(head), head), b")"]
        if "BODYSTRUCTURE" in str(parts):
            return "OK", [(
                b'1 (BODYSTRUCTURE ("TEXT" "PLAIN" ("CHARSET" "UTF-8") '
                b'NIL NIL "7BIT" 5 1 NIL NIL NIL NIL))',
                b"",
            )]
        if "BODY.PEEK[" in str(parts) and "BODY.PEEK[]" not in str(parts):
            _, _, body = raw.partition(b"\n\n")
            return "OK", [(b"1 (BODY[1] {%d}" % len(body), body), b")"]
        return "OK", [(b"1 (BODY[] {%d}" % len(raw), raw), b")"]

    def logout(self):
        self.logged_out = True
        return "BYE", [b"bye"]


class FakeSmtp:
    def __init__(self) -> None:
        self.started = False
        self.logged_in = False
        self.quit_called = False

    def starttls(self):
        self.started = True

    def login(self, user, password):
        if password != "apppasswort":
            raise __import__("smtplib").SMTPAuthenticationError(535, b"bad")
        self.logged_in = True

    def quit(self):
        self.quit_called = True


def _message(subject: str, sender: str, body: str = "Text", html: bool = False) -> bytes:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = "ich@example.com"
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = "<abc@example.com>"
    if html:
        message.set_content(body, subtype="html")
    else:
        message.set_content(body)
    return message.as_bytes()


def _client(fake: FakeImap, smtp=None) -> GmailImapClient:
    return GmailImapClient(
        "ich@example.com",
        "apppasswort",
        imap_factory=lambda: fake,
        smtp_factory=lambda: smtp or FakeSmtp(),
    )


def test_folders_are_found_by_attribute() -> None:
    client = _client(FakeImap())
    with client._imap() as connection:
        assert client._folder(connection, b"\\Drafts") == b"[Gmail]/Drafts"
        assert client._folder(connection, b"\\Sent") == b"[Gmail]/Sent Mail"


def test_create_draft_appends_message_with_attachment(tmp_path) -> None:
    fake = FakeImap()
    attachment = tmp_path / "lebenslauf.pdf"
    attachment.write_bytes(b"%PDF-1.4 test")
    client = _client(fake)
    result = client.create_draft(
        "Bewerbung als Lagerist",
        "Guten Tag",
        "firma@example.com",
        [attachment],
    )

    assert len(result["conversationId"]) == 32
    folder, flags, raw = fake.appended[0]
    assert folder == b"[Gmail]/Drafts"
    assert b"Draft" in flags
    message = BytesParser(policy=policy.default).parsebytes(raw)
    assert message["Subject"] == "Bewerbung als Lagerist"
    assert message["To"] == "firma@example.com"
    assert message["X-AutoApplication-ID"] == result["conversationId"]
    names = [part.get_filename() for part in message.iter_attachments()]
    assert names == ["lebenslauf.pdf"]
    assert message.get_body(("plain",)).get_content().strip() == "Guten Tag"
    assert fake.logged_out


def test_create_draft_embeds_tracking_invisible() -> None:
    fake = FakeImap()
    client = _client(fake)
    code = "AA-7K4P-Q9XM-3TRZ"
    result = client.create_draft(
        "Bewerbung als Lagerist", "Guten Tag", "firma@example.com", tracking=code
    )
    raw = fake.appended[0][2]
    message = BytesParser(policy=policy.default).parsebytes(raw)
    assert message["X-AutoApplication-Ref"] == code
    assert message["X-AutoApplication-ID"] == result["conversationId"]
    # Im reinen Text steht die Kennung nicht - sie soll niemandem auffallen.
    plain = message.get_body(("plain",)).get_content()
    assert "AA-7K4P" not in plain
    html = message.get_body(("html",)).get_content()
    assert code in html
    assert "font-size:0" in html and "#ffffff" in html


def test_inbox_since_reads_tracking_from_quoted_html() -> None:
    code = "AA-7K4P-Q9XM-3TRZ"
    quoted = (
        "<p>Leider eine Absage.</p>"
        '<blockquote><div style="font-size:0;color:#ffffff">'
        f"AutoApplication-Referenz {code}</div></blockquote>"
    )
    fake = FakeImap(
        inbox=[_message("Re: Bewerbung", "hr@firma.example", quoted, html=True)]
    )
    client = _client(fake)
    messages = client.inbox_since("2026-11-01T00:00:00+00:00")
    assert messages[0]["tracking"] == code
    assert messages[0]["body"]["content"].startswith("Leider eine Absage")


def test_inbox_since_reads_tracking_from_references() -> None:
    message = EmailMessage()
    message["From"] = "hr@firma.example"
    message["Subject"] = "Ihre Bewerbung"
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = "<antwort@firma.example>"
    message["References"] = "<abc@autoapplication.local> <AA-7K4P-Q9XM-3TRZ@autoapplication.local>"
    message.set_content("Guten Tag")
    fake = FakeImap(inbox=[message.as_bytes()])
    client = _client(fake)
    messages = client.inbox_since("2026-11-01T00:00:00+00:00")
    assert messages[0]["tracking"] == "AA-7K4P-Q9XM-3TRZ"


def test_inbox_since_without_tracking_is_empty() -> None:
    fake = FakeImap(inbox=[_message("Newsletter", "news@example.com")])
    client = _client(fake)
    assert client.inbox_since("2026-11-01T00:00:00+00:00")[0]["tracking"] == ""


def test_wrong_app_password_is_explained() -> None:
    client = GmailImapClient(
        "ich@example.com",
        "falsch",
        imap_factory=lambda: FakeImap(),
    )
    with pytest.raises(ImapError) as error:
        client.test_connection()
    assert "App-Passwort" in str(error.value)


def test_bodystructure_finds_text_part_of_multipart() -> None:
    from autoapplication.core.imap_mail import _parse_structure, _text_part

    raw = (
        b'1 (BODYSTRUCTURE (((' 
        b'"TEXT" "PLAIN" ("CHARSET" "UTF-8") NIL NIL "7BIT" 5 1)'
        b'("TEXT" "HTML" ("CHARSET" "UTF-8") NIL NIL "7BIT" 9 1) '
        b'"ALTERNATIVE" NIL NIL NIL)'
        b'("APPLICATION" "PDF" ("NAME" "a.pdf") NIL NIL "BASE64" 100) '
        b'"MIXED" NIL NIL NIL))'
    )
    assert _text_part(_parse_structure(raw)) == "1.1"


def test_bodystructure_without_text_part_has_no_number() -> None:
    from autoapplication.core.imap_mail import _parse_structure, _text_part

    raw = (
        b'1 (BODYSTRUCTURE (("APPLICATION" "PDF" NIL NIL NIL "BASE64" 100) '
        b'"MIXED" NIL NIL))'
    )
    assert _text_part(_parse_structure(raw)) == ""


def test_sent_recent_reads_sent_folder() -> None:
    message = EmailMessage()
    message["From"] = "ich@example.com"
    message["Subject"] = "Bewerbung"
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = "<sent@example.com>"
    message["X-AutoApplication-ID"] = "a" * 32
    message["X-AutoApplication-Ref"] = "AA-7K4P-Q9XM-3TRZ"
    message.set_content("Text")
    fake = FakeImap(sent=[message.as_bytes()])
    client = _client(fake)
    sent = client.sent_recent(100)
    assert sent[0]["conversationId"] == "a" * 32
    assert sent[0]["tracking"] == "AA-7K4P-Q9XM-3TRZ"
    assert sent[0]["subject"] == "Bewerbung"
    assert sent[0]["sentDateTime"]
    # Nur Kopfzeilen: keine volle Mail, kein Textteil, keine Anhaenge.
    assert sent[0]["text"] == ""
    assert not any("BODY.PEEK[]" in part for part in fake.fetched)
    assert all("HEADER" in part for part in fake.fetched)


def test_sent_recent_finds_own_draft_by_headers() -> None:
    fake = FakeImap()
    client = _client(fake)
    client.create_draft(
        "Bewerbung",
        "Text",
        to_address="hr@firma.ch",
        tracking="AA-7K4P-Q9XM-3TRZ",
    )
    raw = fake.appended[-1][2]
    sent_fake = FakeImap(sent=[raw])
    sent = _client(sent_fake).sent_recent(100)
    assert sent[0]["tracking"] == "AA-7K4P-Q9XM-3TRZ"
    assert len(sent[0]["conversationId"]) == 32
    assert sent[0]["text"] == ""
    assert not any("BODY.PEEK[]" in part for part in sent_fake.fetched)


def test_sent_recent_reads_text_part_only_without_header_code() -> None:
    message = EmailMessage()
    message["From"] = "ich@example.com"
    message["Subject"] = "Bewerbung"
    message["Date"] = formatdate(localtime=True)
    message.set_content("Kennung AA-7K4P-Q9XM-3TRZ im Text")
    fake = FakeImap(sent=[message.as_bytes()])
    client = _client(fake)
    sent = client.sent_recent(100)
    assert sent[0]["tracking"] == "AA-7K4P-Q9XM-3TRZ"
    assert "AA-7K4P-Q9XM-3TRZ" in sent[0]["text"]
    assert any("BODY.PEEK[1]" in part for part in fake.fetched)
    assert not any("BODY.PEEK[]" in part for part in fake.fetched)


def test_inbox_since_normalizes_sender_and_body() -> None:
    fake = FakeImap(
        inbox=[
            _message("Re: Bewerbung", "Personal <personal@firma.example>", "Guten Tag"),
            _message("Newsletter", "news@example.com", "<p>Nur <b>HTML</b></p>", html=True),
        ]
    )
    client = _client(fake)
    messages = client.inbox_since("2026-11-01T00:00:00+00:00")
    assert len(messages) == 2
    first = messages[0]
    assert first["from"]["emailAddress"]["address"] == "personal@firma.example"
    assert first["subject"] == "Re: Bewerbung"
    assert first["body"]["content"] == "Guten Tag"
    assert first["receivedDateTime"]
    assert "HTML" in messages[1]["body"]["content"]
    assert "<b>" not in messages[1]["body"]["content"]


def test_connection_test_checks_smtp_too() -> None:
    smtp = FakeSmtp()
    client = _client(FakeImap(), smtp=smtp)
    text = client.test_connection()
    assert "Entwürfe" in text
    assert smtp.started and smtp.logged_in and smtp.quit_called


def test_missing_configuration_is_explained() -> None:
    client = GmailImapClient("", "")
    with pytest.raises(ImapError) as error:
        client.create_draft("Betreff", "Text")
    assert "Einstellungen" in str(error.value)
