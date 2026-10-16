# coding=utf-8
"""Plugin OctoPrint: powiadomienia na Discord przez webhook.

Łączy mixiny OctoPrinta z czystą biblioteką ``octoprint_discord`` (klient
webhooka + szablony powiadomień). Dzięki temu logika Discorda jest testowana
niezależnie, a ten moduł zajmuje się tylko integracją z OctoPrintem:

- SettingsPlugin   -> webhook URL + checkboxy eventów
- EventHandlerPlugin -> reakcja na zdarzenia druku
- SimpleApiPlugin  -> przycisk "Testuj" (wysyła testowe powiadomienie + snapshot)
- TemplatePlugin / AssetPlugin -> panel ustawień (jinja2 + JS viewmodel)
"""

from __future__ import absolute_import

import flask
import octoprint.plugin

from octoprint_discord.discord_client import DiscordError, DiscordWebhookClient
from octoprint_discord.events import (
    DEFAULT_ENABLED_EVENTS,
    map_event,
)
from octoprint_discord.notifications import PrintEvent, PrintStatus, build_message
from octoprint_discord.snapshot import SnapshotError, fetch_snapshot
from octoprint_discord.throttle import EventThrottle


class DiscordNotifierPlugin(
    octoprint.plugin.SettingsPlugin,
    octoprint.plugin.EventHandlerPlugin,
    octoprint.plugin.SimpleApiPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.AssetPlugin,
):
    def __init__(self):
        super().__init__()
        # Throttle tworzony leniwie; próg jest odświeżany z ustawień przy każdym
        # zdarzeniu, więc zmiana w panelu działa bez restartu OctoPrinta.
        self._throttle = EventThrottle(min_interval=10.0)

    # ---- SettingsPlugin ----

    def get_settings_defaults(self):
        defaults = dict(
            webhook_url="",
            username="OctoPrint",
            send_snapshot=True,
            # Minimalny odstęp (sekundy) między powiadomieniami tego samego typu.
            # Chroni przed serią np. przy migotaniu portu szeregowego. 0 = wyłącz.
            throttle_seconds=10,
        )
        # Płaskie klucze dla checkboxów: event_PrintStarted itd. Płaska struktura
        # jest niezawodnie bindowana przez Knockout w panelu ustawień (zagnieżdżony
        # dict z dynamicznymi kluczami bywa problematyczny).
        for name, enabled in DEFAULT_ENABLED_EVENTS.items():
            defaults["event_" + name] = enabled
        return defaults

    def get_settings_restricted_paths(self):
        # webhook URL to sekret — nie wysyłaj go do nieuprawnionych klientów.
        return dict(admin=[["webhook_url"]])

    # ---- TemplatePlugin ----

    def get_template_configs(self):
        return [dict(type="settings", name="Discord Notifier", custom_bindings=True)]

    def is_template_autoescaped(self):
        # Włączamy autoescaping templatek (wymagane globalnie od OctoPrint 1.13.0).
        # Nasz template nie renderuje niezaufanych danych, więc jest to bezpieczne.
        return True

    # ---- AssetPlugin ----

    def get_assets(self):
        return dict(js=["js/discord_notifier.js"])

    # ---- EventHandlerPlugin ----

    def on_event(self, event, payload):
        print_event = map_event(event)
        if print_event is None:
            return  # zdarzenie nas nie interesuje

        if not self._settings.get(["event_" + event]):
            self._logger.debug("Event %s disabled in settings — skipping.", event)
            return

        webhook_url = self._settings.get(["webhook_url"])
        if not webhook_url:
            self._logger.warning("No webhook URL — skipping notification for %s.", event)
            return

        # Throttle: nie wysyłaj tego samego typu zdarzenia częściej niż co N sekund.
        # Odświeżamy próg z ustawień, by zmiana w panelu działała bez restartu.
        self._throttle.min_interval = self._throttle_seconds()
        if not self._throttle.should_send(event):
            self._logger.info(
                "Event %s skipped (throttle %ss) — sent too recently.",
                event,
                self._throttle.min_interval,
            )
            return

        status = self._status_from_payload(payload)
        self._send(print_event, status)

    def _throttle_seconds(self):
        """Czyta próg throttle z ustawień; odporny na puste/niepoprawne wartości."""
        raw = self._settings.get(["throttle_seconds"])
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 10.0

    # ---- SimpleApiPlugin (przycisk Testuj) ----

    def get_api_commands(self):
        return dict(test=[])

    def is_api_adminonly(self):
        return True

    def is_api_protected(self):
        # Jawnie deklarujemy ochronę (wymagane od OctoPrint 1.11.2 — inaczej
        # OctoPrint loguje ostrzeżenie o poleganiu na domyślnej implementacji).
        return True

    def on_api_command(self, command, data):
        if command != "test":
            return flask.abort(400)

        webhook_url = self._settings.get(["webhook_url"])
        if not webhook_url:
            return flask.jsonify(success=False, error="Webhook URL is not set.")

        status = PrintStatus(
            filename="test_print.gcode",
            progress=42.0,
            elapsed_seconds=1800,
            remaining_seconds=2400,
            printer_name=self._settings.get(["username"]) or "OctoPrint",
        )
        try:
            self._send(PrintEvent.PROGRESS, status, force_snapshot=True)
        except Exception as exc:  # pragma: no cover - defensywnie
            self._logger.exception("Test notification failed.")
            return flask.jsonify(success=False, error=str(exc))

        return flask.jsonify(success=True)

    # ---- Logika wysyłki (wspólna dla eventów i testu) ----

    def _send(self, print_event, status, force_snapshot=False):
        webhook_url = self._settings.get(["webhook_url"])
        username = self._settings.get(["username"]) or None
        want_snapshot = force_snapshot or self._settings.get(["send_snapshot"])

        snapshot_bytes = None
        if want_snapshot:
            snapshot_bytes = self._try_fetch_snapshot()

        message = build_message(
            print_event,
            status,
            username=username,
            has_snapshot=snapshot_bytes is not None,
        )

        client = DiscordWebhookClient(webhook_url)
        try:
            client.send(message, snapshot=snapshot_bytes)
            self._logger.info("Sent Discord notification: %s", print_event.value)
        except DiscordError as exc:
            self._logger.error("Discord: %s", exc)
            raise

    def _try_fetch_snapshot(self):
        """Pobiera snapshot ze skonfigurowanej w OctoPrint kamery.

        Zwraca bajty lub None (gdy brak URL / błąd — powiadomienie pójdzie bez obrazka).
        """
        snapshot_url, verify_ssl = self._resolve_snapshot_url()
        if not snapshot_url:
            self._logger.info("No webcam snapshot URL configured — sending without image.")
            return None
        try:
            return fetch_snapshot(snapshot_url, verify_ssl=verify_ssl)
        except SnapshotError as exc:
            self._logger.warning("Could not fetch snapshot: %s", exc)
            return None

    def _resolve_snapshot_url(self):
        """Zwraca (snapshot_url, verify_ssl) ze skonfigurowanej kamery.

        Preferuje nowy system kamer wprowadzony w OctoPrint 1.9
        (``octoprint.webcams.get_snapshot_webcam``), który nie generuje
        ostrzeżeń o przestarzałej ścieżce ustawień. Dla starszych wersji
        OctoPrinta używa fallbacku na dawny odczyt ``webcam.snapshot``.
        """
        # Nowy system kamer (1.9+):
        try:
            from octoprint.webcams import get_snapshot_webcam

            webcam = get_snapshot_webcam()
            if webcam is not None and webcam.config is not None:
                compat = webcam.config.compat
                if compat is not None and getattr(compat, "snapshot", None):
                    verify = getattr(compat, "snapshotSslValidation", True)
                    return compat.snapshot, verify
        except ImportError:
            # Starszy OctoPrint bez modułu webcams — spadamy do fallbacku.
            pass
        except Exception as exc:  # pragma: no cover - defensywnie
            self._logger.warning("Could not read webcam (new API): %s", exc)

        # Fallback dla OctoPrint < 1.9 (dawny, przestarzały odczyt):
        url = self._settings.global_get(["webcam", "snapshot"])
        return url, True


    def _status_from_payload(self, payload):
        payload = payload or {}
        progress = None
        # PrintDone ma 100%, inne eventy często nie niosą progresu w payloadzie.
        name = payload.get("name") or payload.get("path")
        return PrintStatus(
            filename=name,
            progress=progress,
            elapsed_seconds=payload.get("time"),
            printer_name=self._settings.get(["username"]) or "OctoPrint",
            error=payload.get("error"),
            # zdarzenie Connected niesie port/baudrate:
            port=payload.get("port"),
            baudrate=payload.get("baudrate"),
        )

    # ---- Software Update Hook ----

    def get_update_information(self):
        """Konfiguracja dla bundled Software Update Plugin OctoPrinta.

        Pozwala aktualizować plugin z poziomu OctoPrinta po opublikowaniu
        nowego release'u na GitHubie (typ: github_release).
        """
        return dict(
            discord_notifier=dict(
                displayName="Discord Notifier",
                displayVersion=self._plugin_version,
                type="github_release",
                user="devouted",
                repo="OctoPrint-DiscordNotifier",
                current=self._plugin_version,
                stable_branch=dict(
                    name="Stable", branch="main", comittish=["main"]
                ),
                pip="https://github.com/devouted/OctoPrint-DiscordNotifier/archive/{target_version}.zip",
            )
        )


__plugin_name__ = "Discord Notifier"
__plugin_version__ = "0.1.5"
__plugin_pythoncompat__ = ">=3.7,<4"
__plugin_implementation__ = DiscordNotifierPlugin()
__plugin_hooks__ = {
    "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
}
