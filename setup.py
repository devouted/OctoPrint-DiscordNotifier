# coding=utf-8
"""Setup dla OctoPrint-DiscordNotifier.

UWAGA dot. budowania:
Nowoczesny pip (jak ten używany przez OctoPrint Plugin Manager) buduje paczkę
w IZOLOWANYM środowisku build. W takiej izolacji nie jest widoczny ani
OctoPrint, ani ``octoprint_setuptools``. Dlatego ten plik NIE importuje
``octoprint_setuptools`` — zamiast tego definiuje parametry pluginu wprost
przez zwykły setuptools. Efekt jest identyczny jak przy
``octoprint_setuptools.create_plugin_setup_parameters`` (ten sam entry point,
package_data, zależności), ale build działa niezależnie od środowiska.
"""

from setuptools import setup

# --- Metadane pluginu ---
plugin_identifier = "discord_notifier"
plugin_package = "octoprint_discord_notifier"
plugin_name = "OctoPrint-DiscordNotifier"
plugin_version = "0.1.5"
plugin_description = "Print notifications to Discord via webhook, with webcam snapshot."
plugin_author = "Marcin Sadowski"
plugin_author_email = "msdevouted@gmail.com"
plugin_url = "https://github.com/devouted/OctoPrint-DiscordNotifier"
plugin_license = "AGPLv3"

setup(
    name=plugin_name,
    version=plugin_version,
    description=plugin_description,
    author=plugin_author,
    author_email=plugin_author_email,
    url=plugin_url,
    license=plugin_license,
    # Sam plugin + czysta biblioteka logiki Discorda.
    packages=[plugin_package, "octoprint_discord"],
    # Zasoby frontendowe pluginu muszą trafić do paczki.
    package_data={
        plugin_package: [
            "static/js/*.js",
            "templates/*.jinja2",
        ]
    },
    include_package_data=True,
    zip_safe=False,
    python_requires=">=3.7,<4",
    # NIE podajemy tu OctoPrinta: jest już zainstalowany w środowisku docelowym,
    # a wpisanie go do install_requires potrafi skłonić pip do prób ponownego
    # pobrania/budowania całego OctoPrinta (długie zawieszenie instalacji).
    install_requires=[
        "requests>=2.25",
    ],
    # Kluczowe: entry point, po którym OctoPrint wykrywa plugin.
    entry_points={
        "octoprint.plugin": [
            "{} = {}".format(plugin_identifier, plugin_package),
        ]
    },
)
