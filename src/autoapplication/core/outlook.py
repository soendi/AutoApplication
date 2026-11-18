"""Outlook-Anbindung ueber Microsoft Graph.

Anmeldung ohne Passwort im Programm: Geraetecode-Verfahren (Device Code Flow)
einer App-Registrierung. Danach legt AutoApplication Bewerbungen als Entwurf in
Outlook ab, erkennt gesendete Mails und liest Antworten im Posteingang.
"""

from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
AUTHORITY = "https://login.microsoftonline.com"
SCOPES = "offline_access User.Read Mail.ReadWrite Mail.Send"
MAX_SIMPLE_ATTACHMENT = 3 * 1024 * 1024  # Grenze fuer einfache Anhaenge in Graph
JSON_HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}


class OutlookError(RuntimeError):
    """Fehler mit einer Meldung, die direkt angezeigt werden kann."""


@dataclass
class DeviceLogin:
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    expires_in: int
    message: str = ""


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
        raise OutlookError(f"Keine Verbindung zu Microsoft: {error}") from error
    try:
        parsed = json.loads(payload) if payload else {}
    except ValueError:
        parsed = {"raw": payload}
    return status, parsed


def _error_text(payload: dict[str, Any]) -> str:
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("code") or "")
    if error:
        description = payload.get("error_description")
        return str(description or error)
    return str(payload.get("message") or "")


@dataclass
class Tokens:
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
    def from_dict(cls, payload: dict[str, Any]) -> "Tokens":
        return cls(
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or ""),
            expires_at=float(payload.get("expires_at") or 0),
            account=str(payload.get("account") or ""),
        )


