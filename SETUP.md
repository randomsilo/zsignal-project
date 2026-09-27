# Device Setup

Commands to install zsignal's dependencies and debug the Linux ALSA sound
configuration on a new device (currently a Xubuntu Chromebook; originally
written against an Orange Pi Zero, armv7l, Ubuntu 18.04.6 LTS, Python
3.6.9 — the steps are generic Linux/ALSA, not board-specific). Run the
numbered sections in order the first time you set up a box; skip to
whichever section you need on subsequent visits. See `SSH.md` first if
you're doing this over a remote session rather than at the keyboard.

## 1. System check (on the device)

Confirm architecture, OS, and Python version — zsignal's codec is pure
standard-library Python (no numpy/scipy needed), but you still want to know
what you're targeting:

```bash
uname -m
cat /etc/os-release
python3 --version
```

## 2. Install dependencies (on the device)

Only ALSA's command-line tools are required for the codec itself; zsignal
shells out to `aplay`/`arecord` rather than using a Python audio binding.

```bash
apt-get update
apt-get install -y alsa-utils
```

No `pip install` needed for the codec itself — it's stdlib-only. The one
exception: `--ptt-serial` for RTS-based PTT over a USB PTT/audio interface
like Digirig Mobile needs:

```bash
pip3 install pyserial
```

(Plain `--ptt-pin` GPIO control doesn't need it.)

## 3. Identify and configure the USB sound card (on the device)

Plug in the USB sound card (or PTT/audio interface, e.g. Digirig) — for a
loopback bench test, bridge speaker-out to mic-in with a cable — then find
its ALSA card/device numbers:

```bash
arecord -l
aplay -l
```

Note the `card N` value from the `USB Audio Device` (or whatever your card
identifies as) entries — you'll use it as `hw:N,0` / `plughw:N,0` below.

Check whether the card supports mono directly at the hardware level, or
needs ALSA's `plug` conversion layer:

```bash
aplay --dump-hw-params -D hw:N,0 /usr/share/sounds/alsa/Front_Center.wav 2>&1 | grep CHANNELS
```

If it reports `CHANNELS: 2` only (no mono), always use `plughw:N,0` instead
of `hw:N,0` for zsignal's playback/record device args — see Troubleshooting.

Check and set mixer levels (avoid clipping on the loopback cable — start
conservative, e.g. 50-ish%, and adjust from the CLI's decode diagnostics):

```bash
amixer -c N scontrols
amixer -c N sget 'Speaker'
amixer -c N sget 'Mic'
amixer -c N sset 'Speaker' 50%
amixer -c N sset 'Mic' 70%
```

## 4. Deploy the zsignal package (from the client)

```bash
scp -r zsignal <user>@<device-ip>:/path/to/zsignal/
```

Re-run this after any local edit to sync changes; it's a plain file copy,
no build step.

## 5. Validate (on the device)

Pure-software round trip first (no audio hardware involved):

```bash
cd /path/to/zsignal
python3 -m zsignal selftest
```

Then the real hardware loopback test (play out the speaker, record from the
mic through your bridge cable, decode):

```bash
python3 -m zsignal loopback "hello from <device>" \
  --play-device plughw:N,0 --rec-device plughw:N,0
```

A clean run prints `ROUND TRIP: OK` with no corrupted-bit or IMD warnings.

## Troubleshooting

- **`aplay`/`arecord` fail with `Channels count non available`** — the
  card's raw ALSA hardware device doesn't support mono directly (common on
  cheap USB audio dongles, which are stereo-only at the hw level). Use
  `plughw:N,0` instead of `hw:N,0`; the `plug` layer handles mono↔stereo and
  sample-rate conversion transparently.
- **`arecord: invalid duration argument '2.78'`** — `arecord -d` only
  accepts whole seconds; zsignal's own `audio.record`/`audio.record_async`
  already round up internally, but if you're calling `arecord` by hand for
  debugging, use an integer duration.
