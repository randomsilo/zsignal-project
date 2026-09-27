# PTT / GPIO relay crash — debugging notes (2026-09-17/18)

## Update 2026-09-18: pivoting to a Digirig Mobile interface

Rather than keep chasing the DIY relay's coil-transient issue, we ordered a
Digirig Mobile interface (USB audio codec + CAT + hardware PTT via RTS,
explicitly lists Baofeng support) plus its black K1 data cable for HTs
(3.5mm/2.5mm TRS, same connector family Baofeng uses). ETA ~2 days. This
should sidestep the whole crash class below since PTT is now keyed via an
isolated USB-serial RTS line instead of a bare GPIO pin driving a relay
coil sharing the Pi's own rail.

Code is ready ahead of the hardware: `zsignal/serial_ptt.py` adds a
`SerialPTT` class that holds a serial port open and drives `.rts` for PTT
(pyserial required: `pip3 install pyserial`). `cli.py`'s `send` command
gained `--ptt-serial <port>` (e.g. `/dev/ttyACM0`), which takes priority
over `--ptt-pin` when set. The old GPIO/relay path (`gpio.py`, `--ptt-pin`)
is untouched and still the default — switch to `--ptt-serial` once the
Digirig arrives and its device path is known (check `dmesg`/`ls /dev/tty*`
after plugging it in).

The relay/GPIO debugging notes below are kept for reference in case we
ever revisit the DIY relay approach, but are no longer the active plan.

## Update 2026-09-26: resolved by moving off the Orange Pi entirely

The Digirig crashed the Orange Pi too — same flash-then-crash signature as
the relay, even though the Digirig has none of the relay's failure modes
(no coil, no jumper, no bare GPIO pin). That means the Pi itself (most
likely its power supply/USB current budget) was the real constraint all
along, not the relay circuit specifically.

Rather than debug the Pi's power further, we ran zsignal from a Windows
PC instead, with the Digirig plugged into it directly:

- Needed the Silicon Labs CP210x VCP driver installed on Windows (showed
  as `ConfigManagerErrorCode 28` / "drivers not installed" until then);
  once installed, the Digirig enumerated as `COM3`.
- Added a Windows playback path to `audio.py` using the stdlib `winsound`
  module (no device selection — set the Digirig as the Windows default
  playback output in Settings > System > Sound instead of passing
  `--device`). Recording is not implemented on Windows yet.
- `serial_ptt.py`'s RTS PTT control needed no changes at all — `pyserial`
  is cross-platform, just point `--ptt-serial` at `COM3` instead of
  `/dev/ttyACM0`/`/dev/ttyUSB0`.
- Both a short message and a ~10s paragraph sent cleanly end-to-end from
  Windows: `python -m zsignal send "..." --ptt-serial COM3`. Confirmed
  received on a second listening radio.

Also worth remembering for next time: the Digirig's own USB-serial chip
is a CP210x, not the CDC-ACM chip we assumed — it shows up as
`/dev/ttyUSB0` on Linux (via the `cp210x` kernel driver), not
`/dev/ttyACM0`.

**Current state: zsignal works end-to-end from Windows via the Digirig.
The Orange Pi is no longer in the loop for transmitting.** If the Pi is
ever wanted back in the loop, its own power supply/USB headroom would
need to be investigated first, independent of anything relay- or
Digirig-specific.

## Symptom

Running `zsignal send` (or any GPIO write to pin 73 / PC9 that engages the
PTT relay) intermittently crashes the entire Orange Pi Zero 3 — not just the
Python process. The board drops off the network entirely and either
self-reboots within seconds, or hangs and needs a manual power-cycle. This
happened repeatedly across an extended debugging session on
`192.168.1.77` (`root`/key auth already set up).

Evidence it's a board-level crash, not a Python exception: `uptime` reads
"up 0 min" (or the box stops answering ping entirely) immediately after a
crash. Also: files written to the device shortly before a crash (a
redeployed `zsignal` package, test scripts in `/root`) are lost afterward —
consistent with an unclean shutdown, not a clean reboot.

## What's ruled out

Tested independently, each confirmed safe on its own:

- **The Python method used to drive the pin.** Both zsignal's `gpio.py`
  (export → set_direction → write, with polling and real exceptions) and a
  direct port of silent-latern-project's `ptt.py` style (setup once, then
  bare value writes) crash identically. This is not a code bug in either
  project — same underlying sysfs writes either way.
- **The USB sound card / ALSA audio path.** Crashed with it plugged in,
  crashed with it unplugged. Also separately fixed a real bug here: `aplay`
  had no `-D` device by default, so it depended on ALSA's `default` PCM,
  which isn't the USB dongle (see [cli.py](zsignal/cli.py) `AUDIO_DEVICE`,
  confirmed via `aplay -l` → `card 3: Device [USB Audio Device]`). That was
  worth fixing regardless, but it is **not** the cause of the board crash.
- **Duration of PTT hold.** Crashed at 10s hold, 30s hold, and even with the
  pin left HIGH indefinitely with no timeout at all (that case did **not**
  crash while held — see below).
