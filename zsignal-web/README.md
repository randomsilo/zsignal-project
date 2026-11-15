# zsignal-web

A small Flask UI over the `zsignal` CLI, with a dark, fixed-width "military
terminal" look (`static/css/terminal.css`, no CDN or web fonts, since this is
meant to run in the field without internet). Sent traffic is orange and
received traffic is green. The layout is kept tight for small screens like a
Chromebook.

The nav bar is **STATION** (the main screen), **ECHO MODE**, **SEND**,
**LISTEN** and **SETTINGS**. Send, Listen and Settings are kept for raw
send/receive and hardware configuration.

Expects `zsignal` to exist as a peer folder (`../zsignal`) — `app.py` adds that
to `sys.path` and imports it directly (`send_text()` from `zsignal/cli.py`,
`LiveListener` from `zsignal/live_listen.py`), rather than shelling out.

## Run (Docker)

From the repo root, after running `./setup.sh` once to confirm Docker is
installed:

```
docker compose up -d zsignal-web
```

Then open `http://127.0.0.1:5055/` (or `http://<machine-ip>:5055/` from
another computer on the LAN — the container binds `0.0.0.0` by default).
Edit the `devices:` list for the `zsignal-web` service in
`../docker-compose.yml` to match your box's sound card / Digirig serial port
(`aplay -l`, `ls /dev/ttyUSB*`) before starting it. `settings.json` persists
in the `zsignal-web-data` Docker volume across restarts.

## Settings

Set the audio device and PTT method (serial port for a Digirig-style USB
interface, or a GPIO pin) on the Settings screen before using Station, Send or
Listen.

## Station

General on-air messaging, in two side-by-side columns:

- **Transmit** (left): Sender, Receiver (may be `CQ` for all stations) and
  Message. Sender and Receiver are auto-uppercased and remembered between
  visits. The three fields go on the wire as one zsignal text payload,
  `SENDER>RECEIVER:MESSAGE`. **Transmit** stops the receiver, sends, then
  turns the receiver back on.
- **Log** (right): sent (`TX`, orange) and cleanly decoded received (`RX`,
  green) messages, newest on top. It's rebuilt from the server's logs, so it
  survives a page reload. **RX ON/OFF** toggles the receiver; **CLEAR** hides
  the current entries in this browser.

## Echo Mode

A link test. While **ECHO MODE** is on (amber), each clean received message
addressed to your Sender callsign or `CQ` is sent back to its sender, after a
2s pause, as `ME>THEM:ECHO: <message>`. A raw payload that isn't in station
format is echoed as `ECHO: <text>`. Turning it on also turns the receiver on.
To keep two stations in Echo Mode from bouncing forever, it never echoes your
own messages or anything that already starts with `ECHO: `. Corrupted or
truncated decodes are never echoed.

Echo Mode runs in the browser (`app.js`), so the page has to stay open. It
always starts off after a reload, so the station never transmits on its own
just because a tab was reopened.

## Platform notes

- **Send** works on Windows and Linux (Windows plays audio via `winsound`, no
  device selection there -- set the interface as the Windows default playback
  device in Sound settings instead of using the device field).
- **Listen** requires Linux (`arecord`) — zsignal's Windows audio path has no
  recording implementation yet, so the Listen screen will report an error if
  started from Windows.
- The Listen screen segments the live audio stream into distinct messages by
  detecting ~1 second of silence after a transmission, then decodes each
  segment independently (see `zsignal/live_listen.py`). Each decoded message
  renders as three stacked lines (text / high-nibble hex / low-nibble hex per
  byte column), in the style of an old mainframe hex-dump editor, newest on
  top.
