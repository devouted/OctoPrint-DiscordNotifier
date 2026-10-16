"""Testy jednostkowe. HTTP mockowany — brak realnego ruchu sieciowego."""

import json

import pytest

from octoprint_discord.discord_client import (
    DiscordError,
    DiscordMessage,
    DiscordWebhookClient,
    Embed,
    EmbedField,
    MAX_CONTENT_CHARS,
    MAX_FIELD_VALUE,
)
from octoprint_discord.notifications import (
    PrintEvent,
    PrintStatus,
    build_message,
)


class FakeResponse:
    def __init__(self, status_code=204, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("brak JSON")
        return self._json


class FakeSession:
    """Nagrywa żądania i zwraca zaprogramowane odpowiedzi."""

    def __init__(self, responses=None):
        self.responses = list(responses or [FakeResponse(204)])
        self.calls = []

    def post(self, url, timeout=None, **kwargs):
        self.calls.append({"url": url, "timeout": timeout, **kwargs})
        return self.responses.pop(0)


# ---- Embed / payload ----

def test_color_from_hex():
    assert Embed.color_from_hex("#2ecc71") == 3066993
    assert Embed.color_from_hex("2ecc71") == 3066993


def test_message_requires_content_or_embed():
    with pytest.raises(DiscordError):
        DiscordMessage().to_payload()


def test_payload_contains_embed_and_content():
    msg = DiscordMessage(content="hej", embeds=[Embed(title="T", color=1)])
    payload = msg.to_payload()
    assert payload["content"] == "hej"
    assert payload["embeds"][0]["title"] == "T"
    assert payload["embeds"][0]["color"] == 1


def test_too_many_embeds():
    msg = DiscordMessage(embeds=[Embed(title=str(i)) for i in range(11)])
    with pytest.raises(DiscordError):
        msg.to_payload()


def test_content_truncation():
    msg = DiscordMessage(content="x" * (MAX_CONTENT_CHARS + 50))
    payload = msg.to_payload()
    assert len(payload["content"]) == MAX_CONTENT_CHARS


def test_field_value_truncation():
    f = EmbedField("n", "y" * (MAX_FIELD_VALUE + 10))
    assert len(f.to_dict()["value"]) == MAX_FIELD_VALUE


# ---- Klient: wysyłka JSON ----

def test_send_json_success():
    session = FakeSession([FakeResponse(204)])
    client = DiscordWebhookClient("https://discord.com/api/webhooks/x", session=session)
    client.send(DiscordMessage(content="test"))
    assert len(session.calls) == 1
    assert session.calls[0]["json"]["content"] == "test"
    assert "files" not in session.calls[0]


def test_send_http_200_is_success():
    # Discord zwraca 200 (z obiektem wiadomości) przy multipart/wait=true.
    # To NIE jest błąd — klient musi to zaakceptować.
    session = FakeSession([FakeResponse(200, json_data={"id": "123"}, text='{"id":"123"}')])
    client = DiscordWebhookClient("https://discord.com/api/webhooks/x", session=session)
    client.send(DiscordMessage(content="test"))  # nie rzuca
    assert len(session.calls) == 1


def test_send_snapshot_http_200_is_success():
    # Realny scenariusz z przycisku testu: multipart + snapshot -> Discord 200.
    session = FakeSession([FakeResponse(200, json_data={"id": "123"})])
    client = DiscordWebhookClient("https://discord.com/api/webhooks/x", session=session)
    msg = build_message(PrintEvent.PROGRESS, PrintStatus(filename="a.gcode", progress=42))
    client.send(msg, snapshot=b"\x89PNG\r\n", snapshot_filename="cam.png")  # nie rzuca
    assert "files" in session.calls[0]


def test_invalid_url():
    with pytest.raises(DiscordError):
        DiscordWebhookClient("not-a-url")


def test_non_2xx_raises():
    session = FakeSession([FakeResponse(400, text="bad request")])
    client = DiscordWebhookClient("https://discord.com/api/webhooks/x", session=session)
    with pytest.raises(DiscordError):
        client.send(DiscordMessage(content="x"))


def test_rate_limit_retry_then_success(monkeypatch):
    import octoprint_discord.discord_client as dc
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)  # bez realnego czekania
    session = FakeSession([
        FakeResponse(429, json_data={"retry_after": 0.01}),
        FakeResponse(204),
    ])
    client = DiscordWebhookClient("https://discord.com/api/webhooks/x", session=session)
    client.send(DiscordMessage(content="x"))
    assert len(session.calls) == 2


def test_rate_limit_exhausted(monkeypatch):
    import octoprint_discord.discord_client as dc
    monkeypatch.setattr(dc.time, "sleep", lambda s: None)
    session = FakeSession([FakeResponse(429, json_data={"retry_after": 0.01})] * 5)
    client = DiscordWebhookClient(
        "https://discord.com/api/webhooks/x", session=session, max_retries=2
    )
    with pytest.raises(DiscordError):
        client.send(DiscordMessage(content="x"))
    assert len(session.calls) == 3  # 1 + 2 retry


# ---- Klient: wysyłka ze snapshotem (multipart) ----

def test_send_with_snapshot_uses_multipart():
    session = FakeSession([FakeResponse(204)])
    client = DiscordWebhookClient("https://discord.com/api/webhooks/x", session=session)
    msg = build_message(PrintEvent.DONE, PrintStatus(filename="a.gcode", progress=100))
    client.send(msg, snapshot=b"\x89PNG\r\n", snapshot_filename="cam.png")

    call = session.calls[0]
    assert "files" in call
    assert "json" not in call
    payload = json.loads(call["files"]["payload_json"][1])
    assert payload["embeds"][0]["image"]["url"] == "attachment://cam.png"
    assert call["files"]["files[0]"][0] == "cam.png"


# ---- Szablony powiadomień ----

@pytest.mark.parametrize("event", list(PrintEvent))
def test_build_message_all_events(event):
    status = PrintStatus(
        filename="benchy.gcode",
        progress=42.0,
        elapsed_seconds=1800,
        remaining_seconds=2400,
        printer_name="Prusa",
        error="boom",
    )
    msg = build_message(event, status, mention="@here")
    payload = msg.to_payload()
    assert payload["embeds"][0]["color"] > 0
    assert payload["embeds"][0]["title"]
    assert payload["content"] == "@here"


def test_failed_event_includes_error():
    msg = build_message(
        PrintEvent.FAILED,
        PrintStatus(filename="x.gcode", error="Thermal runaway"),
    )
    fields = msg.to_payload()["embeds"][0]["fields"]
    names = [f["name"] for f in fields]
    assert "Error" in names


def test_non_failed_event_no_error_field():
    msg = build_message(
        PrintEvent.DONE,
        PrintStatus(filename="x.gcode", error="should be ignored"),
    )
    fields = msg.to_payload()["embeds"][0].get("fields", [])
    names = [f["name"] for f in fields]
    assert "Error" not in names


def test_progress_bar_in_fields():
    msg = build_message(PrintEvent.PROGRESS, PrintStatus(progress=50.0))
    fields = msg.to_payload()["embeds"][0]["fields"]
    progress_field = next(f for f in fields if f["name"] == "Progress")
    assert "█" in progress_field["value"]
    assert "50.0%" in progress_field["value"]
