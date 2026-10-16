"""octoprint_discord — powiadomienia OctoPrint na Discord przez webhook.

Pakiet jest podzielony tak, by logika Discorda była niezależna od OctoPrinta:
- ``discord_client``: niskopoziomowy klient webhooka (testowalny lokalnie).
- ``notifications``: szablony zdarzeń druku -> wiadomości Discord.
"""

from .discord_client import (
    DiscordError,
    DiscordMessage,
    DiscordWebhookClient,
    Embed,
    EmbedField,
)

__all__ = [
    "DiscordError",
    "DiscordMessage",
    "DiscordWebhookClient",
    "Embed",
    "EmbedField",
]
