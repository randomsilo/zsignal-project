# zsignal

An audio-tone data protocol for sending binary/hex payloads over analog FM voice radio (handheld transceivers) using simultaneous multi-tone "chords" in the 1000–3000 Hz band, with built-in per-bit error detection.

## Concept

Standard digital radio protocols (DMR, P25) rely on vocoders tuned for speech, which destroy arbitrary tone patterns. zsignal instead treats the radio as a pure analog audio pipe — same principle as DTMF or paging tones (POCSAG/FLEX) — and encodes data as combinations of simultaneous audio tones within the voice passband (~300–3000 Hz) that any analog FM handheld can pass.

Each transmitted "chord" (a set of tones playing at once) encodes **one byte (8 bits)**. A byte's bits are sent twice — once as themselves, once inverted on a mirrored set of tones — so the receiver can detect (not just guess at) corrupted bits caused by noise, fading, or handheld audio nonlinearity.

## Tone Map

21 tones spaced 100 Hz apart from 1000 Hz to 3000 Hz.

| Freq (Hz) | Index | Data Chord Role | Spacer Chord Role | End Chord Role | Sync/Preamble Chord Role |
|---|---|---|---|---|---|
| 1000 | 00 | Always On — signal detect | Always On — signal detect | Always On — signal detect | Always On — signal detect |
| 1100 | 01 | Bit 1 | Off | On | Off |
| 1200 | 02 | Bit 2 | Off | On | Off |
| 1300 | 03 | Bit 3 | Off | On | Off |
| 1400 | 04 | Bit 4 | Off | On | Off |
| 1500 | 05 | Bit 5 | Off | On | Off |
| 1600 | 06 | Bit 6 | Off | On | Off |
| 1700 | 07 | Bit 7 | Off | On | Off |
| 1800 | 08 | Bit 8 | Off | On | Off |
| 1900 | 09 | Always Off — data flag | Always On — spacer flag | Always Off — spacer flag | Always On — sync flag |
| 2000 | 10 | Always Off — data flag | Always On — spacer flag | Always Off — spacer flag | Always Off |
| 2100 | 11 | Bit 1 (inverse) | Off | On | Off |
| 2200 | 12 | Bit 2 (inverse) | Off | On | Off |
| 2300 | 13 | Bit 3 (inverse) | Off | On | Off |
| 2400 | 14 | Bit 4 (inverse) | Off | On | Off |
| 2500 | 15 | Bit 5 (inverse) | Off | On | Off |
| 2600 | 16 | Bit 6 (inverse) | Off | On | Off |
| 2700 | 17 | Bit 7 (inverse) | Off | On | Off |
| 2800 | 18 | Bit 8 (inverse) | Off | On | Off |
| 2900 | 19 | Unused (guard band) | Unused | Unused | Unused |
| 3000 | 20 | Always On — signal detect | Always On — signal detect | Always On — signal detect | Always On — signal detect |

### Frame types

- **Data chord**: carries one byte. Bits 1–8 (tones 01–08) are the data; bits 1–8 inverse (tones 11–18) are the bitwise complement. For a valid chord, tone N and tone N+10 must always disagree (one on, one off).
- **Spacer chord**: all data/inverse tones off, flag tones 1900/2000 on. Marks a gap between bytes. Cannot be produced by valid data (both flag tones on is otherwise illegal), so it's unambiguous.
- **End chord**: all data/inverse tones on, flag tones 1900/2000 off. Marks end of transmission. Same "impossible in real data" logic as Spacer, distinguished from it by the flag tones being inverted.
- **Sync/preamble chord**: all data/inverse tones off, flag tone 1900 on, flag tone 2000 off. Repeated several times at the start of a transmission so the receiver can lock onto the signal before real data begins. Distinguished from Spacer (both flags on) and End (all data/inverse on) by its unique flag-tone combination, so it can't be produced by any other chord type.

Bookend tones (1000 Hz, 3000 Hz) are always on in every chord type, used for receiver lock/level reference and signal-presence detection.

## Error Detection

Because bit N and its inverse (tone N+10) should never match, any chord where a bit/inverse pair reads the same state (both on or both off) indicates that tone position was corrupted in transit. This gives single-tone-dropout detection per chord without a separate checksum. It does not currently provide correction — a corrupted chord is flagged, not repaired.

## Frame Structure (payload)

A 20-bit payload requires 3 data chords (24-bit capacity, 4 bits unused/padding):

```
[Preamble/Sync] [Data chord 1] [Spacer] [Data chord 2] [Spacer] [Data chord 3] [End]
```

Each data chord = 1 byte = 2 hex digits. A preamble (TBD — likely a short known tone pattern) is needed before the first chord so the receiver can establish timing/level lock before real data starts, similar to POCSAG's alternating-bit preamble.

