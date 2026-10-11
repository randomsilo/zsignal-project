"""Tiny JSON-backed settings persistence for zsignal-web."""

import json
import os

DATA_DIR = os.environ.get("ZSIGNAL_WEB_DATA_DIR", os.path.dirname(__file__))
PATH = os.path.join(DATA_DIR, "settings.json")

DEFAULTS = {
    "device": "",
    "ptt_serial": "",
    "ptt_pin": None,
    "ptt_delay": 0.5,
    "ptt_tail_delay": 0.5,
    "station_sender": "",
    "station_receiver": "",
    "volleyball_station": "",
}


def load():
    if os.path.exists(PATH):
        with open(PATH) as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    return dict(DEFAULTS)


def save(settings):
    with open(PATH, "w") as f:
        json.dump(settings, f, indent=2)
