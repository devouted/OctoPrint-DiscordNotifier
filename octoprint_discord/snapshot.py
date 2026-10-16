"""Pobieranie snapshotu z kamery przez skonfigurowany w OctoPrint URL.

OctoPrint trzyma URL snapshotu w ustawieniach (``webcam.snapshot``), np.
``http://127.0.0.1:8080/?action=snapshot``. Ten helper tylko pobiera obraz
spod podanego URL — jest niezależny od OctoPrinta, więc da się go testować.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """Nie udało się pobrać snapshotu."""


def fetch_snapshot(
    snapshot_url: str,
    timeout: float = 10.0,
    session: Optional[requests.Session] = None,
    verify_ssl: bool = True,
) -> bytes:
    """Pobiera obraz spod snapshot URL i zwraca surowe bajty.

    Args:
        snapshot_url: pełny URL snapshotu (ze skonfigurowanej w OctoPrint kamery).
        timeout: timeout żądania w sekundach.
        session: opcjonalna sesja requests (ułatwia testy).
        verify_ssl: weryfikacja certyfikatu (dla lokalnych kamer po https czasem
            trzeba wyłączyć).

    Raises:
        SnapshotError: gdy brak URL, błąd sieci lub odpowiedź nie jest obrazem.
    """
    if not snapshot_url:
        raise SnapshotError(
            "Brak skonfigurowanego URL snapshotu kamery w OctoPrint "
            "(Settings → Webcam & Timelapse)."
        )

    sess = session or requests
    try:
        resp = sess.get(snapshot_url, timeout=timeout, verify=verify_ssl)
    except requests.RequestException as exc:
        raise SnapshotError(f"Błąd pobierania snapshotu: {exc}") from exc

    if resp.status_code != 200:
        raise SnapshotError(
            f"Kamera zwróciła HTTP {resp.status_code} dla snapshotu."
        )

    content = resp.content
    if not content:
        raise SnapshotError("Kamera zwróciła pustą odpowiedź.")

    content_type = resp.headers.get("Content-Type", "")
    if content_type and not content_type.lower().startswith("image/"):
        logger.warning(
            "Snapshot ma nietypowy Content-Type '%s' — próbuję mimo to.",
            content_type,
        )

    return content
