"""Szablony powiadomień: mapowanie zdarzeń druku na wiadomości Discord.

Warstwa jest niezależna od OctoPrinta — przyjmuje zwykłe dane (nazwa pliku,
procent postępu, czasy) i produkuje ``DiscordMessage``. Dzięki temu zarówno
plugin, jak i lokalny CLI korzystają z tej samej logiki.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .discord_client import DiscordMessage, Embed


class PrintEvent(str, Enum):
    STARTED = "started"
    DONE = "done"
    FAILED = "failed"
    PAUSED = "paused"
    RESUMED = "resumed"
    PROGRESS = "progress"
    CANCELLED = "cancelled"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


# Kolory embedów (dziesiętnie — tak jak wymaga Discord).
_COLORS = {
    PrintEvent.STARTED: Embed.color_from_hex("#3498db"),    # niebieski
    PrintEvent.DONE: Embed.color_from_hex("#2ecc71"),       # zielony
    PrintEvent.FAILED: Embed.color_from_hex("#e74c3c"),     # czerwony
    PrintEvent.PAUSED: Embed.color_from_hex("#f1c40f"),     # żółty
    PrintEvent.RESUMED: Embed.color_from_hex("#1abc9c"),    # turkus
    PrintEvent.PROGRESS: Embed.color_from_hex("#9b59b6"),   # fioletowy
    PrintEvent.CANCELLED: Embed.color_from_hex("#95a5a6"),  # szary
    PrintEvent.CONNECTED: Embed.color_from_hex("#2ecc71"),  # zielony
    PrintEvent.DISCONNECTED: Embed.color_from_hex("#e67e22"), # pomarańczowy
}

_TITLES = {
    PrintEvent.STARTED: "🖨️ Print started",
    PrintEvent.DONE: "✅ Print done",
    PrintEvent.FAILED: "❌ Print failed",
    PrintEvent.PAUSED: "⏸️ Print paused",
    PrintEvent.RESUMED: "▶️ Print resumed",
    PrintEvent.PROGRESS: "📊 Print progress",
    PrintEvent.CANCELLED: "🛑 Print cancelled",
    PrintEvent.CONNECTED: "🔌 Printer connected",
    PrintEvent.DISCONNECTED: "⛔ Printer disconnected",
}


@dataclass
class PrintStatus:
    """Stan druku przekazywany do budowania powiadomienia."""

    filename: Optional[str] = None
    progress: Optional[float] = None          # 0-100
    elapsed_seconds: Optional[float] = None   # czas który minął
    remaining_seconds: Optional[float] = None # szacowany czas do końca
    printer_name: Optional[str] = None
    error: Optional[str] = None
    port: Optional[str] = None                # port szeregowy (Connected)
    baudrate: Optional[int] = None            # prędkość (Connected)


def build_message(
    event: PrintEvent,
    status: PrintStatus,
    *,
    username: Optional[str] = None,
    avatar_url: Optional[str] = None,
    mention: Optional[str] = None,
    has_snapshot: bool = False,
) -> DiscordMessage:
    """Buduje ``DiscordMessage`` dla danego zdarzenia.

    Args:
        event: typ zdarzenia druku.
        status: dane o stanie druku.
        username/avatar_url: nadpisanie tożsamości webhooka.
        mention: np. '<@123456789>' lub '@here' — doklejane do content.
        has_snapshot: jeśli True, embed oczekuje że klient dołączy obrazek
            (image zostanie ustawione przez klienta na attachment://).
    """
    embed = Embed(
        title=_TITLES[event],
        color=_COLORS[event],
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    if status.printer_name:
        embed.author_name = status.printer_name

    if status.port:
        embed.add_field("Port", f"`{status.port}`", inline=True)

    if status.baudrate:
        embed.add_field("Baudrate", str(status.baudrate), inline=True)

    if status.filename:
        embed.add_field("File", f"`{status.filename}`", inline=False)

    if status.progress is not None:
        embed.add_field(
            "Progress",
            f"{_progress_bar(status.progress)} {status.progress:.1f}%",
            inline=False,
        )

    if status.elapsed_seconds is not None:
        embed.add_field("Print time", _format_duration(status.elapsed_seconds), inline=True)

    if status.remaining_seconds is not None:
        embed.add_field("Remaining", _format_duration(status.remaining_seconds), inline=True)

    if event == PrintEvent.FAILED and status.error:
        embed.add_field("Error", status.error, inline=False)

    embed.footer_text = "OctoPrint → Discord"

    content = mention if mention else None

    msg = DiscordMessage(
        content=content,
        username=username,
        avatar_url=avatar_url,
        embeds=[embed],
    )
    return msg


def _progress_bar(percent: float, slots: int = 20) -> str:
    percent = max(0.0, min(100.0, percent))
    filled = int(round(percent / 100 * slots))
    return "█" * filled + "░" * (slots - filled)


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"
