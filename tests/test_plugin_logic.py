"""Testy logiki pluginu niezależnej od OctoPrinta: mapowanie eventów + snapshot.

Sam moduł pluginu importuje ``octoprint``, więc tu testujemy czystą bibliotekę
``octoprint_discord`` (events, snapshot), która stanowi całą logikę pluginu.
HTTP jest mockowany — brak realnej sieci.
"""

import pytest

from octoprint_discord.events import (
    DEFAULT_ENABLED_EVENTS,
    EVENT_LABELS,
    OCTOPRINT_EVENT_MAP,
    map_event,
)
from octoprint_discord.notifications import PrintEvent
from octoprint_discord.snapshot import SnapshotError, fetch_snapshot


# ---- mapowanie zdarzeń OctoPrint ----

def test_map_known_events():
    assert map_event("PrintStarted") == PrintEvent.STARTED
    assert map_event("PrintDone") == PrintEvent.DONE
    assert map_event("PrintFailed") == PrintEvent.FAILED
    assert map_event("PrintPaused") == PrintEvent.PAUSED
    assert map_event("PrintResumed") == PrintEvent.RESUMED
    assert map_event("PrintCancelled") == PrintEvent.CANCELLED
    assert map_event("Connected") == PrintEvent.CONNECTED
    assert map_event("Disconnected") == PrintEvent.DISCONNECTED


def test_map_unknown_event_returns_none():
    assert map_event("ZChangeOrSomethingElse") is None
    assert map_event("") is None


def test_every_mapped_event_has_label_and_default():
    for key in OCTOPRINT_EVENT_MAP:
        assert key in EVENT_LABELS, f"brak etykiety dla {key}"
        assert key in DEFAULT_ENABLED_EVENTS, f"brak domyślnej wartości dla {key}"


def test_defaults_are_booleans():
    assert all(isinstance(v, bool) for v in DEFAULT_ENABLED_EVENTS.values())


# ---- filtrowanie per-checkbox (symulacja decyzji on_event) ----

def _should_notify(event_name, enabled_map):
    """Odwzorowuje decyzję pluginu: znany event + włączony checkbox."""
    if map_event(event_name) is None:
        return False
    return bool(enabled_map.get(event_name))


def test_disabled_event_is_filtered_out():
    enabled = {"PrintStarted": False, "PrintDone": True}
    assert _should_notify("PrintStarted", enabled) is False
    assert _should_notify("PrintDone", enabled) is True


def test_unknown_event_never_notifies():
    assert _should_notify("ClientOpened", {"ClientOpened": True}) is False


# ---- snapshot ----

class FakeResp:
    def __init__(self, status_code=200, content=b"img", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"Content-Type": "image/jpeg"}


class FakeSession:
    def __init__(self, resp=None, exc=None):
        self._resp = resp
        self._exc = exc
        self.calls = []

    def get(self, url, timeout=None, verify=True):
        self.calls.append({"url": url, "timeout": timeout, "verify": verify})
        if self._exc:
            raise self._exc
        return self._resp


def test_fetch_snapshot_success():
    session = FakeSession(FakeResp(200, b"\x89PNG\r\n"))
    data = fetch_snapshot("http://cam/snapshot", session=session)
    assert data == b"\x89PNG\r\n"
    assert session.calls[0]["url"] == "http://cam/snapshot"


def test_fetch_snapshot_empty_url():
    with pytest.raises(SnapshotError):
        fetch_snapshot("")


def test_fetch_snapshot_non_200():
    session = FakeSession(FakeResp(404, b""))
    with pytest.raises(SnapshotError):
        fetch_snapshot("http://cam/snapshot", session=session)


def test_fetch_snapshot_empty_body():
    session = FakeSession(FakeResp(200, b""))
    with pytest.raises(SnapshotError):
        fetch_snapshot("http://cam/snapshot", session=session)


def test_fetch_snapshot_network_error():
    import requests
    session = FakeSession(exc=requests.ConnectionError("boom"))
    with pytest.raises(SnapshotError):
        fetch_snapshot("http://cam/snapshot", session=session)


def test_fetch_snapshot_non_image_content_type_still_returns():
    # Nietypowy content-type: logujemy ostrzeżenie, ale zwracamy dane.
    session = FakeSession(FakeResp(200, b"data", headers={"Content-Type": "application/octet-stream"}))
    data = fetch_snapshot("http://cam/snapshot", session=session)
    assert data == b"data"
