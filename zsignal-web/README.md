# zsignal-web

A small Flask UI over the `zsignal` CLI, styled with a locally-vendored copy
of Bulma CSS (no CDN dependency, since this is meant to run in the field
without internet). **Station COMS** and **Volleyball** are the primary
screens; **Send**, **Listen**, and **Settings** are kept for raw
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
interface, or a GPIO pin) on the Settings tab before using Send/Listen/Station
COMS/Volleyball.

## Station COMS

General on-air messaging. Sender/Receiver (receiver may be `CQ` for all
stations) are free text, auto-uppercased, and remembered between visits. The
three fields are combined into one zsignal text payload on the wire as
`SENDER>RECEIVER:MESSAGE` and parsed back out of received messages for the
log table. **Transmit** stops any active listening, sends, then restarts
listening automatically.

## Volleyball

Bounces a fixed message back and forth with another station to exercise a
radio link: **Start** sends `"{station}: serves."`; whichever station hears
that replies (after a 2s pause) with `"{me}:{server}: bump. set. spike."`;
from then on, either side hearing a `bump. set. spike.` message just echoes
it back unchanged after another 2s pause, so the same message volleys back
and forth indefinitely until **Stop** (which sends `"{station}: Good
Game."` and stops listening). This logic runs entirely in the browser
(`app.js`), so the tab needs to stay open for the rally to continue.

## Platform notes

- **Send** works on Windows and Linux (Windows plays audio via `winsound`, no
  device selection there -- set the interface as the Windows default playback
  device in Sound settings instead of using the device field).
- **Listen** requires Linux (`arecord`) — zsignal's Windows audio path has no
  recording implementation yet, so the Listen tab will report an error if
  started from Windows.
- The Listen tab segments the live audio stream into distinct messages by
  detecting ~1 second of silence after a transmission, then decodes each
  segment independently (see `zsignal/live_listen.py`). Each decoded message
  renders as three stacked lines (text / high-nibble hex / low-nibble hex per
  byte column), in the style of an old mainframe hex-dump editor.
