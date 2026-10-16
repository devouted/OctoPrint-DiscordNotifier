"""Throttle/deduplikacja powiadomień per typ zdarzenia.

Chroni przed serią identycznych powiadomień w krótkim czasie (np. gdy port
szeregowy drukarki migocze i OctoPrint kilka razy pod rząd zgłosi PrintFailed).

Zasada: dla danego typu zdarzenia nie przepuszczaj kolejnego częściej niż co
``min_interval`` sekund. Ustawienie progu na 0 (lub ujemny) WYŁĄCZA throttle —
każde zdarzenie przechodzi.

Klasa jest niezależna od OctoPrinta i czasu systemowego (czas podaje się jawnie),
dzięki czemu jest w pełni testowalna.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional


class EventThrottle:
    def __init__(
        self,
        min_interval: float = 10.0,
        time_func: Optional[Callable[[], float]] = None,
    ) -> None:
        """
        Args:
            min_interval: minimalny odstęp (sekundy) między powiadomieniami tego
                samego typu. <= 0 oznacza brak throttle.
            time_func: źródło czasu monotonicznego (domyślnie time.monotonic);
                wstrzykiwane w testach.
        """
        self.min_interval = min_interval
        self._time = time_func or time.monotonic
        self._last_sent: Dict[str, float] = {}
        self._lock = threading.Lock()

    def should_send(self, event_key: str, now: Optional[float] = None) -> bool:
        """Czy przepuścić zdarzenie danego typu teraz?

        Zwraca True i zapisuje znacznik czasu, gdy minął wymagany odstęp (lub
        throttle wyłączony). Zwraca False, jeśli identyczne zdarzenie wysłano
        zbyt niedawno. Wywołania są bezpieczne wątkowo.
        """
        if self.min_interval <= 0:
            return True

        current = now if now is not None else self._time()
        with self._lock:
            last = self._last_sent.get(event_key)
            if last is not None and (current - last) < self.min_interval:
                return False
            self._last_sent[event_key] = current
            return True

    def reset(self, event_key: Optional[str] = None) -> None:
        """Czyści historię (całą lub dla jednego typu zdarzenia)."""
        with self._lock:
            if event_key is None:
                self._last_sent.clear()
            else:
                self._last_sent.pop(event_key, None)
