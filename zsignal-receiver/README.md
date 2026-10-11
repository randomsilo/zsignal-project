# zsignal-receiver

Headless receiver that runs on an **Orange Pi Zero 3**. The goal: on boot, a
service listens on the sound card, and when a zsignal arrives it switches a
relay (GPIO pin) on for a set number of seconds.

We're building this up in small steps:

- [x] 1. Copy the project to the device
- [x] 2. Test the relay GPIO pins (`gpio_test`)
- [x] 3. Listener: decode zsignals from the sound card (reuses `zsignal.live_listen`)
- [x] 4. Map received messages to relay actions (`service.py`, `"<relay>:<seconds>"`)
- [x] 5. systemd service that starts at boot (`zsignal-receiver.service`)
- [ ] 6. Over-the-air test through a radio instead of the loopback cable

## Commands

The receiver acts on the decoded zsignal text `"<relay>:<seconds>"`:

| Text | Effect |
|---|---|
| `1:5` | relay 1 (PH7) on for 5 s |
| `2:0.5` | relay 2 (PH5) on for 0.5 s |
| `2:0` | relay 2 off now |

- A new command for a relay that's already on replaces its remaining time.
- Commands over `--max-seconds` (default 60) are ignored, so a bad message
  can't hold a relay on.
- The service ignores any frame that doesn't decode cleanly (no end chord,
  or corrupted bits).
- All relays turn off when the service stops.

Send a command from the Chromebook or the Pi itself:

```bash
python3 -m zsignal send "1:5" --no-ptt -D plughw:CARD=Device,DEV=0
```

## Hardware

| Item | Detail |
|---|---|
| Board | Orange Pi Zero 3 (Allwinner H618), Ubuntu 22.04, Python 3.10 |
| Address | `root@192.168.1.199` (passwordless SSH, see `../SSH.md`) |
| Relay 1 | **PH7** = sysfs GPIO **231** |
| Relay 2 | **PH5** = sysfs GPIO **229** |
| Test loads | Two relays in a 3D-printed frame. Each one switches its own circuit: a 9V battery, two 220 Ω resistors and the green leg of an RGB LED. The circuit is wired through the relay's COM and NO (normally open) contacts. |

Allwinner pin names convert to sysfs numbers as `(bank letter − 'A') × 32 +
index`. PH7 is bank H (7), so `7 × 32 + 7 = 231`. `relays.pin_number("PH7")`
does this conversion.

> The 9V LED circuits run only through the relay contacts, so they are
> electrically separate from the Pi. Only the relay modules' VCC, GND and IN
> wires connect to the Pi header. The old PTT notes (`../PTT_NOTES.md`)
> found that switching a relay coil alone was safe on this board. The
> crashes only happened once a radio was connected.

## Layout

```
zsignal-receiver/
  deploy.ps1                   copy zsignal/ + zsignal-receiver/ to the device, then docker compose build/up
  Dockerfile                   image: python3 + alsa-utils + pyserial + this package
  entrypoint.sh                sets mixer levels, then runs service.py (or an overridden command)
  loopback_test.sh             end-to-end test over a 3.5mm loopback cable
  zsignal_receiver/
    relays.py                  Relay class (pin-name -> sysfs, on/off/pulse, active-low option)
    gpio_test.py               bench test for the relay pins
    service.py                 listener: decode zsignals -> relay on for N seconds
```

The container needs `privileged: true` (see `../docker-compose.yml`) --
`relays.py`/`gpio.py` write directly to `/sys/class/gpio`, which otherwise
isn't reliably writable from inside a container.

On the device everything lives in `/opt/zsignal`:

```
/opt/zsignal/zsignal/            the codec package (shared with the sender)
/opt/zsignal/zsignal-receiver/   this directory
```

Requires Docker on the device first -- run `./setup.sh` (repo root) there,
or `--fix` to have it install things for you.

## 1. Deploy (from Windows)

From the `zsignal-project` folder:

```powershell
.\zsignal-receiver\deploy.ps1
```

Run it again after every local edit. It copies the files, then runs
`docker compose build zsignal-receiver && docker compose up -d
zsignal-receiver` on the device. Pass `-SkipUp` to only copy files without
rebuilding/restarting.

## 2. Test the GPIO pins (on the device)

