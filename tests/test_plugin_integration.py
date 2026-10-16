"""Testy integracyjne samego pluginu OctoPrint.

Wymaga zainstalowanego OctoPrinta (import octoprint.plugin). Jeśli brak —
testy są pomijane. Wstrzykujemy atrapy ``_settings`` i ``_logger`` oraz
podmieniamy klienta Discord/snapshot, by zweryfikować przepływ bez sieci.
"""

import sys
import types

import pytest

octoprint = pytest.importorskip("octoprint.plugin")

from octoprint_discord_notifier import DiscordNotifierPlugin  # noqa: E402


class FakeSettings:
    """Atrapa SettingsManager OctoPrinta (get/global_get po ścieżce listy)."""

    def __init__(self, values, global_values=None):
        self._values = values
        self._global = global_values or {}

    def get(self, path):
        node = self._values
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return None
        return node

    def global_get(self, path):
        node = self._global
        for key in path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return None
        return node


class FakeLogger:
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def exception(self, *a, **k): pass


def _make_plugin(settings_values, global_values=None):
    plugin = DiscordNotifierPlugin()
    plugin._settings = FakeSettings(settings_values, global_values)
    plugin._logger = FakeLogger()
    return plugin


def _default_settings(**overrides):
    base = dict(
        webhook_url="https://discord.com/api/webhooks/abc/def",
        username="OctoPrint",
        send_snapshot=False,
        event_PrintStarted=True,
        event_PrintDone=True,
        event_PrintFailed=True,
        event_PrintPaused=False,
        event_PrintResumed=False,
        event_PrintCancelled=True,
        event_Connected=False,
        event_Disconnected=False,
        throttle_seconds=10,
    )
    base.update(overrides)
    return base


@pytest.fixture
def app_context():
    """flask.jsonify wymaga kontekstu aplikacji — dostarczamy minimalny."""
    import flask
    app = flask.Flask(__name__)
    with app.app_context():
        yield


@pytest.fixture
def captured(monkeypatch):
    """Przechwytuje wywołania DiscordWebhookClient.send zamiast realnej wysyłki."""
    sent = []

    import octoprint_discord_notifier as plugin_mod

    class FakeClient:
        def __init__(self, url):
            self.url = url

        def send(self, message, snapshot=None, snapshot_filename="snapshot.png"):
            sent.append(dict(url=self.url, message=message, snapshot=snapshot))

    monkeypatch.setattr(plugin_mod, "DiscordWebhookClient", FakeClient)
    return sent


# ---- on_event ----

def test_on_event_enabled_sends(captured):
    plugin = _make_plugin(_default_settings())
    plugin.on_event("PrintStarted", {"name": "benchy.gcode"})
    assert len(captured) == 1
    assert captured[0]["message"].embeds[0].title == "🖨️ Print started"


def test_on_event_connected_disabled_by_default(captured):
    # Connected/Disconnected domyślnie wyłączone.
    plugin = _make_plugin(_default_settings())
    plugin.on_event("Connected", {"port": "/dev/ttyUSB0", "baudrate": 115200})
    plugin.on_event("Disconnected", {})
    assert captured == []


def test_on_event_connected_enabled_sends_with_port(captured):
    plugin = _make_plugin(_default_settings(event_Connected=True))
    plugin.on_event("Connected", {"port": "/dev/ttyUSB0", "baudrate": 115200})
    assert len(captured) == 1
    embed = captured[0]["message"].embeds[0]
    assert embed.title == "🔌 Printer connected"
    field_names = [f.name for f in embed.fields]
    assert "Port" in field_names
    assert "Baudrate" in field_names


def test_on_event_disconnected_enabled_sends(captured):
    plugin = _make_plugin(_default_settings(event_Disconnected=True))
    plugin.on_event("Disconnected", {})
    assert len(captured) == 1
    assert captured[0]["message"].embeds[0].title == "⛔ Printer disconnected"


def test_on_event_disabled_does_not_send(captured):
    plugin = _make_plugin(_default_settings())  # PrintPaused=False
    plugin.on_event("PrintPaused", {"name": "x.gcode"})
    assert captured == []


def test_on_event_unknown_event_ignored(captured):
    plugin = _make_plugin(_default_settings())
    plugin.on_event("ClientOpened", {})
    assert captured == []


def test_on_event_no_webhook_skips(captured):
    plugin = _make_plugin(_default_settings(webhook_url=""))
    plugin.on_event("PrintDone", {"name": "x.gcode"})
    assert captured == []


def test_on_event_failed_includes_error(captured):
    plugin = _make_plugin(_default_settings())
    plugin.on_event("PrintFailed", {"name": "x.gcode", "error": "thermal runaway"})
    assert len(captured) == 1
    fields = captured[0]["message"].embeds[0].fields
    assert any(f.name == "Error" for f in fields)


# ---- on_api_command (przycisk testu) ----

