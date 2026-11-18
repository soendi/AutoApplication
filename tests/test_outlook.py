from __future__ import annotations

import time
import urllib.parse

import pytest

from autoapplication.core.outlook import (
    GraphAuth,
    OutlookClient,
    OutlookError,
    Tokens,
)


class FakeRequest:
    """Ersetzt den HTTP-Aufruf und merkt sich alle Aufrufe."""

    def __init__(self, responses: list[tuple[int, dict]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, method, url, data=None, headers=None, timeout=30.0):
        self.calls.append(
            {"method": method, "url": url, "data": data, "headers": headers or {}}
        )
        return self.responses.pop(0)


def _auth_with_token() -> GraphAuth:
    auth = GraphAuth("client-id", token_file=None)
    auth.tokens = Tokens(access_token="token", expires_at=time.time() + 3600)
    return auth


def test_device_flow_then_token(tmp_path) -> None:
    request = FakeRequest(
        [
            (
                200,
                {
                    "device_code": "dev",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": "https://microsoft.com/devicelogin",
                    "interval": 5,
                    "expires_in": 900,
                },
            ),
            (400, {"error": "authorization_pending"}),
            (200, {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600}),
        ]
    )
    token_file = tmp_path / "outlook_token.json"
    auth = GraphAuth("client-id", token_file=token_file, request=request)
    assert auth.connected() is False

    login = auth.start_device_flow()
    assert login.user_code == "ABCD-EFGH"
    assert auth.poll_device_flow(login) is False
    assert auth.poll_device_flow(login) is True
    assert auth.connected() is True
    assert auth.token() == "a1"
    assert token_file.exists()
    assert "refresh_token" in token_file.read_text(encoding="utf-8")


def test_device_flow_expired() -> None:
    request = FakeRequest(
        [
            (
                200,
                {
                    "device_code": "dev",
                    "user_code": "CODE",
                    "verification_uri": "https://example",
                    "interval": 5,
                },
            ),
            (400, {"error": "expired_token"}),
        ]
    )
    auth = GraphAuth("client-id", request=request)
    login = auth.start_device_flow()
    with pytest.raises(OutlookError):
        auth.poll_device_flow(login)


def test_token_is_refreshed() -> None:
    request = FakeRequest(
        [(200, {"access_token": "neu", "refresh_token": "r2", "expires_in": 3600})]
    )
    auth = GraphAuth("client-id", request=request)
    auth.tokens = Tokens(access_token="alt", refresh_token="r1", expires_at=0)
    assert auth.token() == "neu"
    call = request.calls[0]
    assert "grant_type=refresh_token" in call["data"].decode()
    assert auth.tokens.refresh_token == "r2"


def test_missing_client_id() -> None:
    auth = GraphAuth("", request=FakeRequest([]))
    with pytest.raises(OutlookError):
        auth.start_device_flow()


def test_create_draft_with_attachment(tmp_path) -> None:
    attachment = tmp_path / "lebenslauf.pdf"
    attachment.write_bytes(b"%PDF-1.4 Test")
    request = FakeRequest(
        [
            (201, {"id": "m1", "conversationId": "c1", "webLink": "https://outlook/x"}),
            (201, {"id": "att1"}),
        ]
    )
    client = OutlookClient(_auth_with_token(), request=request)
    draft = client.create_draft(
        "Bewerbung als Speditionskaufmann",
        "Sehr geehrte Damen und Herren",
        "hr@muster.ch",
        [attachment],
    )
    assert draft["id"] == "m1"
    first = request.calls[0]
    assert first["url"].endswith("/me/messages")
    assert b'"address": "hr@muster.ch"' in first["data"]
    second = request.calls[1]
    assert second["url"].endswith("/me/messages/m1/attachments")
    assert b"lebenslauf.pdf" in second["data"]
    assert b"contentBytes" in second["data"]


def test_create_draft_without_recipient() -> None:
    request = FakeRequest([(201, {"id": "m1"})])
    client = OutlookClient(_auth_with_token(), request=request)
    client.create_draft("Betreff", "Text")
    assert b"toRecipients" not in request.calls[0]["data"]


def test_find_sent_uses_conversation() -> None:
    request = FakeRequest([(200, {"value": [{"id": "s1", "sentDateTime": "2026-11-18T08:00:00Z"}]})])
    client = OutlookClient(_auth_with_token(), request=request)
    sent = client.find_sent("conv'1")
    assert sent is not None and sent["id"] == "s1"
    url = urllib.parse.unquote_plus(request.calls[0]["url"])
    assert "conversationId eq 'conv''1'" in url


def test_find_sent_without_conversation_does_not_call() -> None:
    request = FakeRequest([])
    client = OutlookClient(_auth_with_token(), request=request)
    assert client.find_sent("") is None
    assert request.calls == []


def test_inbox_since() -> None:
    request = FakeRequest([(200, {"value": [{"id": "i1", "subject": "Absage"}]})])
    client = OutlookClient(_auth_with_token(), request=request)
    messages = client.inbox_since("2026-11-01T00:00:00Z")
    assert messages[0]["id"] == "i1"
    url = urllib.parse.unquote_plus(request.calls[0]["url"])
    assert "receivedDateTime ge 2026-11-01T00:00:00Z" in url
    assert request.calls[0]["headers"]["Authorization"] == "Bearer token"


def test_graph_error_becomes_outlook_error() -> None:
    request = FakeRequest(
        [(401, {"error": {"code": "InvalidAuthenticationToken", "message": "Token abgelaufen"}})]
    )
    client = OutlookClient(_auth_with_token(), request=request)
    with pytest.raises(OutlookError) as error:
        client.inbox_since("2026-11-01T00:00:00Z")
    assert "Token abgelaufen" in str(error.value)
