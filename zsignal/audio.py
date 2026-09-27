"""Chord synthesis, WAV file I/O, and playback/capture.

Linux: shells out to ALSA's aplay/arecord. Windows: playback uses the
stdlib winsound module (no device selection -- set the interface as the
Windows default playback device in Sound settings instead); recording
isn't implemented there yet (no stdlib capture API).
"""

import array
import math
import subprocess
import sys
import wave

if sys.platform == "win32":
    import winsound

SAMPLE_RATE = 48000
CHORD_MS = 30
RAMP_MS = 4
AMPLITUDE = 0.85 / 21.0  # per-tone amplitude; 21 tones in-phase at t=0 stays < 0.85 peak
LEAD_SILENCE_MS = 300  # gives the onset detector a quiet region to measure noise floor
TRAIL_SILENCE_MS = 200


def synthesize_chords(chords, sample_rate=SAMPLE_RATE, chord_ms=CHORD_MS,
                       ramp_ms=RAMP_MS, amplitude=AMPLITUDE, freqs=None,
                       lead_silence_ms=LEAD_SILENCE_MS, trail_silence_ms=TRAIL_SILENCE_MS):
    """Render a list of chords (each a list[21] of bool) to a float sample list.

    Leading/trailing silence is included so a receiver can (a) establish a
    noise-floor estimate before the preamble and (b) so real hardware
    playback doesn't start/stop on an abrupt edge.
    """
    if freqs is None:
        from . import protocol
        freqs = protocol.TONE_FREQS

    chord_n = int(sample_rate * chord_ms / 1000.0)
    ramp_n = int(sample_rate * ramp_ms / 1000.0)
    two_pi = 2.0 * math.pi

    out = [0.0] * int(sample_rate * lead_silence_ms / 1000.0)
    for chord in chords:
        active = [freqs[i] for i, on in enumerate(chord) if on]
        block = [0.0] * chord_n
        for f in active:
            w = two_pi * f / sample_rate
            for n in range(chord_n):
                block[n] += amplitude * math.sin(w * n)
        # raised fade in/out to reduce inter-chord splatter/clicks
        for n in range(min(ramp_n, chord_n)):
            g = n / float(ramp_n)
            block[n] *= g
            block[chord_n - 1 - n] *= g
        out.extend(block)
    out.extend([0.0] * int(sample_rate * trail_silence_ms / 1000.0))
    return out


def floats_to_pcm16(samples):
    pcm = array.array("h")
    for s in samples:
        if s > 1.0:
            s = 1.0
        elif s < -1.0:
            s = -1.0
        pcm.append(int(s * 32767))
    return pcm


def pcm16_to_floats(pcm):
    return [s / 32768.0 for s in pcm]


def write_wav(path, samples_float, sample_rate=SAMPLE_RATE):
    pcm = floats_to_pcm16(samples_float)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())


def read_wav(path):
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)

    if sampwidth != 2:
        raise ValueError("only 16-bit WAV supported, got sampwidth=%d" % sampwidth)

    pcm = array.array("h")
    pcm.frombytes(raw)

    if channels == 1:
        mono = pcm
    elif channels == 2:
        mono = array.array("h", [0]) * (len(pcm) // 2)
        for i in range(len(mono)):
            mono[i] = (pcm[2 * i] + pcm[2 * i + 1]) // 2
    else:
        raise ValueError("only mono/stereo WAV supported, got %d channels" % channels)

    return pcm16_to_floats(mono), sample_rate


def play(path, device=None):
    if sys.platform == "win32":
        winsound.PlaySound(path, winsound.SND_FILENAME)
        return
    cmd = ["aplay", "-q"]
    if device:
        cmd += ["-D", device]
    cmd.append(path)
    subprocess.run(cmd, check=True)


def record(path, seconds, device=None, sample_rate=SAMPLE_RATE):
    if sys.platform == "win32":
        raise NotImplementedError(
            "recording isn't implemented on Windows yet (no stdlib capture "
            "API) -- send-only from here, or use 'listen'/'loopback' on Linux")
    cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(sample_rate), "-c", "1",
           "-d", str(int(math.ceil(seconds)))]
    if device:
        cmd += ["-D", device]
    cmd.append(path)
    subprocess.run(cmd, check=True)


def record_async(path, seconds, device=None, sample_rate=SAMPLE_RATE):
    if sys.platform == "win32":
        raise NotImplementedError(
            "recording isn't implemented on Windows yet (no stdlib capture "
            "API) -- send-only from here, or use 'listen'/'loopback' on Linux")
    cmd = ["arecord", "-q", "-f", "S16_LE", "-r", str(sample_rate), "-c", "1",
           "-d", str(int(math.ceil(seconds)))]
    if device:
        cmd += ["-D", device]
    cmd.append(path)
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def record_stream(device=None, sample_rate=SAMPLE_RATE):
    """Start an open-ended raw-PCM capture (mono S16_LE) for live/streaming use.

    Caller reads fixed-size chunks from the returned process's stdout and is
    responsible for calling .terminate() when done -- there's no fixed
    duration, unlike record()/record_async().
    """
    if sys.platform == "win32":
        raise NotImplementedError(
            "streaming capture isn't implemented on Windows yet (no stdlib "
            "capture API) -- use Linux for live listening")
    cmd = ["arecord", "-q", "-t", "raw", "-f", "S16_LE", "-r", str(sample_rate), "-c", "1"]
    if device:
        cmd += ["-D", device]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
