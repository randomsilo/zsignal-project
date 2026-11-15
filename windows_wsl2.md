# Windows + WSL2 Setup

How to run zsignal on a Windows PC under WSL2 (Ubuntu) with a Digirig
Mobile wired to a radio. Everything after the USB passthrough step is the same
as on any Linux box, so this covers only what's different on WSL2 and
otherwise points at `SETUP.md`.

Tested on Windows 11, Ubuntu 24.04 under WSL2 (kernel
`6.18.33.2-microsoft-standard-WSL2`), usbipd-win 5.3.0, Digirig Mobile
(CP2102N serial + C-Media USB audio). The stock WSL2 kernel has both the
`cp210x` and `snd-usb-audio` drivers, so you don't need a custom kernel.

## How it fits together

WSL2 can't see USB devices on its own. Windows owns the Digirig until
[usbipd-win](https://github.com/dorssel/usbipd-win) forwards it into the WSL2
VM over USB/IP. The Digirig shows up to Windows as **two separate USB
devices**, and you have to forward both:

| Windows device | VID:PID | In WSL2 | Used for |
|---|---|---|---|
| Silicon Labs CP210x USB to UART Bridge (COMn) | `10c4:ea60` | `/dev/ttyUSB0` | PTT (RTS line) |
| USB Audio Device | `0d8c:0012` | ALSA card `Device` | TX/RX audio |

While a device is attached to WSL, Windows can't use it, and it disappears
from Sound settings and Device Manager's COM ports.

## 1. Install usbipd-win (Windows, once)

In PowerShell:

```powershell
winget install --interactive --exact dorssel.usbipd-win
```

Then **close and reopen PowerShell** so `usbipd` is on PATH. If it still
isn't, call it by full path: `& 'C:\Program Files\usbipd-win\usbipd.exe'`.

> Run `usbipd` from **Windows PowerShell**, not the WSL terminal. Ubuntu has
> its own unrelated `usbipd` (from `linux-tools`), and running it inside WSL
> gives `WARNING: usbipd not found for kernel ...-microsoft-standard-WSL2`.
> Ignore that and don't install the packages it suggests.

## 2. Bind and attach the Digirig (Windows)

Find the bus IDs:

```powershell
usbipd list
```

```
BUSID  VID:PID    DEVICE                                            STATE
4-1    10c4:ea60  Silicon Labs CP210x USB to UART Bridge (COM3)     Not shared
4-2    0d8c:0012  USB Audio Device, USB Input Device                Not shared
```

Your bus IDs may differ if you use a different USB port. **Bind** once per
device, from an **Administrator** PowerShell:

```powershell
usbipd bind --busid 4-1
usbipd bind --busid 4-2
```

**Attach** both to WSL. This doesn't need admin. Make sure a WSL terminal is
open first:

```powershell
usbipd attach --wsl --busid 4-1
usbipd attach --wsl --busid 4-2
```

`usbipd list` should now show both as `Attached`.

You have to attach again after unplugging the Digirig, rebooting, or running
`wsl --shutdown`. To have usbipd keep re-attaching automatically while the
PowerShell window stays open:

```powershell
usbipd attach --wsl --busid 4-1 --auto-attach
```

(Run one of those per device, each in its own window.) To give the devices
back to Windows: `usbipd detach --busid 4-1` (and `4-2`).

## 3. WSL packages, groups, and device permissions (WSL, once)

```bash
sudo apt-get update
sudo apt-get install -y alsa-utils usbutils python3-serial
sudo usermod -aG dialout,audio $USER
```

(`python3-serial` is the apt-packaged pyserial. Ubuntu 24.04 blocks a bare
`pip3 install pyserial` outside a venv.)

**WSL-specific fix:** the device nodes created for usbipd-attached devices
can come up owned by group IDs that don't exist in the distro (e.g.
`crw-rw---- root 18 /dev/ttyUSB0`, `root 63 /dev/snd/*`), so even a
`dialout`/`audio` member can't open them. A udev rule puts the right groups
on them every time they're attached:

```bash
sudo tee /etc/udev/rules.d/99-digirig-wsl.rules >/dev/null <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", GROUP="dialout", MODE="0660"
SUBSYSTEM=="sound", GROUP="audio", MODE="0660"
EOF
sudo udevadm control --reload
sudo udevadm trigger
```

New group membership only applies to new logins. Close every WSL terminal,
or run `wsl --shutdown` from Windows, reopen, and repeat the **attach** step
from section 2. You can also run a single command with the new group right
away, without logging in again: `sg audio -c "arecord -l"`.

## 4. Verify (WSL)

```bash
groups                                  # includes dialout and audio
ls -l /dev/ttyUSB0 /dev/serial/by-id/   # root dialout, CP2102N by-id link
ls -l /dev/snd/                         # root audio
arecord -l                              # card N: Device [USB Audio Device]
aplay -l
cat /proc/asound/Device/stream0         # playback 2ch, capture 1ch, 44.1k/48k
```

The Digirig's playback is stereo-only, so always use
`plughw:CARD=Device,DEV=0` (not `hw:`). The card name `Device` works no
matter which card number WSL assigns.

## 5. Mixer levels (WSL)

These are the same values as SETUP.md's "Digirig: copy-paste setup":

```bash
amixer -c Device cset name='Auto Gain Control' off
amixer -c Device cset name='Mic Capture Volume' 12        # 0 dB
amixer -c Device cset name='Speaker Playback Volume' 14   # -23 dB
sudo alsactl store
```