```bash
ssh root@192.168.1.199
cd /opt/zsignal

docker compose run --rm zsignal-receiver python3 -m zsignal_receiver.gpio_test                 # relay1 then relay2, 2 s each
docker compose run --rm zsignal-receiver python3 -m zsignal_receiver.gpio_test --pin PH7 -s 5  # just one pin, 5 s
docker compose run --rm zsignal-receiver python3 -m zsignal_receiver.gpio_test --cycles 5      # repeat to check reliability
docker compose run --rm zsignal-receiver python3 -m zsignal_receiver.gpio_test --together -s 10  # both relays on at once
docker compose run --rm zsignal-receiver python3 -m zsignal_receiver.gpio_test --off           # force everything off
```

Or run it from Windows in one line:

```powershell
ssh root@192.168.1.199 "cd /opt/zsignal && docker compose run --rm zsignal-receiver python3 -m zsignal_receiver.gpio_test"
```

**What you should see:** each relay clicks and its green LED lights for
the on-time, then goes dark.

**If it's backwards** (LEDs on while the test says OFF, and off while it
says ON), the relay module is *active-low*. Re-run with `--active-low`. The
service will need that setting too.

**Verified 2026-10-03:** PH7 and PH5 each switch their relay and LED circuit,
one at a time and both together (10 s). The relay modules are **active-high**
(pin HIGH = relay on), so `--active-low` isn't needed. The board stayed up
through every test, so the coil current didn't cause the crashes described in
the old PTT notes. Each module's red light is its own indicator, not the
test LED.

**Quick manual GPIO check without Python:**

```bash
echo 231 > /sys/class/gpio/export          # PH7 (skip if already exported)
echo out > /sys/class/gpio/gpio231/direction
echo 1 > /sys/class/gpio/gpio231/value     # on
echo 0 > /sys/class/gpio/gpio231/value     # off
```

## 3. End-to-end loopback test (on the device)

Connect the USB sound card's speaker-out to its mic-in with a 3.5mm cable.
The card is a GeneralPlus `USB Audio Device`, ALSA name
`plughw:CARD=Device,DEV=0`. The service sets the mixer levels every time it
starts (Speaker 50%, Mic 70%). To set them by hand:

```bash
amixer -c Device sset Speaker 50%
amixer -c Device sset Mic 70% cap
```

Then run the test. It starts its own copy of the listener (stop the running
`zsignal-receiver` container first so they don't fight over the sound card),
sends `1:5` and then `2:5`, and prints the log:

```bash
cd /opt/zsignal
docker compose stop zsignal-receiver
docker compose run --rm --entrypoint bash zsignal-receiver loopback_test.sh            # default 1:5 then 2:5
docker compose run --rm --entrypoint bash zsignal-receiver loopback_test.sh "2:3" "1:1"
docker compose up -d zsignal-receiver
```

**Verified 2026-10-03:** both commands were received, and each relay turned
on for 5 s and then off. (Verified pre-Docker, over the native systemd
service that this container replaced -- re-verify after moving to Docker.)

## 4. Boot container (on the device)

`docker compose up -d zsignal-receiver` (what `deploy.ps1` runs for you)
builds the image if needed and starts the container with `restart:
unless-stopped` -- it comes back on its own after a reboot or a crash, same
as the old systemd unit did, with no separate install/enable step.

Day-to-day commands:

```bash
cd /opt/zsignal
docker compose ps zsignal-receiver                 # running?
docker compose logs -f zsignal-receiver             # live log: received commands, relay ON/OFF
docker compose stop zsignal-receiver                # stop (all relays turn OFF)
docker compose restart zsignal-receiver             # after a code-only change (run deploy.ps1 first to sync files)
```

The service waits for ALSA to come up, sets the mixer levels, and restarts
5 s after any failure (for example if the USB sound card isn't ready yet).
To log the audio noise floor and peak level every 5 s, add `--debug` by
overriding the compose service's `command:` (or editing `entrypoint.sh`).
This is useful when setting the levels for a radio.

**Verified 2026-10-03:** after a reboot, the service started on its own and
acted on `1:3`, `2:3` and `1:2`.

### Gotcha: background noise changes after the first playback

On this sound card, the background level at the input is about 0.001 RMS
after boot. Once anything has been played out the speaker jack, it rises to
about 0.008 and stays there. The listener first calibrated its noise floor
at the low level, so the higher hiss looked like an endless transmission
and nothing was ever decoded. A restart appeared to fix it because the hiss
was already present during calibration. `zsignal/live_listen.py` now handles
this in three ways:

- A transmission ends once the level drops below 25% of that transmission's
  own peak (`END_RATIO`).
- After each transmission, the noise floor is re-measured from the quiet
  that follows.
- Any segment longer than 30 s is decoded anyway, and the noise floor is
  recalibrated (`MAX_SEGMENT_SECONDS`).

Expect the same kind of shift over a radio, where squelch opening and
closing changes the background level.