## Physical / Timing Constraints

- **Tone spacing**: 100 Hz between adjacent tones.
- **Minimum chord duration**: governed by `Δf ≥ 1.5 / T` for non-coherent detection → T ≥ 15 ms at 100 Hz spacing. Target 25–40 ms per chord in practice to leave margin for radio audio-chain filtering and Goertzel detection accuracy.
- **Effective throughput estimate**: ~15–25 bytes/sec including spacer/framing overhead. This is a telemetry/status-message protocol, not a file-transfer protocol.
- **Detection method**: Goertzel algorithm per known tone frequency (not full FFT) — cheap enough for the target hardware.

## Known Risks

- **Intermodulation distortion (IMD)**: with up to ~21 simultaneous tones, FM handheld nonlinearities (mic preamp, compander, speaker) can generate sum/difference products landing on other tone frequencies, causing false detections. Tone 2900 Hz (unused) is a canary — any energy appearing there on a recorded test transmission indicates IMD.
- **Amplitude imbalance**: FM compander/AGC behavior can reshape relative tone levels; detection should rely on frequency presence (Goertzel) rather than absolute amplitude thresholds.
- **Digital radios (DMR/P25/NXDN)**: vocoders will almost certainly destroy the tone structure. zsignal is analog-FM-only.

## Hardware Test Setup

### Current: Xubuntu on an ASUS Chromebook (C223NA)

The Orange Pi Zero 3 (below) was abandoned as the field/portable box after its
PTT circuit repeatedly crashed the whole board — first traced to a DIY relay,
then reproduced identically with a properly-isolated Digirig Mobile USB
interface, which showed the Pi itself (its power supply/USB headroom) was the
real constraint, not the PTT hardware. Full history in `PTT_NOTES.md`.

The replacement is a used ASUS Chromebook C223NA (~$50, Intel Celeron N3350,
4GB RAM, 32GB eMMC — Apollo Lake/"coral" board family) reflashed to run
Xubuntu instead of ChromeOS, with a Digirig Mobile (USB audio + hardware PTT
via RTS) as the radio interface. This sidesteps the Pi's power problem
entirely — the Chromebook has its own proper battery/power management — and
since PTT now goes over USB-serial (`--ptt-serial`) rather than GPIO, none of
the SBC-specific wiring is needed anymore.

#### Converting the C223NA from ChromeOS to Xubuntu

This is the exact procedure that worked on this specific unit (ChromeOS
126, version 15886.74.0, board `coral-signed-mp-v2keys`). Screen text and
exact steps can vary by ChromeOS version — if something doesn't match,
check `mrchromebox.tech` directly for current guidance for the `coral` board.

1. **Enable Developer Mode.** Power off, hold **Esc + Refresh (F3)**, tap
   **Power**, then at the recovery screen press **Ctrl+D** (not Space).
   Confirm through the powerwash (several minutes, multiple reboots). On
   every subsequent boot you'll see a red-bordered "OS verification is
   OFF" warning screen — press **Ctrl+D** or wait ~30s to continue; pressing
   **Space** there re-enables verification and undoes dev mode.
2. **Browse as Guest** at the login screen rather than completing full
   account setup.
3. **Get a privileged shell.** Ctrl+Alt+T opens `crosh`, but neither its
   `shell` command (`ERROR: unknown command: shell` on newer builds) nor
   `bash` typed there gets you a shell that can actually `sudo` — bash
   would run, but `sudo` in it failed with "the no new privileges flag is
   set." What actually worked: press **Ctrl+Alt+Refresh (F3)** to switch to
   a different terminal entirely, then run:
   ```
   sudo sh
   ```
   there to get an actual root shell. Confirm with `whoami` (should say
   `chronos` before this, `root` after).
4. **Fix Backspace if it's not erasing characters.** This terminal's `stty`
   erase setting may not match what your Backspace key sends. Fix:
   ```
   stty erase
   ```
   then press **Ctrl+V** followed by the **Backspace** key (inserts the raw
   byte your key actually sends) before hitting Enter.
5. **Disable firmware write protection.** No physical write-protect screw
   removal was needed on this unit (opening the case and unplugging the
   battery did nothing useful) — just run:
   ```
   flashrom --wp-disable
   ```
   If a later flash attempt fails, check `flashrom --wp-status`; only then
   consider physically removing the board's WP screw.
6. **Run MrChromebox's firmware utility.** `cd`ing with no argument can
   leave you in `/`, which is always read-only on ChromeOS — go somewhere
   writable first. `/usr/local/tmp` didn't exist on this unit, so `/usr/local`
   itself (writable in dev mode) was used directly instead of creating it:
   ```
   cd /usr/local
   curl -LOf https://mrchromebox.tech/firmware-util.sh
   sudo bash firmware-util.sh
   ```
   (Check `mrchromebox.tech` directly if this filename/URL ever changes —
   this is the exact one that worked here.)
