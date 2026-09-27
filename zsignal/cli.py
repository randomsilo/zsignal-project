import argparse
import sys
import tempfile
import time
import os

from . import audio, gpio, protocol
from .decoder import decode_samples, DecodeError

PTT_PIN = 73  # PC9 (sysfs GPIO numbering) -- drives the PTT relay
PTT_DELAY = 0.5  # seconds to hold PTT before audio starts, letting the radio key up
PTT_TAIL_DELAY = 0.5  # seconds to hold PTT after audio ends, before releasing it
# ALSA default relies on system config, which may not point at the USB audio
# dongle wired to the radio -- aplay then fails and crashes mid-transmission,
# dropping PTT early. Confirm the real card with `aplay -l` and correct this.
# On Windows this is unused (winsound has no device selection) -- set the
# interface as the Windows default playback device in Sound settings instead.
AUDIO_DEVICE = None if sys.platform == "win32" else "plughw:CARD=Device,DEV=0"


def _encode_samples(text, sample_rate, chord_ms):
    payload = protocol.text_to_bytes(text)
    chords = protocol.build_frame_chords(payload)
    samples = audio.synthesize_chords(chords, sample_rate=sample_rate, chord_ms=chord_ms)
    return payload, chords, samples


def cmd_encode(args):
    payload, chords, samples = _encode_samples(args.text, args.sample_rate, args.chord_ms)
    audio.write_wav(args.output, samples, sample_rate=args.sample_rate)
    duration = len(samples) / float(args.sample_rate)
    print("text:    %r" % args.text)
    print("hex:     %s (%d bytes)" % (protocol.bytes_to_hex(payload), len(payload)))
    print("chords:  %d  duration: %.2fs" % (len(chords), duration))
    print("wrote:   %s" % args.output)


def cmd_decode(args):
    samples, sample_rate = audio.read_wav(args.input)
    try:
        result = decode_samples(samples, sample_rate, chord_ms=args.chord_ms)
    except DecodeError as e:
        print("DECODE FAILED: %s" % e)
        return 1
    _print_result(result)
    return 0 if result["found_end"] and not result["corrupted"] else 1


def _print_result(result):
    print("hex:     %s" % result["hex"])
    print("text:    %r" % result["text"])
    print("bytes:   %d" % len(result["bytes"]))
    print("end chord found: %s" % result["found_end"])
    if result["corrupted"]:
        print("CORRUPTED bits: %s" % result["corrupted"])
    if result["unknown_chords"]:
        print("unknown/unclassifiable chords: %d" % result["unknown_chords"])
    if result["imd_warning"]:
        print("WARNING: guard-band (2900 Hz) energy elevated -> possible intermodulation distortion")


def cmd_selftest(args):
    messages = args.message if args.message else [
        "hi",
        "hello zsignal",
        "The quick brown fox jumps over the lazy dog. 0123456789",
    ]
    all_ok = True
    for msg in messages:
        payload, chords, samples = _encode_samples(msg, args.sample_rate, args.chord_ms)

        # 1) in-memory round trip (no audio hardware, no file I/O)
        result = decode_samples(samples, args.sample_rate, chord_ms=args.chord_ms)
        ok_mem = result["text"] == msg and result["found_end"] and not result["corrupted"]

        # 2) through a WAV file, exercising the same file I/O used for real hardware
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "selftest.wav")
            audio.write_wav(path, samples, sample_rate=args.sample_rate)
            wav_samples, sr = audio.read_wav(path)
            result_wav = decode_samples(wav_samples, sr, chord_ms=args.chord_ms)
        ok_wav = result_wav["text"] == msg and result_wav["found_end"] and not result_wav["corrupted"]

        ok = ok_mem and ok_wav
        all_ok = all_ok and ok
        status = "OK" if ok else "FAIL"
        print("[%s] %r  (in-memory=%s, wav=%s)" % (status, msg, ok_mem, ok_wav))
        if not ok:
            print("    got (mem): %r" % result["text"])
            print("    got (wav): %r" % result_wav["text"])

    if not all_ok:
        print("SELFTEST: one or more messages failed")
        return 1
    print("SELFTEST: all messages round-tripped cleanly")
    return 0


