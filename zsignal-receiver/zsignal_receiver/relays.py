"""Relay outputs on Allwinner (Orange Pi) GPIO, by pin name (e.g. "PH7").

Builds on zsignal.gpio's sysfs helpers. Allwinner pin names map to sysfs
numbers as (bank - 'A') * 32 + index, so PH7 = 7*32 + 7 = 231.
"""

import os
import time

from zsignal import gpio

# Relay channels wired on the receiver frame.
RELAY_PINS = {
    "relay1": "PH7",
    "relay2": "PH5",
}


def pin_number(name):
    """Convert an Allwinner pin name like "PH7" (or a plain number) to a sysfs GPIO number."""
    name = str(name).strip().upper()
    if name.isdigit():
        return int(name)
    if len(name) < 3 or name[0] != "P" or not name[1].isalpha() or not name[2:].isdigit():
        raise ValueError("bad pin name %r (expected e.g. PH7)" % name)
    return (ord(name[1]) - ord("A")) * 32 + int(name[2:])


class Relay(object):
    """One relay channel. `active_low` is for relay modules that switch on when IN is pulled low."""

    def __init__(self, pin, active_low=False, label=None):
        self.pin_name = str(pin).upper()
        self.pin = pin_number(pin)
        self.active_low = active_low
        self.label = label or self.pin_name

    def setup(self):
        """Export the pin and make it an output that starts in the OFF state, without a glitch."""
        gpio.export(self.pin)
        # Writing "high"/"low" to direction sets output mode and the initial level atomically.
        initial = "high" if self.active_low else "low"
        with open("%s/gpio%d/direction" % (gpio.SYSFS_ROOT, self.pin), "w") as f:
            f.write(initial)

    def set(self, on):
        gpio.write(self.pin, bool(on) != self.active_low)

    def on(self):
        self.set(True)

    def off(self):
        self.set(False)

    def pulse(self, seconds):
        """Turn on for `seconds`, then off -- always off afterwards, even if interrupted."""
        self.on()
        try:
            time.sleep(seconds)
        finally:
            self.off()

    def read(self):
        with open("%s/gpio%d/value" % (gpio.SYSFS_ROOT, self.pin)) as f:
            return f.read().strip() == "1"

    def release(self):
        """Turn off and unexport the pin."""
        self.off()
        if os.path.exists("%s/gpio%d" % (gpio.SYSFS_ROOT, self.pin)):
            with open("%s/unexport" % gpio.SYSFS_ROOT, "w") as f:
                f.write(str(self.pin))