7. **Choose "Install/Update UEFI (Full ROM) Firmware"** from the menu —
   not the `RW_LEGACY`/"Legacy Boot Stub" option. This fully replaces
   ChromeOS's firmware with standard UEFI; there's no going back to
   ChromeOS from here.
8. **Power off completely (not a warm reboot)** once flashing finishes, to
   ensure the embedded controller cold-boots into the new firmware cleanly.
9. **Boot from a Xubuntu USB installer** (made with Rufus/balenaEtcher/`dd`
   on another machine) with it plugged in when you power back on — you'll
   land in a normal UEFI boot menu with nothing else to boot into. Install
   Xubuntu normally from there.

Once Xubuntu is running: `sudo apt install alsa-utils python3-pip`,
`pip3 install pyserial`, copy over the `zsignal/` package, plug in the
Digirig (enumerates as e.g. `/dev/ttyUSB0` for RTS PTT — it uses a Silicon
Labs CP210x chip, not CDC-ACM, so it's `ttyUSB*` and not `ttyACM*` — and
`card N: Device [USB Audio Device]` per `aplay -l` for audio).

### Abandoned: Orange Pi Zero 3

Bench setup was an Orange Pi Zero (armv7l, ~492MB RAM, Ubuntu 18.04, Python
3.6.9) with a USB sound card, speaker output bridged by cable directly to mic
input (audio loopback), used to validate encode/decode logic before testing
over an actual RF link. The USB card (`USB Audio Device`, ALSA card 1) is
stereo-only at the hardware level, so playback/capture went through ALSA's
`plughw:1,0` (not raw `hw:1,0`) to get automatic mono↔stereo and rate
conversion. This part of the pipeline worked fine — it was specifically the
GPIO/relay-driven PTT circuit that made the board itself crash. See
`PTT_NOTES.md` for the full debugging history.

## Implementation

Implemented as a pure standard-library Python package (`zsignal/`) — no numpy/scipy — so the identical codebase runs unmodified on Windows, Linux (Xubuntu, or the earlier Orange Pi), and anywhere else Python 3 runs. Audio in/out is delegated to ALSA's command-line tools (`aplay`/`arecord`) on Linux, or the stdlib `winsound` module for playback on Windows (recording not yet implemented there); `wave` (stdlib) handles WAV file I/O.

| File | Responsibility |
|---|---|
| `protocol.py` | Tone map constants, chord construction (data/spacer/end/preamble), chord classification |
| `goertzel.py` | Pure-Python Goertzel single-frequency magnitude detector |
| `audio.py` | Chord synthesis to PCM, WAV read/write, `aplay`/`arecord` subprocess wrappers |
| `decoder.py` | Preamble onset detection + chord-by-chord frame decode |
| `serial_ptt.py` | RTS-based PTT over a USB PTT/audio interface (e.g. Digirig Mobile), via `pyserial` |
| `live_listen.py` | Continuous capture + silence-gap segmentation for streaming/live decode (used by zsignal-web) |
| `cli.py` / `__main__.py` | `python -m zsignal` command-line entry point |

### Design decisions made (filling in items the protocol spec left as TBD)

- **Sample rate**: 48 kHz. **Chord duration**: 30 ms (within the 25–40 ms target range).
- **Preamble/sync pattern**: 6 repetitions of a dedicated "sync chord" — bookend tones (1000/3000 Hz) on, flag tone 1900 Hz on, flag tone 2000 Hz off, all data/inverse tones off. This bit pattern can't occur in data, spacer, or end chords, so it's unambiguous. The decoder locates it with a coarse energy scan (bookend-tone power vs. an estimated noise floor) followed by a fine matched-filter search (±1 chord, 1 ms steps) that maximizes on-tone vs. off-tone energy to pin down the exact chord boundary.
- **Amplitude**: fixed per-tone amplitude (~0.04) rather than normalizing to a fixed peak per chord, so that "on" tones read the same Goertzel magnitude regardless of how many other tones are active in that chord — needed for reliable per-tone on/off thresholding.
- **On/off thresholding**: each chord's own bookend-tone magnitude (always on, by definition) is used as the reference level, and a tone is "on" if its magnitude exceeds 40% of that reference. This makes detection amplitude-invariant, per the Known Risks note about AGC/companding.
- **Framing padding**: 300 ms of lead-in silence and 200 ms of trail-out silence are added around every transmission, giving the receiver a quiet window to establish its noise floor and avoiding abrupt speaker clicks.
- **IMD canary check**: guard tone (2900 Hz) magnitude is tracked across the frame and compared to the bookend reference; the CLI prints an IMD warning if it's elevated.

