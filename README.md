# OctoPrint-DiscordNotifier

An OctoPrint plugin that sends print notifications directly to a Discord
channel via **webhook** — no intermediate relay script required.

## Features

- Configure the Discord **webhook URL** in the settings panel.
- **Checkboxes** to select which events trigger a notification:
  - Print started / Print done / Print failed
  - Paused / Resumed / Cancelled
  - Printer connected / Printer disconnected
- **Webcam snapshot** — notifications (and the test) can attach an image from
  the webcam configured in OctoPrint. The image is sent as an attachment
  (`multipart`), with no need to host it externally.
- **Notification limit (throttle)** — a configurable interval (default 10 s)
  that prevents a burst of identical notifications (e.g. when the printer's
  serial port flaps). `0` disables the limit.
- **"Send test"** button — sends a sample notification together with a webcam
  image (if configured). The test is not subject to throttling.
- Rich embeds with a per-event-type color, a progress bar, timestamps and
  port/baudrate (for the connection event).

## Architecture

The project is deliberately split into two parts so the Discord logic stays
independent of OctoPrint and fully testable:

- **`octoprint_discord/`** — a pure library (no OctoPrint dependency):
  - `discord_client.py` — webhook client (JSON + multipart, retry on 429,
    accepts any 2xx response, field limits and truncation).
  - `notifications.py` — builds messages/embeds for each event type.
  - `snapshot.py` — fetches the image from the webcam snapshot URL.
  - `events.py` — maps OctoPrint event names to internal types, default
    checkbox values and labels.
  - `throttle.py` — deduplication/throttling of notifications per event type.
  - `cli.py` — local CLI for testing without OctoPrint.
- **`octoprint_discord_notifier/`** — the actual OctoPrint plugin:
  - `__init__.py` — mixins (Settings, EventHandler, SimpleApi, Template,
    Asset), event mapping, test-button API, snapshot fetching.
  - `templates/discord_notifier_settings.jinja2` — settings panel.
  - `static/js/discord_notifier.js` — view model (test button).

## Requirements

- OctoPrint (tested on 1.11.x, Python 3.12; declared compatibility `>=3.7,<4`).
- Runtime dependency: `requests`.

## Installation

The easiest way is via the **Plugin Manager** in OctoPrint:

1. *Settings → Plugin Manager → Get More… → "… from an uploaded archive"*.
2. Select the file `dist/octoprint_discordnotifier-<version>.tar.gz`.
3. Install and restart OctoPrint.

Alternatively, from the command line in OctoPrint's active venv:

```bash
pip install dist/octoprint_discordnotifier-<version>.tar.gz
```

> Note: `setup.py` intentionally does **not** depend on `octoprint_setuptools`,
> so the build also works in an isolated pip environment (like the Plugin
> Manager uses). OctoPrint is **not** listed in `install_requires`, so pip does
> not try to rebuild it.

## Configuration

1. In Discord: *channel settings → Integrations → Webhooks → Copy Webhook URL*.
2. In OctoPrint: *Settings → Discord Notifier* → paste the URL into the
   **Webhook URL** field.
3. Select events (checkboxes), optionally set a **username** and the
   **notification limit**, then save.
4. (Optional) configure the webcam snapshot URL in *Settings → Webcam &
   Timelapse* so the test and notifications attach an image; enable
   **"Attach webcam image"**.
5. Click **Send test** to verify the configuration.

### Settings

| Setting | Description | Default |
|---|---|---|
| `webhook_url` | Discord webhook URL | (empty) |
| `username` | Message author name shown on Discord | `OctoPrint` |
| `send_snapshot` | Attach a webcam image to notifications | `true` |
| `throttle_seconds` | Min. interval between notifications of the same type; `0` = disabled | `10` |
| `event_PrintStarted` | Notify on print start | `true` |
| `event_PrintDone` | Notify on print completion | `true` |
| `event_PrintFailed` | Notify on print failure | `true` |
| `event_PrintPaused` | Notify on pause | `false` |
| `event_PrintResumed` | Notify on resume | `false` |
| `event_PrintCancelled` | Notify on cancellation | `true` |
| `event_Connected` | Notify when the printer connects | `false` |
| `event_Disconnected` | Notify when the printer disconnects | `false` |

## Local testing without OctoPrint (CLI)

The `octoprint_discord` library works standalone. Preview the payload without
sending:

```bash
python -m octoprint_discord.cli -e done --filename benchy.gcode --elapsed 3661 --dry-run
```

Actually send to a channel (webhook from ENV or `-w`):

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python -m octoprint_discord.cli -e done --filename benchy.gcode --elapsed 3661
# with a snapshot and a mention:
python -m octoprint_discord.cli -e failed --snapshot ./snap.png --mention '@here'
```

Available event types (`-e`): `started`, `done`, `failed`, `paused`, `resumed`,
`progress`, `cancelled`, `connected`, `disconnected`.

## Development and tests

Unit and integration tests (HTTP mocked, no real network):

```bash
python -m pytest
```

Building the package (sdist + wheel):

```bash
python setup.py sdist bdist_wheel
# artifacts in dist/
```

## Notes

- **Webcam snapshot:** uses the snapshot URL from OctoPrint's webcam
  configuration (supports the webcam system introduced in OctoPrint 1.9).
- **API security:** the test endpoint is protected and admin-only; the webhook
  URL is stored as a sensitive setting and never exposed to non-admin clients.
- The plugin only talks to the Discord webhook you configure; if Discord is
  unreachable it fails gracefully without disrupting OctoPrint.

## AI-assisted development

This plugin was built with the help of **AI — Kiro (kiro-dev)**. In line with
the OctoPrint Plugin Repository guidelines, it is marked with the
`ai-developed` attribute. The author (maintainer) is responsible for
maintenance, bug fixes and compatibility with future OctoPrint versions.

## License

AGPLv3.