def test_api_test_without_webhook_returns_error(captured, app_context):
    plugin = _make_plugin(_default_settings(webhook_url=""))
    resp = plugin.on_api_command("test", {})
    data = resp.get_json()
    assert data["success"] is False
    assert "webhook" in data["error"].lower()
    assert captured == []


def test_api_test_sends_with_snapshot(captured, monkeypatch, app_context):
    import octoprint_discord_notifier as plugin_mod
    monkeypatch.setattr(plugin_mod, "fetch_snapshot", lambda url, **k: b"IMG")

    plugin = _make_plugin(
        _default_settings(send_snapshot=False),
        global_values={"webcam": {"snapshot": "http://cam/snap"}},
    )
    resp = plugin.on_api_command("test", {})
    data = resp.get_json()
    assert data["success"] is True
    assert len(captured) == 1
    # test wymusza snapshot niezależnie od send_snapshot:
    assert captured[0]["snapshot"] == b"IMG"


def test_api_test_snapshot_failure_still_sends(captured, monkeypatch, app_context):
    import octoprint_discord_notifier as plugin_mod
    from octoprint_discord.snapshot import SnapshotError

    def boom(url, **k):
        raise SnapshotError("cam down")

    monkeypatch.setattr(plugin_mod, "fetch_snapshot", boom)

    plugin = _make_plugin(
        _default_settings(),
        global_values={"webcam": {"snapshot": "http://cam/snap"}},
    )
    resp = plugin.on_api_command("test", {})
    data = resp.get_json()
    assert data["success"] is True
    assert len(captured) == 1
    assert captured[0]["snapshot"] is None  # snapshot się nie udał, ale wysyłka tak


# ---- settings / template vars ----

def test_settings_defaults_structure():
    plugin = DiscordNotifierPlugin()
    defaults = plugin.get_settings_defaults()
    assert "webhook_url" in defaults
    # płaskie klucze checkboxów event_*
    assert "event_PrintStarted" in defaults
    assert isinstance(defaults["event_PrintStarted"], bool)
    assert "event_PrintCancelled" in defaults


def test_api_is_admin_only():
    assert DiscordNotifierPlugin().is_api_adminonly() is True


def test_api_is_protected():
    # Wymagane od OctoPrint 1.11.2 — jawna deklaracja ochrony API.
    assert DiscordNotifierPlugin().is_api_protected() is True


# ---- throttle w on_event ----

class _Clock:
    def __init__(self, start=0.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def _plugin_with_clock(settings_overrides=None):
    from octoprint_discord.throttle import EventThrottle
    plugin = _make_plugin(_default_settings(**(settings_overrides or {})))
    clock = _Clock()
    plugin._throttle = EventThrottle(min_interval=10, time_func=clock)
    return plugin, clock


def test_on_event_throttles_repeated_same_event(captured):
    plugin, clock = _plugin_with_clock()
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    plugin.on_event("PrintFailed", {"name": "x.gcode"})  # natychmiast ponownie
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    assert len(captured) == 1  # tylko pierwsze przeszło


def test_on_event_allows_after_window(captured):
    plugin, clock = _plugin_with_clock()
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    clock.advance(10)
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    assert len(captured) == 2  # po oknie przeszło ponownie


def test_on_event_different_events_not_throttled_together(captured):
    plugin, clock = _plugin_with_clock()
    plugin.on_event("PrintStarted", {"name": "x.gcode"})
    plugin.on_event("PrintCancelled", {"name": "x.gcode"})
    assert len(captured) == 2  # różne typy niezależne


def test_on_event_throttle_zero_disables(captured):
    plugin, clock = _plugin_with_clock({"throttle_seconds": 0})
    for _ in range(4):
        plugin.on_event("PrintFailed", {"name": "x.gcode"})
    assert len(captured) == 4  # throttle wyłączony


def test_on_event_throttle_reads_setting_live(captured):
    # Zmiana throttle_seconds w ustawieniach działa bez restartu.
    plugin, clock = _plugin_with_clock({"throttle_seconds": 10})
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    clock.advance(5)
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    assert len(captured) == 1  # 5s < 10s -> zablokowane
    # użytkownik obniża próg do 2s
    plugin._settings._values["throttle_seconds"] = 2
    plugin.on_event("PrintFailed", {"name": "x.gcode"})
    assert len(captured) == 2  # 5s >= 2s -> przechodzi


def test_api_test_not_affected_by_throttle(captured, app_context):
    # Przycisk testu woła _send bezpośrednio — można testować wielokrotnie.
    plugin, clock = _plugin_with_clock()
    plugin.on_event("PrintFailed", {"name": "x.gcode"})  # zużywa okno dla eventu
    plugin.on_api_command("test", {})
    plugin.on_api_command("test", {})
    # 1 event + 2 testy = 3 wysyłki (testy nie podlegają throttle)
    assert len(captured) == 3
