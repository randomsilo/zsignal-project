"""Pure-Python Goertzel algorithm for single-frequency magnitude detection."""

import math


def goertzel_mag(samples, sample_rate, freq):
    n = len(samples)
    if n == 0:
        return 0.0
    k = int(0.5 + (n * freq) / sample_rate)
    omega = (2.0 * math.pi * k) / n
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
