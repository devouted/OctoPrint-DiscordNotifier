"""Mapowanie nazw zdarzeń OctoPrint na wewnętrzne PrintEvent.

Nazwy zdarzeń pochodzą z OctoPrint (octoprint.events.Events). Trzymamy je jako
zwykłe stringi, żeby moduł pozostał testowalny bez instalacji OctoPrinta.
Lista kluczy = eventy, które użytkownik może włączać/wyłączać w panelu.
"""

from __future__ import annotations

from typing import Dict, Optional

from .notifications import PrintEvent

# Klucz = nazwa zdarzenia OctoPrint, wartość = nasz PrintEvent.
OCTOPRINT_EVENT_MAP: Dict[str, PrintEvent] = {
    "PrintStarted": PrintEvent.STARTED,
    "PrintDone": PrintEvent.DONE,
    "PrintFailed": PrintEvent.FAILED,
    "PrintPaused": PrintEvent.PAUSED,
    "PrintResumed": PrintEvent.RESUMED,
    "PrintCancelled": PrintEvent.CANCELLED,
    "Connected": PrintEvent.CONNECTED,
    "Disconnected": PrintEvent.DISCONNECTED,
}

# Domyślne ustawienia checkboxów (które eventy są włączone zaraz po instalacji).
DEFAULT_ENABLED_EVENTS: Dict[str, bool] = {
    "PrintStarted": True,
    "PrintDone": True,
    "PrintFailed": True,
    "PrintPaused": False,
    "PrintResumed": False,
    "PrintCancelled": True,
    "Connected": False,
    "Disconnected": False,
}

# Human-readable labels for the settings panel.
EVENT_LABELS: Dict[str, str] = {
    "PrintStarted": "Print started",
    "PrintDone": "Print done",
    "PrintFailed": "Print failed",
    "PrintPaused": "Paused",
    "PrintResumed": "Resumed",
    "PrintCancelled": "Cancelled",
    "Connected": "Printer connected",
    "Disconnected": "Printer disconnected",
}


def map_event(octoprint_event: str) -> Optional[PrintEvent]:
    """Zwraca PrintEvent dla nazwy zdarzenia OctoPrint lub None, gdy nieobsługiwane."""
    return OCTOPRINT_EVENT_MAP.get(octoprint_event)