A fresh attach starts the card at its defaults (AGC **on**, mic 20,
speaker 27). WSL doesn't reliably restore `alsactl store` state when the
device is attached, so after every attach either run `sudo alsactl restore`
or re-run the three `amixer` lines above.

## 6. Test without transmitting (WSL, from the project root)

Run the pure-software round trip:

```bash
cd /path/to/zsignal-project
python3 -m zsignal selftest
```

Record 5 seconds of receive audio from the radio:

```bash
arecord -D plughw:CARD=Device,DEV=0 -f S16_LE -r 48000 -c 1 -d 5 rx.wav
```

With the squelch closed you should get near-silence (about -80 dBFS). Open
the squelch or receive a signal to see real levels, and check there's no
clipping.

Next, check that the PTT serial port opens **without keying the radio**.
pyserial raises RTS by default when it opens a port, so set RTS low before
opening:

```bash
python3 -c "
import serial
s = serial.Serial(); s.port = '/dev/ttyUSB0'; s.baudrate = 9600
s.rts = False; s.dtr = False
s.open(); print('opened', s.name, 'RTS', s.rts); s.close()"
```

Run `python3 -m zsignal --help` for the receive/listen and transmit commands,
and see `PTT_NOTES.md` for how PTT is driven. Only transmit when you're
licensed for the frequency and it's clear.

## 7. Running the services

**Native CLI:** run the commands from SETUP.md sections 5 and later from the
project root, using `--play-device`/`--rec-device plughw:CARD=Device,DEV=0` and
`--ptt-serial /dev/ttyUSB0`.

**Docker** (tested: Docker Engine 29.1.3 and Compose 2.40.3 inside
Ubuntu 24.04). Install Docker Engine inside the distro. `systemd` is enabled
by default on current WSL Ubuntu, so the daemon runs as a normal service:

```bash
./setup.sh --fix                       # installs docker.io + docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
getent group docker                    # must list your user
```

Check that last line. If `setup.sh --fix` doesn't add you to the group,
you'll get `permission denied while trying to connect to the docker API`.
After adding yourself, start a new login (close the WSL terminals) to pick
up the group.

Build and start the web app from the project root:

```bash
docker compose build                   # builds zsignal-web and zsignal-receiver
docker compose up -d zsignal-web
docker compose logs zsignal-web        # should show "Running on all addresses (0.0.0.0)"
```

zsignal-web is then at <http://localhost:5055> from a Windows browser,
because WSL2 forwards localhost ports to Windows. On the Settings tab, set
audio device `plughw:CARD=Device,DEV=0` and PTT serial port `/dev/ttyUSB0`.
They're saved in the `zsignal-web-data` volume (`/data/settings.json`) and
survive restarts.

`docker-compose.yml` already passes `/dev/snd` and `/dev/ttyUSB0` through,
and the container runs as root, so the host's groups don't matter inside it.
To check the container can see the Digirig:

```bash
docker compose exec zsignal-web sh -c 'ls -l /dev/ttyUSB0; arecord -l'
```

**Attach the Digirig before starting the container.** Docker only passes
through devices that exist when the container starts, so after a re-attach
run `docker compose restart zsignal-web`. If `/dev/ttyUSB0` doesn't exist at
all, `docker compose up` fails with a "no such file or directory" error for
the device. Docker Desktop's WSL backend hasn't been tested with usbipd
devices. Docker Engine inside the distro is the known-good path.

### Tested on this setup

The following worked in the container: the UI and static assets loading,
saving settings, settings surviving a restart, and Listen start, levels and
stop recording live from the Digirig. The **Listen** path only runs
`arecord` and never opens the PTT port. **Send**, **Station COMS** and
**Volleyball** key the radio through RTS. Only use them when you're licensed
for the frequency and it's clear. Transmitting from the container hasn't
been verified on WSL2 yet.

`zsignal-receiver` builds on WSL2 but is meant for the Orange Pi's GPIO
relay board. Don't run it here.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `usbipd: The term 'usbipd' is not recognized` | PowerShell was opened before the install. Open a new window, or use the full path `C:\Program Files\usbipd-win\usbipd.exe`. |
| `WARNING: usbipd not found for kernel ...` | You ran `usbipd` inside WSL. Run it in Windows PowerShell. |
| `bind` fails with access denied | `bind` needs an **Administrator** PowerShell. |
| No `/dev/ttyUSB0`, or `arecord -l` shows `no soundcards found` | The device isn't attached (check `usbipd list` on Windows), **or** your shell doesn't have the `audio` group yet (start a new login). `cat /proc/asound/cards` lists the card even without permission. |
| `Permission denied` on `/dev/ttyUSB0` or `/dev/snd/*` with numeric group (18, 63) | The udev rule from section 3 is missing. Add it, then run `sudo udevadm trigger`. |
| Received audio clips or the level drifts | AGC was turned back on by a re-attach. Redo section 5. |
| Windows lost its "USB Audio Device" sound device | It's attached to WSL. Run `usbipd detach --busid <id>`. |
| Container can't see the devices | They were attached after the container started. Run `docker compose restart zsignal-web`. |
| `permission denied while trying to connect to the docker API` | You're not in the `docker` group (`getent group docker`), or your shell predates joining it. Run `sudo usermod -aG docker $USER`, then start a new login. |
| `sg docker` asks for a password | `/etc/group` doesn't actually list you in `docker` yet. Run the `usermod` above. |
