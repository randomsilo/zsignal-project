"""Receiver service: listen on the sound card for zsignal commands and drive the relays.

Command format (the decoded zsignal text):  "<relay>:<seconds>"
    "1:5"   -> relay1 on for 5 seconds
    "2:0.5" -> relay2 on for half a second
    "2:0"   -> relay2 off now

A new command for a relay that is already on replaces its remaining time.
Only frames that decode cleanly (end chord found, no corrupted bits) are acted on.

    PYTHONPATH=/opt/zsignal python3 -m zsignal_receiver.service
"""

import argparse
import queue
import re
import signal
import sys
import threading
import time

from zsignal.live_listen import LiveListener

from .relays import RELAY_PINS, Relay

AUDIO_DEVICE = "plughw:CARD=Device,DEV=0"
MAX_SECONDS = 60.0  # cap on any single on-time, so a bad command can't latch a relay on
COMMAND_RE = re.compile(r"^\s*(\d+)\s*:\s*(\d+(?:\.\d+)?)\s*$")


def log(msg):
    print("%s %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg))
    sys.stdout.flush()


def parse_command(text, max_seconds=MAX_SECONDS):
    """Parse "N:S" into (relay_name, seconds), or raise ValueError."""
    m = COMMAND_RE.match(text)
    if not m:
        raise ValueError("not a relay command: %r" % text)
    name = "relay%s" % m.group(1)
    if name not in RELAY_PINS:
        raise ValueError("unknown relay %s (have: %s)" % (m.group(1), ", ".join(sorted(RELAY_PINS))))
    seconds = float(m.group(2))
    if seconds > max_seconds:
        raise ValueError("%.1fs exceeds max %.1fs" % (seconds, max_seconds))
    return name, seconds


class RelayTimers(object):
    """Turns relays on with an off-deadline; a background thread turns them off when due."""

    def __init__(self, relays):
        self.relays = relays
        self.deadlines = {}
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def activate(self, name, seconds):
        with self.lock:
            if seconds <= 0:
                self.deadlines.pop(name, None)
                self.relays[name].off()
                log("%s OFF (command)" % name)
                return
            self.deadlines[name] = time.monotonic() + seconds
            self.relays[name].on()
        log("%s ON for %.1fs" % (name, seconds))

    def _run(self):
        while not self._stop.wait(0.05):
            now = time.monotonic()
            with self.lock:
                for name, due in list(self.deadlines.items()):
                    if now >= due:
                        del self.deadlines[name]
                        self.relays[name].off()
                        log("%s OFF" % name)

    def stop(self):
        self._stop.set()
        with self.lock:
            self.deadlines.clear()
            for r in self.relays.values():
                r.off()


def main(argv=None):
    p = argparse.ArgumentParser(prog="zsignal-receiver", description=__doc__.splitlines()[0])
    p.add_argument("-D", "--device", default=AUDIO_DEVICE, help="ALSA capture device (default: %s)" % AUDIO_DEVICE)
    p.add_argument("--max-seconds", type=float, default=MAX_SECONDS,
                   help="reject commands longer than this (default: %.0f)" % MAX_SECONDS)
    p.add_argument("--active-low", action="store_true", help="relay modules switch on when the pin is LOW")
    p.add_argument("--debug", action="store_true", help="log noise floor and peak audio level every 5s")
    args = p.parse_args(argv)

    relays = {}
    for name, pin in sorted(RELAY_PINS.items()):
        r = Relay(pin, active_low=args.active_low, label=name)
        r.setup()
        relays[name] = r
        log("%s on %s (gpio%d) ready, OFF" % (name, pin, r.pin))

    timers = RelayTimers(relays)
    timers.start()

    stopping = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stopping.set())

    listener = LiveListener(device=args.device)
    listener.start()
    log("listening on %s" % args.device)

    next_debug = time.monotonic() + 5
    try:
        while not stopping.is_set():
            if args.debug and time.monotonic() >= next_debug:
                next_debug += 5
                nf = listener.noise_floor
                log("debug: noise floor %s, peak %.5f" % ("calibrating" if nf is None else "%.5f" % nf,
                                                          listener.peak_level))
                listener.peak_level = 0.0
            try:
                ev = listener.events.get(timeout=0.5)
            except queue.Empty:
                if not listener._thread.is_alive():
                    log("audio capture stopped unexpectedly -- exiting")
                    return 1
                continue
            if not ev["ok"]:
                log("decode failed: %s" % ev["error"])
                continue
            res = ev["result"]
            text = res["text"]
            if not res["found_end"] or res["corrupted"]:
                log("ignored %r (end found=%s, corrupted bits=%s)" % (text, res["found_end"], res["corrupted"]))
                continue
            log("received %r" % text)
            try:
                name, seconds = parse_command(text, args.max_seconds)
            except ValueError as e:
                log("ignored: %s" % e)
                continue
            timers.activate(name, seconds)
    finally:
        listener.stop()
        timers.stop()
        log("stopped -- all relays OFF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
