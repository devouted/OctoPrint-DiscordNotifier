"""Lekki klient webhooka Discord.

Moduł jest całkowicie niezależny od OctoPrinta — można go testować lokalnie.
Discord webhook: POST JSON (lub multipart gdy dołączamy plik) na URL webhooka.
Sukces = HTTP 204 No Content. Przy przekroczeniu limitu = HTTP 429 z polem
``retry_after`` (sekundy).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Discordowe limity (patrz dokumentacja API).
MAX_CONTENT_CHARS = 2000
MAX_EMBEDS = 10
MAX_FIELD_NAME = 256
MAX_FIELD_VALUE = 1024


class DiscordError(Exception):
    """Błąd komunikacji z Discordem."""


@dataclass
class EmbedField:
    name: str
    value: str
    inline: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": _truncate(self.name, MAX_FIELD_NAME),
            "value": _truncate(self.value, MAX_FIELD_VALUE),
            "inline": self.inline,
        }


@dataclass
class Embed:
    """Reprezentacja pojedynczego embeda Discord.

    ``color`` podajemy jako liczbę całkowitą (dziesiętnie!). Discord nie
    akceptuje stringów hex — konwertuj przez ``Embed.color_from_hex``.
    """

    title: Optional[str] = None
    description: Optional[str] = None
    color: Optional[int] = None
    url: Optional[str] = None
    timestamp: Optional[str] = None
    fields: List[EmbedField] = field(default_factory=list)
    footer_text: Optional[str] = None
    footer_icon_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    image_url: Optional[str] = None
    author_name: Optional[str] = None
    author_icon_url: Optional[str] = None

    @staticmethod
    def color_from_hex(hex_color: str) -> int:
        """Konwersja '#RRGGBB' lub 'RRGGBB' na int wymagany przez Discord."""
        return int(hex_color.lstrip("#"), 16)

    def add_field(self, name: str, value: str, inline: bool = False) -> "Embed":
        self.fields.append(EmbedField(name, value, inline))
        return self

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.title is not None:
            data["title"] = self.title
        if self.description is not None:
            data["description"] = self.description
        if self.color is not None:
            data["color"] = self.color
        if self.url is not None:
            data["url"] = self.url
        if self.timestamp is not None:
            data["timestamp"] = self.timestamp
        if self.fields:
            data["fields"] = [f.to_dict() for f in self.fields]
        if self.footer_text is not None:
            footer: Dict[str, Any] = {"text": self.footer_text}
            if self.footer_icon_url is not None:
                footer["icon_url"] = self.footer_icon_url
            data["footer"] = footer
        if self.thumbnail_url is not None:
            data["thumbnail"] = {"url": self.thumbnail_url}
        if self.image_url is not None:
            data["image"] = {"url": self.image_url}
        if self.author_name is not None:
            author: Dict[str, Any] = {"name": self.author_name}
            if self.author_icon_url is not None:
                author["icon_url"] = self.author_icon_url
            data["author"] = author
        return data


@dataclass
class DiscordMessage:
    """Pełna wiadomość do wysłania na webhook."""

    content: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    embeds: List[Embed] = field(default_factory=list)

    def to_payload(self) -> Dict[str, Any]:
        if not self.content and not self.embeds:
            raise DiscordError(
                "Wiadomość musi zawierać 'content' lub przynajmniej jeden embed."
            )
        if len(self.embeds) > MAX_EMBEDS:
            raise DiscordError(
                f"Discord pozwala na maks. {MAX_EMBEDS} embedów, podano {len(self.embeds)}."
            )

        payload: Dict[str, Any] = {}
        if self.content:
            payload["content"] = _truncate(self.content, MAX_CONTENT_CHARS)
        if self.username:
            payload["username"] = self.username
        if self.avatar_url:
            payload["avatar_url"] = self.avatar_url
        if self.embeds:
            payload["embeds"] = [e.to_dict() for e in self.embeds]
        return payload


class DiscordWebhookClient:
    """Klient wysyłający wiadomości na webhook Discord.

    Args:
        webhook_url: pełny URL webhooka z Discorda.
        timeout: timeout pojedynczego żądania HTTP (sekundy).
        max_retries: ile razy ponowić przy odpowiedzi 429 (rate limit).
        session: opcjonalna sesja requests (ułatwia testy i reużycie połączeń).
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: float = 10.0,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not webhook_url or not webhook_url.startswith("http"):
            raise DiscordError("Nieprawidłowy webhook_url.")
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = session or requests.Session()

    def send(
        self,
        message: DiscordMessage,
        snapshot: Optional[bytes] = None,
        snapshot_filename: str = "snapshot.png",
    ) -> None:
        """Wysyła wiadomość. Opcjonalnie dołącza snapshot jako plik.

        Gdy ``snapshot`` jest podany, wysyłamy multipart/form-data i podpinamy
        obraz do pierwszego embeda przez ``attachment://`` (nie trzeba hostować
        obrazka na zewnątrz).
        """
        payload = message.to_payload()

        if snapshot is not None:
            if message.embeds:
                payload["embeds"][0]["image"] = {
                    "url": f"attachment://{snapshot_filename}"
                }
            self._post_multipart(payload, snapshot, snapshot_filename)
        else:
            self._post_json(payload)

    def _post_json(self, payload: Dict[str, Any]) -> None:
        self._request(json=payload)

    def _post_multipart(
        self, payload: Dict[str, Any], snapshot: bytes, filename: str
    ) -> None:
        files = {
            "payload_json": (None, json.dumps(payload), "application/json"),
            "files[0]": (filename, snapshot, "application/octet-stream"),
        }
        self._request(files=files)

    def _request(self, **kwargs: Any) -> None:
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._session.post(
                    self.webhook_url, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                raise DiscordError(f"Błąd sieci przy wysyłce do Discorda: {exc}") from exc

            # Discord zwraca 204 (No Content) dla zwykłego POST, ale 200 z
            # obiektem utworzonej wiadomości gdy wysyłamy multipart (załącznik)
            # lub użyto ?wait=true. Każdy kod 2xx oznacza sukces.
            if 200 <= resp.status_code < 300:
                logger.debug("Discord: wysłano (HTTP %d).", resp.status_code)
                return

            if resp.status_code == 429 and attempt <= self.max_retries:
                retry_after = _parse_retry_after(resp)
                logger.warning(
                    "Discord rate limit (429), ponawiam za %.2fs (próba %d/%d).",
                    retry_after,
                    attempt,
                    self.max_retries,
                )
                time.sleep(retry_after)
                continue

            raise DiscordError(
                f"Discord odrzucił żądanie: HTTP {resp.status_code} — {resp.text[:500]}"
            )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _parse_retry_after(resp: requests.Response) -> float:
    try:
        data = resp.json()
        if isinstance(data, dict) and "retry_after" in data:
            return float(data["retry_after"])
    except (ValueError, TypeError):
        pass
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return 1.0