def _key_and_play(path, args, ptt_on, ptt_off, ptt_label):
    print("PTT: %s on, waiting %dms" % (ptt_label, args.ptt_delay * 1000))
    ptt_on()
    try:
        time.sleep(args.ptt_delay)
        audio.play(path, device=args.device)
        time.sleep(args.ptt_tail_delay)
    finally:
        ptt_off()
        print("PTT: %s off" % ptt_label)


def send_text(text, device=None, ptt_pin=None, ptt_serial=None,
              ptt_delay=PTT_DELAY, ptt_tail_delay=PTT_TAIL_DELAY,
              sample_rate=audio.SAMPLE_RATE, chord_ms=audio.CHORD_MS):
    """Encode `text` and transmit it with PTT. Returns (payload_bytes, duration_seconds).

    Shared by the CLI's `send` command and zsignal-web -- one place for the
    encode -> key PTT -> play -> release PTT sequence.
    """
    payload, chords, samples = _encode_samples(text, sample_rate, chord_ms)

    class _Args(object):
        pass
    args = _Args()
    args.device = device
    args.ptt_delay = ptt_delay
    args.ptt_tail_delay = ptt_tail_delay

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "tx.wav")
        audio.write_wav(path, samples, sample_rate=sample_rate)
        duration = len(samples) / float(sample_rate)
        print("sending %r (%s, %.2fs) via %s" % (
            text, protocol.bytes_to_hex(payload), duration, device or "default"))

        if ptt_serial:
            from . import serial_ptt
            with serial_ptt.SerialPTT(ptt_serial) as ptt:
                _key_and_play(path, args, ptt.on, ptt.off,
                              "serial %s (RTS)" % ptt_serial)
        elif ptt_pin is not None:
            _key_and_play(path, args,
                          lambda: gpio.set_pin(ptt_pin, 1),
                          lambda: gpio.set_pin(ptt_pin, 0),
                          "GPIO%d" % ptt_pin)
        else:
            audio.play(path, device=device)
    print("sent.")
    return payload, duration


def cmd_send(args):
    send_text(args.text, device=args.device, ptt_pin=args.ptt_pin,
              ptt_serial=args.ptt_serial, ptt_delay=args.ptt_delay,
              ptt_tail_delay=args.ptt_tail_delay,
              sample_rate=args.sample_rate, chord_ms=args.chord_ms)


def cmd_listen(args):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "rx.wav")
        print("recording %.1fs from %s ..." % (args.seconds, args.device or "default"))
        audio.record(path, args.seconds, device=args.device, sample_rate=args.sample_rate)
        samples, sr = audio.read_wav(path)
        if args.save:
            audio.write_wav(args.save, samples, sample_rate=sr)
    try:
        result = decode_samples(samples, sr, chord_ms=args.chord_ms)
    except DecodeError as e:
        print("DECODE FAILED: %s" % e)
        return 1
    _print_result(result)
    return 0 if result["found_end"] and not result["corrupted"] else 1


def cmd_loopback(args):
    """Encode -> play out speaker -> record from mic (same box, bridged cable) -> decode."""
    payload, chords, samples = _encode_samples(args.text, args.sample_rate, args.chord_ms)
    tx_duration = len(samples) / float(args.sample_rate)
    record_seconds = tx_duration + args.pad

    with tempfile.TemporaryDirectory() as d:
        tx_path = os.path.join(d, "tx.wav")
        rx_path = os.path.join(d, "rx.wav")
        audio.write_wav(tx_path, samples, sample_rate=args.sample_rate)

        print("text:   %r" % args.text)
        print("hex:    %s (%d bytes, %d chords, %.2fs)" % (
            protocol.bytes_to_hex(payload), len(payload), len(chords), tx_duration))
        print("recording %.2fs on %s while playing on %s ..." % (
            record_seconds, args.rec_device or "default", args.play_device or "default"))

        rec_proc = audio.record_async(rx_path, record_seconds, device=args.rec_device,
                                       sample_rate=args.sample_rate)
        time.sleep(args.lead_in)
        audio.play(tx_path, device=args.play_device)
        rec_proc.wait()

        if args.save:
            import shutil
            shutil.copyfile(rx_path, args.save)

        samples_rx, sr = audio.read_wav(rx_path)

    try:
        result = decode_samples(samples_rx, sr, chord_ms=args.chord_ms)
    except DecodeError as e:
        print("DECODE FAILED: %s" % e)
        return 1

    _print_result(result)
    ok = result["text"] == args.text and result["found_end"] and not result["corrupted"]
    print("ROUND TRIP: %s" % ("OK" if ok else "MISMATCH/DEGRADED"))
    return 0 if ok else 1


