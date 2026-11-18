from __future__ import annotations

import base64
import time

import pytest

from autoapplication.core.google import (
    GmailClient,
    GoogleAuth,
    GoogleError,
    GoogleTokens,
    build_message,
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


def _client(responses: list[tuple[int, dict]]) -> tuple[GmailClient, FakeRequest]:
    auth = GoogleAuth("client-id", "secret", token_file=None)
    auth.tokens = GoogleTokens(access_token="token", expires_at=time.time() + 3600)
    request = FakeRequest(responses)
    return GmailClient(auth, request=request), request


def test_device_flow_needs_client_data(tmp_path) -> None:
    auth = GoogleAuth("", token_file=tmp_path / "google_token.json")
    with pytest.raises(GoogleError):
        auth.start_device_flow()
    auth = GoogleAuth("client-id", "", token_file=tmp_path / "google_token.json")
    with pytest.raises(GoogleError):
        auth.start_device_flow()


def test_device_flow_polls_until_token(tmp_path) -> None:
    request = FakeRequest(
        [
            (
                200,
                {
                    "device_code": "dev",
                    "user_code": "ABCD-EFGH",
                    "verification_url": "https://www.google.com/device",
                    "interval": 5,
                    "expires_in": 900,
                },
            ),
            (400, {"error": "authorization_pending"}),
            (200, {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600}),
        ]
    )
    token_file = tmp_path / "google_token.json"
    auth = GoogleAuth("client-id", "secret", token_file=token_file, request=request)
    assert auth.connected() is False

    login = auth.start_device_flow()
    assert login.user_code == "ABCD-EFGH"
    assert login.verification_uri == "https://www.google.com/device"
    assert auth.poll_device_flow(login) is False
    assert auth.poll_device_flow(login) is True
    assert auth.connected() is True
    assert token_file.exists()

    auth.disconnect()
    assert auth.connected() is False


def test_refresh_token_is_used(tmp_path) -> None:
    request = FakeRequest(
        [(200, {"access_token": "neu", "expires_in": 3600})]
    )
    auth = GoogleAuth("client-id", "secret", token_file=None, request=request)
    auth.tokens = GoogleTokens(refresh_token="r1", expires_at=0)
    assert auth.token() == "neu"
    body = request.calls[0]["data"].decode()
    assert "grant_type=refresh_token" in body
    assert "client_secret=secret" in body


def test_message_contains_attachment(tmp_path) -> None:
    file = tmp_path / "Lebenslauf.pdf"
    file.write_bytes(b"%PDF-1.4 test")
    raw = build_message("Bewerbung", "Guten Tag", "hr@example.ch", [file])
    text = raw.decode("utf-8", errors="replace")
    assert "Subject: Bewerbung" in text
    assert "hr@example.ch" in text
    assert "Lebenslauf.pdf" in text


def test_create_draft_uses_thread_link() -> None:
    client, request = _client(
        [(200, {"id": "draft1", "message": {"id": "m1", "threadId": "t1"}})]
    )
    draft = client.create_draft("Betreff", "Text", "hr@example.ch")
    assert draft["id"] == "draft1"
    assert draft["conversationId"] == "t1"
    assert draft["webLink"].endswith("#all/t1")
    call = request.calls[0]
    assert call["url"].endswith("/drafts")
    assert call["headers"]["Authorization"] == "Bearer token"


def test_find_sent_reads_thread_labels() -> None:
    client, _ = _client(
        [
            (
                200,
                {
                    "messages": [
                        {"id": "m1", "labelIds": ["DRAFT"], "internalDate": "1"},
                        {
                            "id": "m2",
                            "labelIds": ["SENT"],
                            "internalDate": "1763440500000",
                            "payload": {
                                "headers": [
                                    {"name": "Message-ID", "value": "<abc@example>"}
                                ]
                            },
                        },
                    ]
                },
            )
        ]
    )
    sent = client.find_sent("t1")
    assert sent is not None
    assert sent["id"] == "m2"
    assert sent["internetMessageId"] == "<abc@example>"
    assert sent["sentDateTime"].startswith("20")


def test_inbox_since_maps_to_mail_shape() -> None:
    body = base64.urlsafe_b64encode("Leider eine Absage.".encode()).decode()
    client, request = _client(
        [
            (200, {"messages": [{"id": "x1"}]}),
            (
                200,
                {
                    "id": "x1",
                    "threadId": "t1",
                    "internalDate": "1763440500000",
                    "snippet": "Absage",
                    "payload": {
                        "mimeType": "text/plain",
                        "headers": [
                            {"name": "Subject", "value": "Ihre Bewerbung"},
                            {"name": "From", "value": "Firma <hr@example.ch>"},
                        ],
                        "body": {"data": body},
                    },
                },
            ),
        ]
    )
    messages = client.inbox_since("2026-11-17T00:00:00+00:00")
    assert len(messages) == 1
    message = messages[0]
    assert message["conversationId"] == "t1"
    assert message["from"]["emailAddress"]["address"] == "hr@example.ch"
    assert "Absage" in message["body"]["content"]
    assert "in%3Ainbox" in request.calls[0]["url"]
