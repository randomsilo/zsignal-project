"""Tiny JSON-backed settings persistence for zsignal-web."""

import json
import os

DATA_DIR = os.environ.get("ZSIGNAL_WEB_DATA_DIR", os.path.dirname(__file__))
PATH = os.path.join(DATA_DIR, "settings.json")

# Keys from removed features, dropped from settings.json on the next save.
OBSOLETE = ("volleyball_station",)

DEFAULTS = {
    # Match the CLI defaults (zsignal/cli.py AUDIO_DEVICE): the Digirig's USB
    # sound card, and its serial port as docker-compose.yml maps it. An empty
    # device makes aplay use ALSA "default", which is card 0 -- on the
    # Chromebook that has no playback PCM, so sends fail.
    "device": "plughw:CARD=Device,DEV=0",
    "ptt_serial": "/dev/ttyUSB0",
    "ptt_pin": None,
    "ptt_delay": 0.5,
    "ptt_tail_delay": 0.5,
    "station_sender": "",
    "station_receiver": "",
}


def load():
    if os.path.exists(PATH):
        with open(PATH) as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        for k in OBSOLETE:
            merged.pop(k, None)
        return merged
    return dict(DEFAULTS)


def save(settings):
    with open(PATH, "w") as f:
        json.dump(settings, f, indent=2)
