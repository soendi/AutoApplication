"""Gmail-Anbindung ueber IMAP und SMTP mit App-Passwort.

Kein OAuth, kein Microsoft-Konto: AutoApplication meldet sich mit der
Gmail-Adresse und einem 16-stelligen App-Passwort an (Google-Konto >
Sicherheit > App-Passwoerter, 2-Faktor-Authentifizierung noetig).

Entwuerfe werden per IMAP in den Ordner mit dem Attribut ``\\Drafts`` gelegt
(bei Gmail "[Gmail]/Drafts" bzw. "[Gmail]/Entwuerfe"), gesendet wird ueber
smtp.gmail.com. Der Versand wird im Ordner ``\\Sent`` erkannt, Antworten im
Posteingang gelesen. Alles laeuft ueber die Standardbibliothek.
"""

from __future__ import annotations

import imaplib
import logging
import mimetypes
import re
import smtplib
import time
import uuid
from contextlib import contextmanager
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Iterator

from .text import strip_html

log = logging.getLogger(__name__)

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
MAX_ATTACHMENT = 15 * 1024 * 1024  # Gmail erlaubt 25 MB; Sicherheitsabstand
INBOX_LIMIT = 50
MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


class ImapError(RuntimeError):
    """Fehler mit einer Meldung, die direkt angezeigt werden kann."""


def _imap_date(value: Any) -> str:
    """Datum im IMAP-Format (18-Nov-2026), unabhaengig von der Sprache."""
    if hasattr(value, "strftime"):
        day, month, year = value.day, value.month, value.year
    else:
        return "1-Jan-1970"
    return f"{day}-{MONTHS[max(1, min(12, month)) - 1]}-{year}"


def _iso(value: Any) -> str:
    """Mail-Datum als ISO-Zeitstempel; leer, wenn nicht lesbar."""
    if not value:
        return ""
    try:
        moment = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return ""
    if moment is None:
        return ""
    return moment.isoformat(timespec="seconds")


def _folder_name(raw: bytes) -> bytes:
    name = raw.strip()
    if name.startswith(b'"') and name.endswith(b'"') and len(name) >= 2:
        name = name[1:-1]
    return name


