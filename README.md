# OctoPrint-DiscordNotifier

Plugin OctoPrint, który wysyła powiadomienia o druku bezpośrednio na kanał
Discord przez **webhook** — bez pośredniczącego skryptu/przelotki.

> Interfejs pluginu (panel ustawień, powiadomienia na Discordzie) jest
> w języku **angielskim**. Niniejszy README jest po polsku jako dokumentacja
> deweloperska.

## Funkcje

- Konfiguracja **URL webhooka** Discord w panelu ustawień.
- **Checkboxy** wyboru zdarzeń, pod które plugin ma reagować:
  - Print started / Print done / Print failed
  - Paused / Resumed / Cancelled
  - Printer connected / Printer disconnected
- **Snapshot z kamery** — powiadomienia (oraz test) mogą dołączać obraz
  z kamery skonfigurowanej w OctoPrint. Obraz jest wysyłany jako załącznik
  (`multipart`), bez potrzeby hostowania go na zewnątrz.
- **Limit powiadomień (throttle)** — konfigurowalny odstęp (domyślnie 10 s),
  który zapobiega serii identycznych powiadomień (np. przy migotaniu portu
  szeregowego drukarki). `0` wyłącza limit.
- Przycisk **„Send test"** — wysyła przykładowe powiadomienie wraz z obrazem
  z kamery (jeśli skonfigurowana). Test nie podlega throttle.
- Ładne embedy z kolorem per typ zdarzenia, paskiem postępu, czasami oraz
  portem/baudrate (dla zdarzenia połączenia).

## Architektura

Projekt jest celowo podzielony na dwie części, aby logika Discorda była
niezależna od OctoPrinta i w pełni testowalna:

- **`octoprint_discord/`** — czysta biblioteka (bez zależności od OctoPrinta):
  - `discord_client.py` — klient webhooka (JSON + multipart, retry na 429,
    akceptacja odpowiedzi 2xx, limity i obcinanie pól).
  - `notifications.py` — budowanie wiadomości/embedów dla typów zdarzeń.
  - `snapshot.py` — pobieranie obrazu ze snapshot URL kamery.
  - `events.py` — mapowanie nazw zdarzeń OctoPrint na typy wewnętrzne,
    domyślne wartości checkboxów i etykiety.
  - `throttle.py` — deduplikacja/throttle powiadomień per typ zdarzenia.
  - `cli.py` — lokalne CLI do testów bez OctoPrinta.
- **`octoprint_discord_notifier/`** — właściwy plugin OctoPrint:
  - `__init__.py` — mixiny (Settings, EventHandler, SimpleApi, Template,
    Asset), mapowanie zdarzeń, API przycisku testu, pobieranie snapshotu.
  - `templates/discord_notifier_settings.jinja2` — panel ustawień.
  - `static/js/discord_notifier.js` — view model (przycisk testu).

## Wymagania

- OctoPrint (testowane na 1.11.x, Python 3.12; deklarowana zgodność `>=3.7,<4`).
- Zależność runtime: `requests`.

## Instalacja

Najprościej przez **Plugin Manager** w OctoPrincie:

1. *Settings → Plugin Manager → Get More… → „… from an uploaded archive"*.
2. Wskaż plik `dist/octoprint_discordnotifier-<wersja>.tar.gz`.
3. Zainstaluj i zrestartuj OctoPrint.

Alternatywnie z linii poleceń, w aktywnym venv OctoPrinta:

```bash
pip install dist/octoprint_discordnotifier-<wersja>.tar.gz
```

> Uwaga: `setup.py` celowo **nie** zależy od `octoprint_setuptools`, dzięki
> czemu build działa też w izolowanym środowisku pip (jak w Plugin Managerze).
> OctoPrint **nie** jest wpisany w `install_requires`, aby pip nie próbował go
> przebudowywać.

## Konfiguracja

