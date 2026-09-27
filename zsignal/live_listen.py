"""Continuous listen: capture audio, segment on silence gaps, decode each segment.

Unlike decoder.decode_samples() (one WAV file, one decode), this segments a
live audio stream into discrete transmissions separated by a gap of silence,
decoding each as it completes. Used by zsignal-web's Listen tab.
"""

import array
import queue
import threading
import time

from . import audio as audio_mod
from .decoder import decode_samples, DecodeError

GAP_SECONDS = 1.0
NOISE_PROBE_SECONDS = 0.5
SIGNAL_RATIO = 4.0  # a chunk counts as "signal" once RMS exceeds noise_floor * this
CHUNK_MS = 100


def _pcm16_bytes_to_floats(raw):
    a = array.array("h")
    a.frombytes(raw)
    return audio_mod.pcm16_to_floats(a)


def _rms(samples):
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5


class LiveListener:
    """Runs a background thread that segments incoming audio on silence gaps
    and decodes each segment, pushing results onto a thread-safe queue.
    """

    def __init__(self, device=None, sample_rate=audio_mod.SAMPLE_RATE, chord_ms=30,
                 gap_seconds=GAP_SECONDS, chunk_ms=CHUNK_MS):
        self.device = device
        self.sample_rate = sample_rate
        self.chord_ms = chord_ms
        self.gap_seconds = gap_seconds
        self.chunk_ms = chunk_ms
        self.events = queue.Queue()
        self._proc = None
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        self._stop.clear()
        self._proc = audio_mod.record_stream(device=self.device, sample_rate=self.sample_rate)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._proc is not None:
            self._proc.terminate()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self):
        chunk_samples = int(self.sample_rate * self.chunk_ms / 1000.0)
        bytes_per_chunk = chunk_samples * 2  # mono 16-bit
        noise_probe_chunks = max(1, int(NOISE_PROBE_SECONDS * 1000 / self.chunk_ms))
        gap_chunks_needed = max(1, int(self.gap_seconds * 1000 / self.chunk_ms))

        segment = []
        silence_run = 0
        noise_floor = None
        calibration = []

        stdout = self._proc.stdout
        try:
            while not self._stop.is_set():
                raw = stdout.read(bytes_per_chunk)
                if not raw or len(raw) < 2:
                    break
                floats = _pcm16_bytes_to_floats(raw)
                level = _rms(floats)

                if noise_floor is None:
                    calibration.append(level)
                    if len(calibration) >= noise_probe_chunks:
                        noise_floor = sorted(calibration)[len(calibration) // 2]
                    continue

                is_signal = level > max(noise_floor * SIGNAL_RATIO, 1e-6)

                if is_signal:
                    segment.extend(floats)
                    silence_run = 0
                elif segment:
                    segment.extend(floats)  # keep trailing silence as decode margin
                    silence_run += 1
                    if silence_run >= gap_chunks_needed:
                        self._finish_segment(segment)
                        segment = []
                        silence_run = 0
                # else: no transmission in progress yet -- discard silence
        finally:
            if segment:
                self._finish_segment(segment)

    def _finish_segment(self, segment):
        try:
            result = decode_samples(segment, self.sample_rate, chord_ms=self.chord_ms)
            self.events.put({"ok": True, "result": result, "ts": time.time()})
        except DecodeError as e:
            self.events.put({"ok": False, "error": str(e), "ts": time.time()})
