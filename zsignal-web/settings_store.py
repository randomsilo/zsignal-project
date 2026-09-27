"""Tiny JSON-backed settings persistence for zsignal-web."""

import json
import os

PATH = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULTS = {
    "device": "",
    "ptt_serial": "",
    "ptt_pin": None,
    "ptt_delay": 0.5,
    "ptt_tail_delay": 0.5,
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
