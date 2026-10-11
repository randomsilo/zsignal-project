#!/bin/sh
# Mixer leveling, then hand off to the listener/relay service. Mirrors the old
# systemd unit's "ExecStartPre=-..." lines: best-effort, don't fail the
# container if the USB sound card isn't enumerated yet (the service itself
# retries via Docker's restart policy).
amixer -c Device sset Speaker 50% 2>/dev/null || true
amixer -c Device sset Mic 70% cap 2>/dev/null || true

# No command override (the normal `docker compose up` path): run the
# listener/relay service. An override (e.g. `docker compose run --rm
# zsignal-receiver python3 -m zsignal_receiver.gpio_test ...`) runs that
# instead, still after the mixer levels above have been applied.
if [ "$#" -eq 0 ]; then
    exec python3 -m zsignal_receiver.service
fi
exec "$@"
