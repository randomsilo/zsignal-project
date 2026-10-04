# zsignal-web

A small Flask UI over the `zsignal` CLI: Send, Listen, and Settings tabs, styled
with a locally-vendored copy of Bulma CSS (no CDN dependency, since this is meant
to run in the field without internet).

Expects `zsignal` to exist as a peer folder (`../zsignal`) — `app.py` adds that
to `sys.path` and imports it directly (`send_text()` from `zsignal/cli.py`,
`LiveListener` from `zsignal/live_listen.py`), rather than shelling out.

## Run

```
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5055/`.

By default it only listens on the machine itself. To open it from another
computer on the LAN, start it like this:

```
ZSIGNAL_WEB_HOST=0.0.0.0 python3 app.py
```

Then browse to `http://<machine-ip>:5055/` (for example
`http://192.168.1.44:5055/`). Flask's debug mode is switched off
automatically in this mode, because its debugger would let anyone on the
network run code on the machine. If it still doesn't load, check the
firewall: `sudo ufw allow 5055/tcp`. `ZSIGNAL_WEB_PORT` changes the port.

## Settings

Set the audio device and PTT method (serial port for a Digirig-style USB
interface, or a GPIO pin) on the Settings tab before using Send/Listen. Settings
persist to `settings.json` next to `app.py`.

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
