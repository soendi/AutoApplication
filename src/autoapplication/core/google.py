"""Google-Anbindung ueber Gmail.

Anmeldung ohne Passwort im Programm: Geraetecode-Verfahren (OAuth 2.0 fuer
Geraete mit begrenzter Eingabe). Danach legt AutoApplication Bewerbungen als
Entwurf in Gmail ab, erkennt gesendete Mails und liest Antworten im Posteingang.

In der Google Cloud Console braucht es dafuer einen OAuth-Client vom Typ
"TVs and Limited Input devices" sowie die aktivierte Gmail-API.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

from .outlook import DeviceLogin, OutlookError
from .text import strip_html

log = logging.getLogger(__name__)

DEVICE_CODE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
DRAFT_LINK = "https://mail.google.com/mail/u/0/#drafts"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.modify"
MAX_ATTACHMENT = 20 * 1024 * 1024  # Gmail nimmt insgesamt rund 25 MB
JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class GoogleError(OutlookError):
    """Fehler der Google-Anbindung - erbt die Meldung fuer die Oberflaeche."""


def _request(
    method: str,
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    """HTTP-Aufruf, der auch Fehlerantworten als JSON zurueckgibt."""
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
            status = response.status
    except urllib.error.HTTPError as error:
        payload = error.read().decode("utf-8", errors="replace")
        status = error.code
    except (urllib.error.URLError, OSError) as error:
        raise GoogleError(f"Keine Verbindung zu Google: {error}") from error
    try:
        parsed = json.loads(payload) if payload else {}
    except ValueError:
        parsed = {"raw": payload}
    return status, parsed


def _error_text(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("status") or "")
    if error:
        description = payload.get("error_description")
        return str(description or error)
    return str(payload.get("message") or "")


@dataclass
class GoogleTokens:
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0
    account: str = ""

    def usable(self) -> bool:
        return bool(self.access_token) and self.expires_at - 60 > time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "account": self.account,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GoogleTokens":
        return cls(
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or ""),
            expires_at=float(payload.get("expires_at") or 0),
            account=str(payload.get("account") or ""),
        )


class GoogleAuth:
    """Geraetecode-Anmeldung und Token-Verwaltung fuer Google."""

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        token_file: Path | None = None,
        request: Callable[..., tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.token_file = token_file
        self.request = request or _request
        self.tokens = GoogleTokens()
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.token_file or not self.token_file.exists():
            return
        try:
            payload = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.tokens = GoogleTokens.from_dict(payload)

    def save(self) -> None:
        if not self.token_file:
            return
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(
            json.dumps(self.tokens.to_dict(), indent=2), encoding="utf-8"
        )
        try:  # Nur der eigene Benutzer soll die Datei lesen koennen.
            self.token_file.chmod(0o600)
        except OSError:
            pass

    def connected(self) -> bool:
        return bool(self.tokens.refresh_token or self.tokens.usable())

    def disconnect(self) -> None:
        self.tokens = GoogleTokens()
        if self.token_file and self.token_file.exists():
            try:
                self.token_file.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    def _check_client(self) -> None:
        if not self.client_id:
            raise GoogleError(
                "Es fehlt die Client-ID des Google-OAuth-Clients. Sie steht unter "
                "Einstellungen > Google."
            )
        if not self.client_secret:
            raise GoogleError(
                "Es fehlt das Client-Geheimnis des Google-OAuth-Clients. Es steht "
                "unter Einstellungen > Google."
            )

    def start_device_flow(self) -> DeviceLogin:
        self._check_client()
        status, payload = self.request(
            "POST",
            DEVICE_CODE_URL,
            data=urllib.parse.urlencode(
                {"client_id": self.client_id, "scope": SCOPES}
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status >= 400:
            raise GoogleError(_error_text(payload) or "Anmeldung nicht moeglich.")
        return DeviceLogin(
            device_code=str(payload.get("device_code") or ""),
            user_code=str(payload.get("user_code") or ""),
            verification_uri=str(
                payload.get("verification_url")
                or payload.get("verification_uri")
                or "https://www.google.com/device"
            ),
            interval=int(payload.get("interval") or 5),
            expires_in=int(payload.get("expires_in") or 900),
            message=str(payload.get("message") or ""),
        )

    def poll_device_flow(self, login: DeviceLogin) -> bool:
        """Einmal nachfragen; True, sobald die Anmeldung abgeschlossen ist."""
        status, payload = self.request(
            "POST",
            TOKEN_URL,
            data=urllib.parse.urlencode(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "device_code": login.device_code,
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status < 400:
            self._store(payload)
            return True
        error = str(payload.get("error") or "")
        if error in {"authorization_pending", "slow_down"}:
            return False
        if error == "expired_token":
            raise GoogleError("Der Code ist abgelaufen. Bitte neu verbinden.")
        if error == "access_denied":
            raise GoogleError("Die Anmeldung wurde abgebrochen.")
        raise GoogleError(_error_text(payload) or "Anmeldung fehlgeschlagen.")

    def _store(self, payload: dict[str, Any]) -> None:
        self.tokens = GoogleTokens(
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or self.tokens.refresh_token),
            expires_at=time.time() + float(payload.get("expires_in") or 3600),
            account=self.tokens.account,
        )
        self.save()

    def token(self) -> str:
        if self.tokens.usable():
            return self.tokens.access_token
        if not self.tokens.refresh_token:
            raise GoogleError(
                "Google ist noch nicht verbunden. Bitte unter Einstellungen "
                "> Google anmelden."
            )
        status, payload = self.request(
            "POST",
            TOKEN_URL,
            data=urllib.parse.urlencode(
                {
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.tokens.refresh_token,
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status >= 400:
            raise GoogleError(
                _error_text(payload)
                or "Die Google-Anmeldung ist abgelaufen. Bitte neu verbinden."
            )
        self._store(payload)
        if not self.tokens.access_token:
            raise GoogleError("Google lieferte kein Token.")
        return self.tokens.access_token


def build_message(
    subject: str,
    body: str,
    to_address: str = "",
    attachments: list[Path] | None = None,
) -> bytes:
    """Mail nach RFC 822 bauen - Gmail erwartet sie als Rohformat."""
    message = EmailMessage()
    message["Subject"] = subject
    if to_address and "@" in to_address:
        message["To"] = to_address
    message.set_content(body)
    for path in attachments or []:
        try:
            raw = path.read_bytes()
        except OSError as exc:
            log.warning("Anhang %s nicht lesbar: %s", path, exc)
            continue
        if len(raw) > MAX_ATTACHMENT:
            log.warning("Anhang %s ist zu gross fuer eine Mail", path.name)
            continue
        guessed, _encoding = mimetypes.guess_type(path.name)
        maintype, _, subtype = (guessed or "application/octet-stream").partition("/")
        message.add_attachment(
            raw,
            maintype=maintype or "application",
            subtype=subtype or "octet-stream",
            filename=path.name,
        )
    return message.as_bytes()


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for header in (payload.get("payload") or {}).get("headers") or []:
        name = str(header.get("name") or "").lower()
        if name and name not in result:
            result[name] = str(header.get("value") or "")
    return result


def _plain_text(payload: dict[str, Any]) -> str:
    """Text aus einem Gmail-Nachrichtenteil holen."""
    stack = [payload.get("payload") or {}]
    while stack:
        part = stack.pop()
        mime = str(part.get("mimeType") or "")
        data = (part.get("body") or {}).get("data")
        if data and mime.startswith("text/plain"):
            try:
                return base64.urlsafe_b64decode(data + "===").decode(
                    "utf-8", errors="replace"
                )
            except (ValueError, TypeError):
                pass
        stack.extend(part.get("parts") or [])
    snippet = str(payload.get("snippet") or "")
    return strip_html(snippet)


def _iso_from_millis(value: Any) -> str:
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return ""
    if millis <= 0:
        return ""
    return datetime.fromtimestamp(millis / 1000, timezone.utc).isoformat(
        timespec="seconds"
    )


class GmailClient:
    """Gmail-Aufrufe fuer Entwuerfe, gesendete Mails und den Posteingang."""

    def __init__(
        self,
        auth: GoogleAuth,
        request: Callable[..., tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.auth = auth
        self.request = request or _request

    # ------------------------------------------------------------------
    def _call(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{GMAIL_API}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = dict(JSON_HEADERS)
        headers["Authorization"] = f"Bearer {self.auth.token()}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        status, body = self.request(method, url, data=data, headers=headers)
        if status >= 400:
            raise GoogleError(_error_text(body) or f"Gmail-Fehler {status}.")
        return body

    # ------------------------------------------------------------------
    def create_draft(
        self,
        subject: str,
        body: str,
        to_address: str = "",
        attachments: list[Path] | None = None,
    ) -> dict[str, Any]:
        """Bewerbung als Entwurf ablegen - gesendet wird von Hand."""
        raw = build_message(subject, body, to_address, attachments)
        encoded = base64.urlsafe_b64encode(raw).decode("ascii")
        created = self._call(
            "POST", "/drafts", payload={"message": {"raw": encoded}}
        )
        message = created.get("message") or {}
        thread_id = str(message.get("threadId") or "")
        link = f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else DRAFT_LINK
        return {
            "id": str(created.get("id") or ""),
            "conversationId": thread_id,
            "webLink": link,
        }

    def find_sent(self, thread_id: str) -> dict[str, Any] | None:
        """Wurde der Entwurf verschickt? Suche im Thread nach der Marke SENT."""
        if not thread_id:
            return None
        body = self._call(
            "GET",
            f"/threads/{urllib.parse.quote(thread_id)}",
            params={"format": "metadata", "metadataHeaders": "Message-ID"},
        )
        for message in body.get("messages") or []:
            labels = message.get("labelIds") or []
            if "SENT" not in labels:
                continue
            headers = _headers(message)
            return {
                "id": str(message.get("id") or ""),
                "sentDateTime": _iso_from_millis(message.get("internalDate")),
                "internetMessageId": headers.get("message-id", ""),
            }
        return None

    def inbox_since(self, since_iso: str, top: int = 50) -> list[dict[str, Any]]:
        """Nachrichten im Posteingang ab einem Zeitpunkt."""
        try:
            moment = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            epoch = int(moment.timestamp())
        except (TypeError, ValueError):
            epoch = int(time.time()) - 86_400
        listing = self._call(
            "GET",
            "/messages",
            params={
                "q": f"in:inbox after:{epoch}",
                "maxResults": str(max(1, min(100, int(top)))),
            },
        )
        result: list[dict[str, Any]] = []
        for reference in (listing.get("messages") or [])[:top]:
            message_id = str(reference.get("id") or "")
            if not message_id:
                continue
            message = self._call(
                "GET",
                f"/messages/{urllib.parse.quote(message_id)}",
                params={"format": "full"},
            )
            headers = _headers(message)
            sender = headers.get("from", "")
            result.append(
                {
                    "id": message_id,
                    "conversationId": str(message.get("threadId") or ""),
                    "receivedDateTime": _iso_from_millis(message.get("internalDate")),
                    "subject": headers.get("subject", ""),
                    "bodyPreview": str(message.get("snippet") or ""),
                    "body": {"contentType": "text", "content": _plain_text(message)},
                    "from": {"emailAddress": {"address": _address(sender)}},
                }
            )
        return result

    def profile(self) -> dict[str, Any]:
        body = self._call("GET", "/profile")
        address = str(body.get("emailAddress") or "")
        return {"displayName": address, "mail": address, "userPrincipalName": address}

    def draft_link(self, draft_id: str) -> str:
        body = self._call("GET", f"/drafts/{urllib.parse.quote(draft_id)}")
        thread_id = str((body.get("message") or {}).get("threadId") or "")
        return f"https://mail.google.com/mail/u/0/#all/{thread_id}" if thread_id else DRAFT_LINK


def _address(value: str) -> str:
    """Adresse aus "Name <mail@example.ch>" herausschneiden."""
    text = (value or "").strip()
    if "<" in text and ">" in text:
        return text[text.rfind("<") + 1 : text.rfind(">")].strip()
    return text