- **The relay's own coil power draw in isolation.** With COM/NO
  (the radio-side contacts) physically disconnected, toggling the pin with
  the coil fully wired to VCC/GND/IN is completely safe, repeatably.
- **The physical connection to the radio, tested piecewise.** Relay
  contacts reconnected but cables unplugged from the radio: safe. Only the
  2.5mm PTT cable plugged into the radio (sound card present, radio on):
  safe. Sound card present with nothing plugged into the radio: safe.
- **The specific radio.** Swapped to a second, different handheld — still
  crashed under the full circuit, so it's not a fault specific to one radio.
- **Radio power state matters, but isn't the whole story.** Radio powered
  off + full circuit connected: always safe. Radio powered on: sometimes
  crashes, not 100% of the time.
- **Ground-loop fixes attempted so far didn't resolve it.** Added a direct
  wire from the Pi's ground to a metal tab on the radio chassis — crashed
  again afterward. (Caveat: that metal tab may not actually be tied to the
  radio's real signal/PTT ground — see Leading theory.)
- **The Pi's own power supply.** Swapped to a different (wired) power
  supply for the Pi itself — still crashed. Rules out "the Pi's supply just
  has poor transient headroom" as the main/sole cause.

## The one clean, repeatable signature

Leaving PTT **on** indefinitely (no auto-off) held rock solid — pin read
back as `1`, Pi stayed up the whole time we left it. The crash has shown up
at **both** the on-transition and the off-transition across different
attempts (not consistently one or the other), but never during a steady
hold. That points at a switching transient on the relay coil, not steady
current draw.

## Leading theory

The relay module is an opto-isolated **3V** board (Eagles-brand, "3V Relay
Module... Raspberry Pi 3.3V Application") that advertises built-in flyback
diode protection. But these modules have a jumper bridging `VCC` and
`JD-VCC` — `VCC` powers the opto-coupler LED (low current, isolated,
fine to share with the Pi), while `JD-VCC` powers the actual relay coil. If
that jumper is still installed, the coil's power is still electrically the
same rail as whatever's feeding the Pi, regardless of the opto-isolation on
the *signal* side. Even with a working onboard diode clamping the voltage
spike, the current from the collapsing coil field still has to go
somewhere — and with the jumper in, that's back into the shared VCC/Pi
rail.

Likely contributing factors on top of that:
- 3V-rated coils draw more current than an equivalent 5V coil for similar
  holding force, so the transient is bigger to begin with.
- Wire length/gauge between the Pi and the relay module adds source
  impedance, making the same transient show up as a bigger dip at the Pi.

## What's left to try (next session)

1. **Pull the JD-VCC/VCC jumper** on the relay module and feed `JD-VCC`
   from a genuinely separate ~3V source (e.g. a 2×AA battery holder — NOT
   9V, that would over-volt this specific 3V-rated coil). Leave `VCC` /
   `GND` / `IN` wired to the Pi as-is; that side is low-current and was
   never implicated. This is the most promising untried fix.
2. If that doesn't fully resolve it: re-check the metal-tab ground wire
   actually lands on the radio's real signal ground (the sleeve contact of
   the 2.5mm/3.5mm jack), not an isolated chassis part.
3. If still unresolved: multimeter continuity check (radio off, battery
   out) between the relay's COM/NO leads at the 2.5mm plug and the radio's
   battery positive terminal — rule out an actual short in the PTT wiring
   itself, separate from the coil-transient theory.
4. Verify the onboard flyback diode is actually present/correctly oriented
   on this specific board (cheap multi-packs occasionally have assembly
   defects) — visual inspection or continuity check across the coil
   terminals.

## Code-side status (already done, no further action needed here)

- [cli.py](zsignal/cli.py): `PTT_DELAY` (lead-in, 0.5s) and
  `PTT_TAIL_DELAY` (hold after audio ends, 0.5s) both implemented, PTT-off
  guaranteed via `try/finally` even if playback throws.
- `AUDIO_DEVICE` defaults to `plughw:CARD=Device,DEV=0`, confirmed against
  this device's actual `aplay -l` output — no more silent fallback to
  ALSA's `default`.
- A full ~20s paragraph message was successfully sent end-to-end and
  received on a second radio during this session, proving the
  code/protocol/audio path all work correctly when the hardware doesn't
  crash mid-transmission.

## Useful commands from this session

```bash
# Redeploy after any local edit
scp -r zsignal root@192.168.1.77:/shop/ezh/dev/zsignal/

# Bare pin toggle test (bypasses zsignal entirely, silent-latern-style)
ssh root@192.168.1.77 "cd /root && python3 -u ptt_hold_test_silentlatern.py"

# Real send with PTT
ssh root@192.168.1.77 "cd /shop/ezh/dev/zsignal && python3 -u -m zsignal send 'hi there' --ptt-pin 73"

# Check if the board actually rebooted vs. just lost network
ssh root@192.168.1.77 "uptime"
```
