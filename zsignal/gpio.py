"""Minimal sysfs GPIO control, used to key a PTT relay around a transmission."""

import os
import time

SYSFS_ROOT = "/sys/class/gpio"


def _pin_path(pin):
    return "%s/gpio%d" % (SYSFS_ROOT, pin)


def export(pin):
    path = _pin_path(pin)
    if os.path.exists(path):
        return
    with open("%s/export" % SYSFS_ROOT, "w") as f:
        f.write(str(pin))
    for _ in range(50):
        if os.path.exists(path):
            return
        time.sleep(0.01)
    raise RuntimeError("gpio%d did not appear under %s after export" % (pin, SYSFS_ROOT))


def set_direction(pin, direction):
    with open("%s/direction" % _pin_path(pin), "w") as f:
        f.write(direction)


def write(pin, value):
    with open("%s/value" % _pin_path(pin), "w") as f:
        f.write("1" if value else "0")


def set_pin(pin, value):
    """Export (if needed), set as output, and drive pin high/low."""
    export(pin)
    set_direction(pin, "out")
    write(pin, value)
