"""Append-only JSON Lines persistence for zsignal-web's sent/received logs.

Each log is one file in DATA_DIR (the zsignal-web-data Docker volume at
/data), one JSON object per line, so the logs survive container restarts
and rebuilds. Appending a line per message means a crash can lose at most
the line being written, and a damaged line is skipped on load.
"""

import json
import os

from settings_store import DATA_DIR

SENT_PATH = os.path.join(DATA_DIR, "sent.jsonl")
RECEIVED_PATH = os.path.join(DATA_DIR, "received.jsonl")

# Only the newest entries are loaded into memory (and served to the UI);
# the files themselves keep everything.
MAX_LOADED = 1000


def load(path):
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue  # partial line from an interrupted write
    return entries[-MAX_LOADED:]


def append(path, entry):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
