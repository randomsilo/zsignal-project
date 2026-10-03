"""Bench test for the relay GPIO pins.

    python3 -m zsignal_receiver.gpio_test                   # pulse each relay once, 2s each
    python3 -m zsignal_receiver.gpio_test --pin PH7 -s 5    # one pin, 5 seconds
    python3 -m zsignal_receiver.gpio_test --cycles 3        # repeat the sequence
    python3 -m zsignal_receiver.gpio_test --together -s 5   # all relays on at once
    python3 -m zsignal_receiver.gpio_test --active-low      # for relay modules triggered by LOW
    python3 -m zsignal_receiver.gpio_test --off             # force all relays off and exit

Must run as root (sysfs GPIO).
"""

import argparse
import sys
import time

from .relays import RELAY_PINS, Relay


def main(argv=None):
    p = argparse.ArgumentParser(prog="gpio_test", description="pulse the receiver relay GPIO pins")
    p.add_argument("--pin", action="append",
                   help="pin name (e.g. PH7) or relay name (relay1); repeatable. Default: all relays")
    p.add_argument("-s", "--seconds", type=float, default=2.0, help="on-time per pulse (default 2)")
    p.add_argument("--gap", type=float, default=1.0, help="off-time between pulses (default 1)")
    p.add_argument("--cycles", type=int, default=1, help="repeat the whole sequence N times")
    p.add_argument("--together", action="store_true", help="switch all selected relays at the same time")
    p.add_argument("--active-low", action="store_true", help="relay switches on when the pin is LOW")
    p.add_argument("--off", action="store_true", help="just force the relays off and exit")
    args = p.parse_args(argv)

    names = args.pin or list(RELAY_PINS)
    relays = []
    for n in names:
        pin = RELAY_PINS.get(n.lower(), n)
        label = "%s (%s)" % (n, pin) if n.lower() in RELAY_PINS else str(pin).upper()
        relays.append(Relay(pin, active_low=args.active_low, label=label))

    for r in relays:
        r.setup()
        print("%-16s gpio%d ready, OFF (pin level %s)" % (
            r.label, r.pin, "HIGH" if r.active_low else "LOW"))

    if args.off:
        return 0

    try:
        for cycle in range(1, args.cycles + 1):
            if args.cycles > 1:
                print("-- cycle %d/%d" % (cycle, args.cycles))
            if args.together:
                print("ALL ON  for %.1fs: %s" % (args.seconds, ", ".join(r.label for r in relays)))
                sys.stdout.flush()
                for r in relays:
                    r.on()
                time.sleep(args.seconds)
                for r in relays:
                    r.off()
                print("ALL OFF")
                time.sleep(args.gap)
                continue
            for r in relays:
                print("%-16s ON  for %.1fs" % (r.label, args.seconds))
                sys.stdout.flush()
                r.pulse(args.seconds)
                print("%-16s OFF" % r.label)
                time.sleep(args.gap)
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        for r in relays:
            r.off()
    print("done -- all relays OFF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