### CLI usage

All commands are run as `python3 -m zsignal <subcommand> ...` (or `python -m zsignal ...`
on Windows). Global flags `--sample-rate` and `--chord-ms` apply to every subcommand.

```
python3 -m zsignal encode "text" -o out.wav         # text -> WAV file, no hardware
python3 -m zsignal decode in.wav                    # WAV file -> text
python3 -m zsignal selftest [--message "..."]       # pure-software round-trip check (repeatable flag)
python3 -m zsignal send "text" [options]            # encode + play out an audio device, with PTT
python3 -m zsignal listen [--seconds N] [-D dev] [--save out.wav]   # record + decode
python3 -m zsignal loopback "text" [options]        # play+record+decode in one shot (same-box test)
```

**`send` options:**

```
-D, --device DEV        ALSA device on Linux, e.g. hw:1,0 or plughw:1,0
                         (ignored on Windows -- winsound has no device
                         selection; set the interface as the Windows
                         default playback device in Settings > System >
                         Sound instead)
--ptt-pin N              sysfs GPIO pin to drive high for PTT (default: 73 / PC9)
--ptt-serial PORT         serial port for RTS-based PTT via a USB PTT/audio
                          interface (e.g. Digirig Mobile) -- /dev/ttyUSB0 or
                          /dev/ttyACM0 on Linux, COM3 etc. on Windows.
                          Overrides --ptt-pin when set. Requires pyserial
                          (pip3 install pyserial).
--no-ptt                  disable PTT control entirely (just play the audio)
--ptt-delay SECONDS       hold PTT before audio starts, letting the radio key up (default: 0.5)
--ptt-tail-delay SECONDS  hold PTT after audio ends, before releasing it (default: 0.5)
```

**`listen` options:** `-D/--device`, `--seconds` (recording length, default 5.0), `--save PATH`.

**`loopback` options:** `--play-device`, `--rec-device`, `--pad` (extra recording seconds
after TX ends, default 1.5), `--lead-in` (delay before playback so the recorder is armed,
default 0.4), `--save PATH`.

Examples:

```
# Linux / Orange Pi, GPIO relay PTT
python3 -m zsignal send "hello" -D plughw:CARD=Device,DEV=0 --ptt-pin 73

# Linux, Digirig-style USB PTT/audio interface
python3 -m zsignal send "hello" --ptt-serial /dev/ttyUSB0

# Windows, Digirig on COM3 (set it as the default playback device first)
python -m zsignal send "hello" --ptt-serial COM3

# No PTT hardware at all, just play the tones
python3 -m zsignal send "hello" --no-ptt
```

## Status / Next Steps

- [x] Build chord generator (tone synthesis + amplitude normalization for simultaneous tones)
- [x] Build Goertzel-based chord decoder
- [x] Validate encode → decode round-trip in pure software (no audio hardware) — `python -m zsignal selftest`, also stress-tested with injected noise/gain-scaling/DC-offset
- [x] Validate over sound-card speaker→mic loopback — 5/5 clean round trips on the Orange Pi's USB sound card (short and long messages, repeated trials), zero bit corruption, correct end-of-frame detection every time
- [x] Define preamble/sync pattern — see Implementation section above
- [x] Test over actual handheld TX → RX pair — sent both short and ~10s paragraph messages via a Digirig Mobile (RTS PTT), received cleanly on a second handheld
- [ ] Check for IMD at 2900 Hz on a real over-the-air recording (loopback-only so far)
- [ ] Add forward error correction (currently detection-only)

### Known issues hit and fixed along the way

- The Orange Pi's USB sound card only exposes stereo (`CHANNELS: 2`) at the raw ALSA `hw:` level — mono `aplay`/`arecord` against `hw:1,0` fails with "Channels count non available". Fixed by using `plughw:1,0` instead.
- `arecord -d` rejects fractional-second durations (`invalid duration argument '2.78'`) — the CLI now rounds recording duration up to the next whole second.
- `aplay` with no `-D` silently falls back to ALSA's `default` device, which may not be the USB interface actually wired to the radio — `aplay` then fails and crashes mid-transmission, dropping PTT early. Fixed by giving `--device` a real default (confirmed via `aplay -l`) instead of `None`.
- A USB cable that only carries power (no D+/D- data lines) makes a USB device completely invisible to the host — not a failed enumeration, no `dmesg` activity at all, just silence. Looks identical to "device not plugged in." Fixed by swapping to a cable known to carry data.
- On Windows, the Digirig's CP210x serial chip needs Silicon Labs' VCP driver installed manually (`ConfigManagerErrorCode 28` / "drivers not installed" in Device Manager until then) — Windows didn't auto-install it via Windows Update in this case.

## Naming

zsignal — working name for this schema/project.