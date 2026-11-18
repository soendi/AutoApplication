"""Google-Anbindung ueber Gmail.

Anmeldung wie im Browser gewohnt: AutoApplication oeffnet die Google-Seite, der
Benutzer meldet sich mit seinem Google-Konto an und die Freigabe kommt ueber
einen lokalen Rueckkanal zurueck (OAuth 2.0 Authorization Code mit PKCE). Ein
Client-Geheimnis wird dabei nicht gebraucht - der OAuth-Client ist oeffentlich
(Typ "Desktop app" in der Google Cloud Console).

Danach legt AutoApplication Bewerbungen als Entwurf in Gmail ab, erkennt
gesendete Mails und liest Antworten im Posteingang.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from .outlook import OutlookError
from .text import strip_html

log = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
DRAFT_LINK = "https://mail.google.com/mail/u/0/#drafts"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.modify"
MAX_ATTACHMENT = 20 * 1024 * 1024  # Gmail nimmt insgesamt rund 25 MB
LOGIN_TIMEOUT = 300
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


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


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


class _CallbackHandler(BaseHTTPRequestHandler):
    """Nimmt die Weiterleitung von Google auf 127.0.0.1 entgegen."""

    def do_GET(self) -> None:  # noqa: N802 - Namensschema von http.server
        parsed = urllib.parse.urlparse(self.path)
        params = {
            key: values[0]
            for key, values in urllib.parse.parse_qs(parsed.query).items()
            if values
        }
        if "code" in params or "error" in params:
            self.server.result = params  # type: ignore[attr-defined]
            message = (
                "Anmeldung abgeschlossen. Dieses Fenster kann geschlossen werden."
                if "code" in params
                else "Die Anmeldung wurde nicht abgeschlossen."
            )
            self._answer(200, message)
        else:
            self._answer(404, "Warte auf die Anmeldung bei Google.")

    def _answer(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html lang='de'><meta charset='utf-8'>"
            "<title>AutoApplication</title>"
            "<body style='font-family:sans-serif;padding:40px'>"
            f"<h2>{message}</h2>"
            "<p>Sie koennen dieses Fenster schliessen und zu AutoApplication "
            "zurueckkehren.</p></body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: Any) -> None:  # noqa: D102 - keine Logzeilen
        return


@dataclass
class GoogleLogin:
    """Eine laufende Anmeldung: Adresse, PKCE-Werte und lokaler Rueckkanal."""

    verification_uri: str
    state: str
    redirect_uri: str
    code_verifier: str
    interval: int = 2
    expires_in: int = LOGIN_TIMEOUT
    user_code: str = ""
    message: str = ""
    expires_at: float = 0.0
    server: ThreadingHTTPServer | None = field(default=None, repr=False)
    result: dict[str, str] | None = field(default=None, repr=False)


class GoogleAuth:
    """Anmeldung ueber den Google-Login im Browser (Authorization Code + PKCE)."""

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        token_file: Path | None = None,
        request: Callable[..., tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        # Google verlangt beim Desktop-Client das Client-Geheimnis beim
        # Token-Tausch, auch mit PKCE. Es bleibt lokal in den Einstellungen.
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
    def start_device_flow(self) -> GoogleLogin:
        """Anmeldung starten - Name bleibt fuer die Oberflaeche gleich."""
        return self.start_login()

    def start_login(self, port: int = 0) -> GoogleLogin:
        """Lokalen Rueckkanal oeffnen und die Google-Anmeldeseite bauen."""
        if not self.client_id:
            raise GoogleError(
                "Es fehlt die Client-ID des Google-OAuth-Clients. Sie steht unter "
                "Einstellungen > Google."
            )
        verifier = _b64url(secrets.token_bytes(48))
        state = secrets.token_urlsafe(24)
        server = ThreadingHTTPServer(("127.0.0.1", port), _CallbackHandler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        redirect_uri = f"http://127.0.0.1:{server.server_port}"
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return GoogleLogin(
            verification_uri=f"{AUTH_URL}?{urllib.parse.urlencode(params)}",
            state=state,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
            interval=2,
            expires_in=LOGIN_TIMEOUT,
            expires_at=time.time() + LOGIN_TIMEOUT,
            message="Im Browser mit dem Google-Konto anmelden und die Freigabe erteilen.",
            server=server,
        )

    def poll_device_flow(self, login: GoogleLogin) -> bool:
        """Nachsehen, ob die Anmeldung im Browser abgeschlossen wurde."""
        if login.server is None:
            raise GoogleError("Die Anmeldung wurde bereits beendet.")
        if login.result is None:
            login.result = getattr(login.server, "result", None)
        if login.result is None:
            if login.expires_at and time.time() > login.expires_at:
                self.cancel_login(login)
                raise GoogleError("Die Anmeldung hat zu lange gedauert. Bitte neu starten.")
            return False

        params = login.result
        self.cancel_login(login)
        error = params.get("error")
        if error:
            if error == "access_denied":
                raise GoogleError("Die Anmeldung wurde abgebrochen.")
            raise GoogleError(params.get("error_description") or error)
        if params.get("state") != login.state:
            raise GoogleError("Die Antwort von Google passte nicht zur Anmeldung.")
        code = params.get("code")
        if not code:
            raise GoogleError("Google lieferte keinen Anmeldecode.")

        fields = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "code": code,
            "code_verifier": login.code_verifier,
            "redirect_uri": login.redirect_uri,
        }
        if self.client_secret:
            fields["client_secret"] = self.client_secret
        status, payload = self.request(
            "POST",
            TOKEN_URL,
            data=urllib.parse.urlencode(fields).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status >= 400:
            raise GoogleError(_error_text(payload) or "Anmeldung fehlgeschlagen.")
        self._store(payload)
        return True

    def cancel_login(self, login: GoogleLogin | None) -> None:
        """Rueckkanal schliessen (z. B. bei Abbruch oder nach der Anmeldung)."""
        if login is None or login.server is None:
            return
        try:
            login.server.shutdown()
            login.server.server_close()
        except OSError:
            pass
        finally:
            login.server = None

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
        fields = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.tokens.refresh_token,
        }
        if self.client_secret:
            fields["client_secret"] = self.client_secret
        status, payload = self.request(
            "POST",
            TOKEN_URL,
            data=urllib.parse.urlencode(fields).encode(),
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
