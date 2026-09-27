"""Onset (frame-sync) detection and chord-by-chord frame decoding."""

from . import protocol
from .goertzel import goertzel_mag, goertzel_mags

ON_RATIO = 0.4          # tone counts as ON if magnitude > ON_RATIO * bookend reference
ONSET_THRESHOLD_MULT = 6.0
COARSE_HOP_MS = 5
FINE_STEP_MS = 1
EDGE_GUARD_FRAC = 0.15  # fraction of chord skipped at each edge before Goertzel scoring


def _chord_samples(sample_rate, chord_ms):
    return int(sample_rate * chord_ms / 1000.0)


def _scoring_window(samples, start, chord_n):
    guard = int(chord_n * EDGE_GUARD_FRAC)
    a = start + guard
    b = start + chord_n - guard
    if a < 0 or b > len(samples) or a >= b:
        return None
    return samples[a:b]


def _bookend_energy(samples, sample_rate, start, chord_n):
    win = _scoring_window(samples, start, chord_n)
    if win is None:
        return 0.0
    lo = goertzel_mag(win, sample_rate, protocol.TONE_FREQS[protocol.BOOKEND_LOW])
    hi = goertzel_mag(win, sample_rate, protocol.TONE_FREQS[protocol.BOOKEND_HIGH])
    return (lo + hi) / 2.0


def _sync_score(samples, sample_rate, start, chord_n):
    win = _scoring_window(samples, start, chord_n)
    if win is None:
        return -1.0
    mags = goertzel_mags(win, sample_rate, protocol.TONE_FREQS)
    on_idx = {protocol.BOOKEND_LOW, protocol.BOOKEND_HIGH, protocol.FLAG_A}
    score = 0.0
    for i, m in enumerate(mags):
        score += m if i in on_idx else -m
    return score


class DecodeError(Exception):
    pass


def find_onset(samples, sample_rate, chord_ms=30):
    """Locate the sample index of the first preamble chord boundary."""
    chord_n = _chord_samples(sample_rate, chord_ms)
    hop = max(1, int(sample_rate * COARSE_HOP_MS / 1000.0))

    noise_probe_len = min(len(samples), int(sample_rate * 0.3))
    noise_samples = []
    idx = 0
    while idx + chord_n <= noise_probe_len:
        noise_samples.append(_bookend_energy(samples, sample_rate, idx, chord_n))
        idx += chord_n
    noise_floor = sorted(noise_samples)[len(noise_samples) // 2] if noise_samples else 0.0
    threshold = max(noise_floor * ONSET_THRESHOLD_MULT, 1e-6)

    coarse_hit = None
    idx = 0
    while idx + chord_n <= len(samples):
        e = _bookend_energy(samples, sample_rate, idx, chord_n)
        if e > threshold:
            coarse_hit = idx
            break
        idx += hop

    if coarse_hit is None:
        return None

    fine_step = max(1, int(sample_rate * FINE_STEP_MS / 1000.0))
    search_start = max(0, coarse_hit - hop)
    search_end = min(len(samples) - chord_n, coarse_hit + chord_n)

    best_offset = coarse_hit
    best_score = -1e18
    off = search_start
    while off <= search_end:
        s = _sync_score(samples, sample_rate, off, chord_n)
        if s > best_score:
            best_score = s
            best_offset = off
        off += fine_step

    return best_offset


def decode_frame(samples, sample_rate, start, chord_ms=30):
    """Step through chords from `start`, classify each, and reassemble bytes.

    Returns a dict: bytes, hex, text, corrupted (list of (byte_index, bit_positions)),
    unknown_chords (count), found_end (bool), guard_energy (max canary magnitude).
    """
    chord_n = _chord_samples(sample_rate, chord_ms)
    idx = start
    out_bytes = []
    corrupted = []
    unknown_chords = 0
    found_end = False
    guard_energy = 0.0
    guard_ref_sum = 0.0
    guard_ref_n = 0

    while idx + chord_n <= len(samples):
        win = _scoring_window(samples, idx, chord_n)
        if win is None:
            break
        mags = goertzel_mags(win, sample_rate, protocol.TONE_FREQS)
        ref = (mags[protocol.BOOKEND_LOW] + mags[protocol.BOOKEND_HIGH]) / 2.0
        if ref <= 0:
            break
        on_mask = [m > ref * ON_RATIO for m in mags]
        kind, byte_val, bad_bits = protocol.classify_chord(on_mask)

        guard_energy = max(guard_energy, mags[protocol.GUARD])
        guard_ref_sum += ref
        guard_ref_n += 1

        if kind == protocol.ChordKind.PREAMBLE:
            idx += chord_n
            continue
        if kind == protocol.ChordKind.SPACER:
            idx += chord_n
            continue
        if kind == protocol.ChordKind.END:
            found_end = True
            break
        if kind == protocol.ChordKind.DATA:
            if bad_bits:
                corrupted.append((len(out_bytes), bad_bits))
            out_bytes.append(byte_val)
            idx += chord_n
            continue

        unknown_chords += 1
        idx += chord_n

    payload = bytes(out_bytes)
    guard_ref_avg = (guard_ref_sum / guard_ref_n) if guard_ref_n else 0.0
    return {
        "bytes": payload,
        "hex": protocol.bytes_to_hex(payload),
        "text": protocol.bytes_to_text(payload),
        "corrupted": corrupted,
        "unknown_chords": unknown_chords,
        "found_end": found_end,
        "guard_energy": guard_energy,
        "guard_ref_avg": guard_ref_avg,
        "imd_warning": guard_ref_avg > 0 and guard_energy > guard_ref_avg * ON_RATIO,
    }


def decode_samples(samples, sample_rate, chord_ms=30):
    start = find_onset(samples, sample_rate, chord_ms=chord_ms)
    if start is None:
        raise DecodeError("no signal detected (preamble not found)")
    return decode_frame(samples, sample_rate, start, chord_ms=chord_ms)