class GraphAuth:
    """Geraetecode-Anmeldung und Token-Verwaltung."""

    def __init__(
        self,
        client_id: str,
        tenant: str = "common",
        token_file: Path | None = None,
        request: Callable[..., tuple[int, dict[str, Any]]] | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.tenant = (tenant or "common").strip() or "common"
        self.token_file = token_file
        self.request = request or _request
        self.tokens = Tokens()
        self.load()

    # ------------------------------------------------------------------
    def _authority(self, path: str) -> str:
        return f"{AUTHORITY}/{self.tenant}/oauth2/v2.0/{path}"

    def load(self) -> None:
        if not self.token_file or not self.token_file.exists():
            return
        try:
            payload = json.loads(self.token_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.tokens = Tokens.from_dict(payload)

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
        self.tokens = Tokens()
        if self.token_file and self.token_file.exists():
            try:
                self.token_file.unlink()
            except OSError:
                pass

    # ------------------------------------------------------------------
    def start_device_flow(self) -> DeviceLogin:
        if not self.client_id:
            raise OutlookError(
                "Es fehlt die Client-ID der App-Registrierung. Sie steht unter "
                "Einstellungen > Outlook."
            )
        status, payload = self.request(
            "POST",
            self._authority("devicecode"),
            data=urllib.parse.urlencode(
                {"client_id": self.client_id, "scope": SCOPES}
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status >= 400:
            raise OutlookError(_error_text(payload) or "Anmeldung nicht moeglich.")
        return DeviceLogin(
            device_code=str(payload.get("device_code") or ""),
            user_code=str(payload.get("user_code") or ""),
            verification_uri=str(
                payload.get("verification_uri") or "https://microsoft.com/devicelogin"
            ),
            interval=int(payload.get("interval") or 5),
            expires_in=int(payload.get("expires_in") or 900),
            message=str(payload.get("message") or ""),
        )

    def poll_device_flow(self, login: DeviceLogin) -> bool:
        """Einmal nachfragen; True, sobald die Anmeldung abgeschlossen ist."""
        status, payload = self.request(
            "POST",
            self._authority("token"),
            data=urllib.parse.urlencode(
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "client_id": self.client_id,
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
            raise OutlookError("Der Code ist abgelaufen. Bitte neu verbinden.")
        if error == "authorization_declined":
            raise OutlookError("Die Anmeldung wurde abgebrochen.")
        raise OutlookError(_error_text(payload) or "Anmeldung fehlgeschlagen.")

    def _store(self, payload: dict[str, Any]) -> None:
        self.tokens = Tokens(
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
            raise OutlookError(
                "Outlook ist noch nicht verbunden. Bitte unter Einstellungen "
                "> Outlook anmelden."
            )
        status, payload = self.request(
            "POST",
            self._authority("token"),
            data=urllib.parse.urlencode(
                {
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "refresh_token": self.tokens.refresh_token,
                    "scope": SCOPES,
                }
            ).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if status >= 400:
            raise OutlookError(
                _error_text(payload)
                or "Die Outlook-Anmeldung ist abgelaufen. Bitte neu verbinden."
            )
        self._store(payload)
        if not self.tokens.access_token:
            raise OutlookError("Microsoft lieferte kein Token.")
        return self.tokens.access_token


class OutlookClient:
    """Graph-Aufrufe fuer Entwuerfe, gesendete Mails und den Posteingang."""

    def __init__(
        self,
        auth: GraphAuth,
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
        url = f"{GRAPH}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = dict(JSON_HEADERS)
        headers["Authorization"] = f"Bearer {self.auth.token()}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        status, body = self.request(method, url, data=data, headers=headers)
        if status >= 400:
            raise OutlookError(_error_text(body) or f"Graph-Fehler {status}.")
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
        message: dict[str, Any] = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
        }
        if to_address and "@" in to_address:
            message["toRecipients"] = [{"emailAddress": {"address": to_address}}]
        created = self._call("POST", "/me/messages", payload=message)
        message_id = str(created.get("id") or "")
        # Anhaenge einzeln nachreichen: mehrere PDFs sprengen sonst die Grenze
        # fuer einfache Anhaenge beim Anlegen der Nachricht.
        if message_id:
            for path in attachments or []:
                try:
                    raw = path.read_bytes()
                except OSError as exc:
                    log.warning("Anhang %s nicht lesbar: %s", path, exc)
                    continue
                if len(raw) > MAX_SIMPLE_ATTACHMENT:
                    log.warning("Anhang %s ist zu gross fuer eine Mail", path.name)
                    continue
                try:
                    self._call(
                        "POST",
                        f"/me/messages/{message_id}/attachments",
                        payload={
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": path.name,
                            "contentBytes": base64.b64encode(raw).decode("ascii"),
                        },
                    )
                except OutlookError as exc:
                    log.warning("Anhang %s nicht angehaengt: %s", path.name, exc)
        return created

    def find_sent(self, conversation_id: str) -> dict[str, Any] | None:
        """Wurde der Entwurf verschickt? Suche im Ordner Gesendete Elemente."""
        if not conversation_id:
            return None
        escaped = conversation_id.replace("'", "''")
        body = self._call(
            "GET",
            "/me/mailFolders/sentitems/messages",
            params={
                "$filter": f"conversationId eq '{escaped}'",
                "$select": "id,sentDateTime,internetMessageId,conversationId,subject",
                "$top": "1",
            },
        )
        items = body.get("value") or []
        return items[0] if items else None

    def inbox_since(self, since_iso: str, top: int = 50) -> list[dict[str, Any]]:
        """Nachrichten im Posteingang ab einem Zeitpunkt."""
        body = self._call(
            "GET",
            "/me/mailFolders/inbox/messages",
            params={
                "$filter": f"receivedDateTime ge {since_iso}",
                "$select": (
                    "id,receivedDateTime,subject,bodyPreview,conversationId,"
                    "from,body"
                ),
                "$orderby": "receivedDateTime desc",
                "$top": str(top),
            },
        )
        return list(body.get("value") or [])

    def profile(self) -> dict[str, Any]:
        return self._call("GET", "/me", params={"$select": "displayName,mail,userPrincipalName"})

    def draft_link(self, draft_id: str) -> str:
        return self._call(
            "GET", f"/me/messages/{draft_id}", params={"$select": "webLink"}
        ).get("webLink", "")


def sender_address(message: dict[str, Any]) -> str:
    sender = message.get("from") or {}
    email = sender.get("emailAddress") or {}
    return str(email.get("address") or "")


def message_body(message: dict[str, Any]) -> str:
    body = message.get("body") or {}
    content = body.get("content") or ""
    if body.get("contentType") == "html":
        from .text import strip_html

        return strip_html(content)
    return str(content or message.get("bodyPreview") or "")
