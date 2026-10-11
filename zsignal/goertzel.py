"""Pure-Python Goertzel algorithm for single-frequency magnitude detection."""

import math


def goertzel_mag(samples, sample_rate, freq):
    n = len(samples)
    if n == 0:
        return 0.0
    # Evaluate at the exact frequency rather than the nearest DFT bin: with a
    # ~1000-sample window the bins are ~48 Hz apart, and a tone halfway between
    # two (e.g. 1500 Hz) would otherwise read at ~0.6 of its true magnitude.
    omega = 2.0 * math.pi * freq / sample_rate
    cos_w = math.cos(omega)
    sin_w = math.sin(omega)
    coeff = 2.0 * cos_w

    q1 = 0.0
    q2 = 0.0
    for x in samples:
        q0 = coeff * q1 - q2 + x
        q2 = q1
        q1 = q0

    real = q1 - q2 * cos_w
    imag = q2 * sin_w
    return math.sqrt(real * real + imag * imag) / n


def goertzel_mags(samples, sample_rate, freqs):
    return [goertzel_mag(samples, sample_rate, f) for f in freqs]
