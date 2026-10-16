"""CLI do lokalnego testowania powiadomień Discord — bez OctoPrinta.

Przykłady:
    # Prosty test — każdy typ zdarzenia wysyła pełny przykład
    python -m octoprint_discord.cli --webhook "https://discord.com/api/webhooks/..." --event done

    # Z własnymi danymi
    python -m octoprint_discord.cli -w URL -e progress \\
        --filename benchy.gcode --progress 42.5 --elapsed 1800 --remaining 2400

    # Z dołączonym snapshotem (plik PNG/JPG z kamery)
    python -m octoprint_discord.cli -w URL -e done --snapshot ./snap.png

    # Dry-run: wypisz payload JSON zamiast wysyłać
    python -m octoprint_discord.cli -w URL -e started --dry-run

Webhook URL można też podać przez zmienną środowiskową DISCORD_WEBHOOK_URL.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Optional

from .discord_client import DiscordError, DiscordWebhookClient
from .notifications import PrintEvent, PrintStatus, build_message


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="octoprint_discord.cli",
        description="Test sending of OctoPrint notifications to Discord.",
    )
    p.add_argument(
        "-w", "--webhook",
        default=os.environ.get("DISCORD_WEBHOOK_URL"),
        help="Discord webhook URL (or DISCORD_WEBHOOK_URL env var).",
    )
    p.add_argument(
        "-e", "--event",
        required=True,
        choices=[e.value for e in PrintEvent],
        help="Event type to send.",
    )
    p.add_argument("--filename", default="example.gcode", help="Print file name.")
    p.add_argument("--progress", type=float, default=None, help="Progress 0-100.")
    p.add_argument("--elapsed", type=float, default=None, help="Elapsed print time (seconds).")
    p.add_argument("--remaining", type=float, default=None, help="Remaining time (seconds).")
    p.add_argument("--printer-name", default="OctoPrint", help="Printer name.")
    p.add_argument("--error", default="Thermal runaway", help="Error text (for event=failed).")
    p.add_argument("--mention", default=None, help="E.g. '<@123>' or '@here'.")
    p.add_argument("--username", default=None, help="Override the webhook username.")
    p.add_argument("--snapshot", default=None, help="Path to an image to attach.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send — only print the JSON payload.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG logs.")
    return p


def main(argv: Optional[list] = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    event = PrintEvent(args.event)

    # Dla zdarzeń bez naturalnego postępu nie wymuszamy wartości,
    # ale dla progress damy wartość domyślną, by przykład był sensowny.
    progress = args.progress
    if event == PrintEvent.PROGRESS and progress is None:
        progress = 50.0
    if event == PrintEvent.DONE and progress is None:
        progress = 100.0

    status = PrintStatus(
        filename=args.filename,
        progress=progress,
        elapsed_seconds=args.elapsed,
        remaining_seconds=args.remaining,
        printer_name=args.printer_name,
        error=args.error if event == PrintEvent.FAILED else None,
    )

    snapshot_bytes = None
    snapshot_name = "snapshot.png"
    if args.snapshot:
        try:
            with open(args.snapshot, "rb") as fh:
                snapshot_bytes = fh.read()
            snapshot_name = os.path.basename(args.snapshot)
        except OSError as exc:
            print(f"Cannot read snapshot: {exc}", file=sys.stderr)
            return 2

    message = build_message(
        event,
        status,
        username=args.username,
        mention=args.mention,
        has_snapshot=snapshot_bytes is not None,
    )

    if args.dry_run:
        payload = message.to_payload()
        if snapshot_bytes is not None and payload.get("embeds"):
            payload["embeds"][0]["image"] = {"url": f"attachment://{snapshot_name}"}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if snapshot_bytes is not None:
            print(f"\n[dry-run] + attachment: {snapshot_name} ({len(snapshot_bytes)} B)",
                  file=sys.stderr)
        return 0

    if not args.webhook:
        print(
            "No webhook URL. Provide --webhook or set DISCORD_WEBHOOK_URL.",
            file=sys.stderr,
        )
        return 2

    client = DiscordWebhookClient(args.webhook)
    try:
        client.send(message, snapshot=snapshot_bytes, snapshot_filename=snapshot_name)
    except DiscordError as exc:
        print(f"Sending failed: {exc}", file=sys.stderr)
        return 1

    print(f"Sent '{event.value}' notification to Discord.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