1. W Discordzie: *ustawienia kanału → Integracje → Webhooki → Kopiuj URL webhooka*.
2. W OctoPrincie: *Settings → Discord Notifier* → wklej URL w polu **Webhook URL**.
3. Zaznacz zdarzenia (checkboxy), ustaw opcjonalnie **username** i **limit
   powiadomień**, zapisz.
4. (Opcjonalnie) skonfiguruj snapshot URL kamery w *Settings → Webcam &
   Timelapse*, aby test i powiadomienia dołączały obraz; zaznacz
   **„Attach webcam image"**.
5. Kliknij **Send test**, aby zweryfikować konfigurację.

### Ustawienia

| Ustawienie | Opis | Domyślnie |
|---|---|---|
| `webhook_url` | URL webhooka Discord | (puste) |
| `username` | Nazwa autora wiadomości na Discordzie | `OctoPrint` |
| `send_snapshot` | Dołączaj obraz z kamery do powiadomień | `true` |
| `throttle_seconds` | Min. odstęp między powiadomieniami tego samego typu; `0` = wyłączony | `10` |
| `event_PrintStarted` | Powiadomienie o rozpoczęciu druku | `true` |
| `event_PrintDone` | Powiadomienie o zakończeniu druku | `true` |
| `event_PrintFailed` | Powiadomienie o błędzie druku | `true` |
| `event_PrintPaused` | Powiadomienie o wstrzymaniu | `false` |
| `event_PrintResumed` | Powiadomienie o wznowieniu | `false` |
| `event_PrintCancelled` | Powiadomienie o anulowaniu | `true` |
| `event_Connected` | Powiadomienie o podłączeniu drukarki | `false` |
| `event_Disconnected` | Powiadomienie o odłączeniu drukarki | `false` |

## Lokalne testy bez OctoPrinta (CLI)

Biblioteka `octoprint_discord` działa samodzielnie. Podgląd payloadu bez wysyłki:

```bash
python -m octoprint_discord.cli -e done --filename benchy.gcode --elapsed 3661 --dry-run
```

Realna wysyłka na kanał (webhook z ENV lub `-w`):

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python -m octoprint_discord.cli -e done --filename benchy.gcode --elapsed 3661
# ze snapshotem i wzmianką:
python -m octoprint_discord.cli -e failed --snapshot ./snap.png --mention '@here'
```

Dostępne typy zdarzeń (`-e`): `started`, `done`, `failed`, `paused`, `resumed`,
`progress`, `cancelled`, `connected`, `disconnected`.

## Rozwój i testy

Testy jednostkowe i integracyjne (HTTP mockowany, bez realnej sieci):

```bash
python -m pytest
```

Budowanie paczki (sdist + wheel):

```bash
python setup.py sdist bdist_wheel
# artefakty w dist/
```

## Uwagi techniczne

- **Odpowiedzi Discorda:** webhook zwraca `204 No Content` dla zwykłego POST
  oraz `200 OK` (z obiektem wiadomości) przy wysyłce z załącznikiem. Klient
  traktuje cały zakres `2xx` jako sukces.
- **Snapshot z kamery:** plugin preferuje system kamer wprowadzony w
  OctoPrint 1.9 (`octoprint.webcams.get_snapshot_webcam`), z fallbackiem na
  starszy odczyt ustawień dla wcześniejszych wersji.
- **Bezpieczeństwo API:** endpoint testu jest chroniony i tylko dla admina
  (`is_api_protected`, `is_api_adminonly`); webhook URL jest oznaczony jako
  ustawienie wrażliwe.

## Status rejestracji w repozytorium pluginów

Plugin **nie jest** zarejestrowany w oficjalnym OctoPrint Plugin Repository.
Przed ewentualną rejestracją należy m.in.:

- uzupełnić realne `user`/`repo`/`author` w `setup.py` i (opcjonalnie) włączyć
  hook aktualizacji (`octoprint.plugin.softwareupdate.check_config`),
- utworzyć plik rejestracyjny `_plugins/discord_notifier.md` z atrybutem
  `ai-developed` (plugin powstał z pomocą AI) oraz screenshotami.

## Licencja

AGPLv3.