def build_parser():
    p = argparse.ArgumentParser(prog="zsignal", description="zsignal tone-chord codec utility")
    p.add_argument("--sample-rate", type=int, default=audio.SAMPLE_RATE)
    p.add_argument("--chord-ms", type=float, default=audio.CHORD_MS)
    sub = p.add_subparsers(dest="cmd")

    pe = sub.add_parser("encode", help="encode text to a zsignal WAV file (no hardware)")
    pe.add_argument("text")
    pe.add_argument("-o", "--output", required=True)
    pe.set_defaults(func=cmd_encode)

    pd = sub.add_parser("decode", help="decode a zsignal WAV file to text")
    pd.add_argument("input")
    pd.set_defaults(func=cmd_decode)

    ps = sub.add_parser("selftest", help="pure-software encode->decode round trip (no audio)")
    ps.add_argument("--message", action="append", help="repeatable; defaults to a small builtin set")
    ps.set_defaults(func=cmd_selftest)

    psend = sub.add_parser("send", help="encode and play text out an ALSA device")
    psend.add_argument("text")
    psend.add_argument("-D", "--device", default=AUDIO_DEVICE,
                        help="ALSA device, e.g. hw:1,0 (default: %s)" % AUDIO_DEVICE)
    psend.add_argument("--ptt-pin", type=int, default=PTT_PIN,
                        help="sysfs GPIO pin to drive high for PTT before/during TX (default: %d / PC9)" % PTT_PIN)
    psend.add_argument("--ptt-delay", type=float, default=PTT_DELAY,
                        help="seconds to hold PTT high before audio starts (default: %.1f)" % PTT_DELAY)
    psend.add_argument("--ptt-tail-delay", type=float, default=PTT_TAIL_DELAY,
                        help="seconds to hold PTT high after audio ends (default: %.1f)" % PTT_TAIL_DELAY)
    psend.add_argument("--no-ptt", dest="ptt_pin", action="store_const", const=None,
                        help="disable PTT GPIO control")
    psend.add_argument("--ptt-serial", default=None,
                        help="serial port for RTS-based PTT, e.g. /dev/ttyACM0 "
                             "(a USB PTT/audio interface like Digirig Mobile); "
                             "overrides --ptt-pin when set")
    psend.set_defaults(func=cmd_send)

    plisten = sub.add_parser("listen", help="record from an ALSA device and decode")
    plisten.add_argument("-D", "--device", default=AUDIO_DEVICE,
                          help="ALSA device, e.g. hw:1,0 (default: %s)" % AUDIO_DEVICE)
    plisten.add_argument("--seconds", type=float, default=5.0)
    plisten.add_argument("--save", default=None, help="also save the recording to this WAV path")
    plisten.set_defaults(func=cmd_listen)

    plb = sub.add_parser("loopback", help="send+record+decode in one shot (same-box loopback test)")
    plb.add_argument("text")
    plb.add_argument("--play-device", default=None, help="ALSA playback device, e.g. hw:1,0")
    plb.add_argument("--rec-device", default=None, help="ALSA capture device, e.g. hw:1,0")
    plb.add_argument("--pad", type=float, default=1.5, help="extra recording seconds after tx ends")
    plb.add_argument("--lead-in", type=float, default=0.4, help="delay before playback so recorder is armed")
    plb.add_argument("--save", default=None, help="also save the raw recording to this WAV path")
    plb.set_defaults(func=cmd_loopback)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.error("a subcommand is required")
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