class GmailImapClient:
    """Entwuerfe, Versand und Posteingang ueber Gmail IMAP/SMTP."""

    def __init__(
        self,
        email: str,
        password: str,
        *,
        imap_factory: Callable[[], Any] | None = None,
        smtp_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.email = (email or "").strip()
        self.password = password or ""
        self._imap_factory = imap_factory or (
            lambda: imaplib.IMAP4_SSL(IMAP_HOST, 993)
        )
        self._smtp_factory = smtp_factory or (
            lambda: smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        )

    # ------------------------------------------------------------------
    def configured(self) -> bool:
        return bool(self.email and self.password)

    @contextmanager
    def _imap(self) -> Iterator[Any]:
        if not self.configured():
            raise ImapError(
                "Gmail ist noch nicht eingerichtet. Bitte unter Einstellungen "
                "> Gmail die Adresse und das App-Passwort eintragen."
            )
        try:
            connection = self._imap_factory()
        except (OSError, imaplib.IMAP4.error) as exc:
            raise ImapError(f"Keine Verbindung zu Gmail: {exc}") from exc
        try:
            try:
                connection.login(self.email, self.password)
            except imaplib.IMAP4.error as exc:
                raise ImapError(
                    "Gmail hat die Anmeldung abgelehnt. Bitte das App-Passwort "
                    "prüfen: Google-Konto > Sicherheit > App-Passwörter "
                    "(2-Faktor-Authentifizierung muss aktiv sein)."
                ) from exc
            yield connection
        finally:
            try:
                connection.logout()
            except Exception:  # noqa: BLE001 - Verbindung darf nichts stoppen
                pass

    def _folder(self, connection: Any, flag: bytes) -> bytes:
        """Ordner anhand seines IMAP-Attributs finden (Sprache egal)."""
        try:
            status, data = connection.list()
        except Exception as exc:  # noqa: BLE001 - Fehler verstaendlich machen
            raise ImapError(f"Ordnerliste nicht lesbar: {exc}") from exc
        if status != "OK":
            raise ImapError("Gmail lieferte keine Ordnerliste.")
        for item in data or []:
            if not isinstance(item, (bytes, bytearray)):
                continue
            line = bytes(item)
            match = re.match(
                rb"\((?P<attrs>[^)]*)\)\s+(?P<delim>\"[^\"]*\"|NIL)\s+(?P<name>.+)$",
                line,
            )
            if not match:
                continue
            if flag.lower() not in match.group("attrs").lower():
                continue
            return _folder_name(match.group("name"))
        raise ImapError(
            "Gmail hat keinen passenden Ordner gemeldet. Bitte prüfen, ob IMAP "
            "im Google-Konto zugelassen ist."
        )

    # ------------------------------------------------------------------
    def test_connection(self) -> str:
        """IMAP- und SMTP-Anmeldung pruefen und den Ordnernamen melden."""
        with self._imap() as connection:
            drafts = self._folder(connection, b"\\Drafts")
        try:
            server = self._smtp_factory()
            try:
                server.starttls()
                server.login(self.email, self.password)
            finally:
                try:
                    server.quit()
                except Exception:  # noqa: BLE001 - Aufraeumen darf nichts stoppen
                    pass
        except smtplib.SMTPAuthenticationError as exc:
            raise ImapError(
                "Gmail hat den Versand-Login abgelehnt. Bitte das App-Passwort "
                "prüfen."
            ) from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise ImapError(f"Keine Verbindung zum Versandserver: {exc}") from exc
        return f"Gmail ist erreichbar. Entwürfe: {drafts.decode('utf-8', 'replace')}"

    # ------------------------------------------------------------------
    def create_draft(
        self,
        subject: str,
        body: str,
        to_address: str = "",
        attachments: list[Path] | None = None,
    ) -> dict[str, Any]:
        """Bewerbung als Entwurf in Gmail ablegen - gesendet wird von Hand."""
        token = uuid.uuid4().hex
        message = EmailMessage()
        message["From"] = self.email
        if to_address and "@" in to_address:
            message["To"] = to_address
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = f"<{token}@autoapplication.local>"
        # Eigener Kopf, damit der Versand auch dann erkannt wird, wenn Gmail
        # die Message-ID beim Senden ersetzt.
        message["X-AutoApplication-ID"] = token
        message.set_content(body)

        total = 0
        for path in attachments or []:
            try:
                raw = path.read_bytes()
            except OSError as exc:
                log.warning("Anhang %s nicht lesbar: %s", path, exc)
                continue
            if len(raw) > MAX_ATTACHMENT or total + len(raw) > 2 * MAX_ATTACHMENT:
                log.warning("Anhang %s ist zu gross fuer eine Mail", path.name)
                continue
            total += len(raw)
            guessed = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            maintype, _, subtype = guessed.partition("/")
            message.add_attachment(
                raw,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=path.name,
            )

        with self._imap() as connection:
            drafts = self._folder(connection, b"\\Drafts")
            try:
                status, _ = connection.append(
                    drafts,
                    "(\\Draft)",
                    imaplib.Time2Internaldate(time.time()),
                    message.as_bytes(),
                )
            except Exception as exc:  # noqa: BLE001 - Fehler verstaendlich machen
                raise ImapError(f"Entwurf konnte nicht abgelegt werden: {exc}") from exc
            if status != "OK":
                raise ImapError("Gmail hat den Entwurf nicht angenommen.")

        return {"id": token, "conversationId": token, "webLink": "", "subject": subject}

    # ------------------------------------------------------------------
    def find_sent(self, conversation_id: str) -> dict[str, Any] | None:
        """Wurde der Entwurf verschickt? Suche im Ordner Gesendet."""
        token = (conversation_id or "").strip()
        # Nur eigene Kennungen durchlassen - verhindert IMAP-Suchinjektion.
        if not re.fullmatch(r"[0-9a-f]{32}", token):
            return None
        with self._imap() as connection:
            sent = self._folder(connection, b"\\Sent")
            connection.select(sent, readonly=True)
            numbers = self._search(
                connection,
                "HEADER",
                "X-AutoApplication-ID",
                f'"{token}"',
            )
            if not numbers:
                numbers = self._search(
                    connection,
                    "HEADER",
                    "Message-ID",
                    f'"<{token}@autoapplication.local>"',
                )
            if not numbers:
                return None
            raw = self._fetch(connection, numbers[-1])
        if raw is None:
            return None
        message = BytesParser(policy=policy.default).parsebytes(raw)
        message_id = str(message.get("Message-ID") or "")
        return {
            "id": message_id,
            "conversationId": token,
            "internetMessageId": message_id,
            "sentDateTime": _iso(message.get("Date")),
            "subject": str(message.get("Subject") or ""),
        }

    # ------------------------------------------------------------------
    def inbox_since(self, since_iso: str, top: int = INBOX_LIMIT) -> list[dict[str, Any]]:
        """Nachrichten im Posteingang ab einem Zeitpunkt."""
        try:
            from datetime import datetime

            since = datetime.fromisoformat(since_iso)
        except (TypeError, ValueError):
            from datetime import datetime, timedelta

            since = datetime.now() - timedelta(days=30)
        with self._imap() as connection:
            connection.select("INBOX", readonly=True)
            numbers = self._search(connection, "SINCE", _imap_date(since))
            if not numbers:
                return []
            result: list[dict[str, Any]] = []
            for number in numbers[-max(1, top):]:
                raw = self._fetch(connection, number)
                if raw is None:
                    continue
                message = BytesParser(policy=policy.default).parsebytes(raw)
                sender = str(message.get("From") or "")
                address = sender
                if "<" in sender and ">" in sender:
                    address = sender[sender.index("<") + 1: sender.rindex(">")]
                text = self._text(message)
                result.append(
                    {
                        "id": str(message.get("Message-ID") or number.decode("ascii", "replace")),
                        "receivedDateTime": _iso(message.get("Date")),
                        "subject": str(message.get("Subject") or ""),
                        "conversationId": "",
                        "bodyPreview": text[:200],
                        "from": {"emailAddress": {"address": address.strip()}},
                        "body": {"contentType": "Text", "content": text},
                    }
                )
            return result

    # ------------------------------------------------------------------
    @staticmethod
    def _search(connection: Any, *criteria: str) -> list[bytes]:
        try:
            status, data = connection.search(None, *criteria)
        except Exception as exc:  # noqa: BLE001 - Fehler verstaendlich machen
            raise ImapError(f"Suche im Postfach fehlgeschlagen: {exc}") from exc
        if status != "OK" or not data:
            return []
        return list((data[0] or b"").split())

    @staticmethod
    def _fetch(connection: Any, number: bytes) -> bytes | None:
        try:
            status, data = connection.fetch(number, "(BODY.PEEK[])")
        except Exception as exc:  # noqa: BLE001 - Fehler verstaendlich machen
            raise ImapError(f"Nachricht nicht lesbar: {exc}") from exc
        if status != "OK":
            return None
        for part in data or []:
            if isinstance(part, tuple) and len(part) >= 2:
                return bytes(part[1])
        return None

    @staticmethod
    def _text(message: Any) -> str:
        """Text einer Mail - bevorzugt text/plain, sonst HTML ohne Markup."""
        try:
            if message.is_multipart():
                for part in message.walk():
                    disposition = str(part.get("Content-Disposition") or "")
                    if part.get_content_type() == "text/plain" and "attachment" not in disposition:
                        return str(part.get_content()).strip()
                for part in message.walk():
                    if part.get_content_type() == "text/html":
                        return strip_html(str(part.get_content())).strip()
                return ""
            if message.get_content_type() == "text/html":
                return strip_html(str(message.get_content())).strip()
            return str(message.get_content()).strip()
        except (LookupError, UnicodeDecodeError, ValueError):
            payload = message.get_payload(decode=True) or b""
            return payload.decode("utf-8", errors="replace")


__all__ = ["GmailImapClient", "ImapError", "IMAP_HOST", "SMTP_HOST"]
