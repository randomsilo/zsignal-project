"""zsignal chord protocol: byte <-> 21-tone chord, frame assembly/parsing.

Tone layout (see READEME.md):
  index 0        1000 Hz  bookend (always on)
  index 1-8      1100-1800 Hz  data bits 1-8 (bit1 = MSB)
  index 9-10     1900-2000 Hz  flag tones
  index 11-18    2100-2800 Hz  inverse of bits 1-8
  index 19       2900 Hz  guard band (always off; IMD canary)
  index 20       3000 Hz  bookend (always on)
"""

NUM_TONES = 21
TONE_START_HZ = 1000
TONE_STEP_HZ = 100
TONE_FREQS = [TONE_START_HZ + i * TONE_STEP_HZ for i in range(NUM_TONES)]

BOOKEND_LOW = 0
BOOKEND_HIGH = 20
BIT_INDEXES = list(range(1, 9))       # tones for bit1..bit8
INV_INDEXES = list(range(11, 19))     # tones for inverse of bit1..bit8
FLAG_A = 9
FLAG_B = 10
GUARD = 19

# Preamble uses a chord pattern that can never occur in data/spacer/end chords:
# bookends on, FLAG_A on, FLAG_B off, all data/inverse tones off.
PREAMBLE_REPS = 6


def _empty_chord():
    return [False] * NUM_TONES


def sync_chord():
    c = _empty_chord()
    c[BOOKEND_LOW] = True
    c[BOOKEND_HIGH] = True
    c[FLAG_A] = True
    return c


def data_chord(byte_val):
    if not 0 <= byte_val <= 255:
        raise ValueError("byte_val must be 0-255, got %r" % (byte_val,))
    c = _empty_chord()
    c[BOOKEND_LOW] = True
    c[BOOKEND_HIGH] = True
    for i in range(1, 9):
        bit = (byte_val >> (8 - i)) & 1
        c[i] = bool(bit)
        c[i + 10] = not bool(bit)
    return c


def spacer_chord():
    c = _empty_chord()
    c[BOOKEND_LOW] = True
    c[BOOKEND_HIGH] = True
    c[FLAG_A] = True
    c[FLAG_B] = True
    return c


def end_chord():
    c = [True] * NUM_TONES
    c[FLAG_A] = False
    c[FLAG_B] = False
    c[GUARD] = False
    return c


def build_frame_chords(payload_bytes):
    """Assemble the full chord sequence for a payload: preamble + data/spacer + end."""
    chords = [sync_chord() for _ in range(PREAMBLE_REPS)]
    n = len(payload_bytes)
    for i, b in enumerate(payload_bytes):
        chords.append(data_chord(b))
        if i < n - 1:
            chords.append(spacer_chord())
    chords.append(end_chord())
    return chords


class ChordKind:
    PREAMBLE = "preamble"
    SPACER = "spacer"
    END = "end"
    DATA = "data"
    UNKNOWN = "unknown"


def classify_chord(on_mask):
    """Classify a tone on/off mask (list of 21 bools) as preamble/spacer/end/data/unknown.

    Returns (kind, extra) where extra is the decoded byte for DATA chords
    (or None), plus a list of corrupted bit positions (1-8) for DATA chords.
    """
    flag_a, flag_b = on_mask[FLAG_A], on_mask[FLAG_B]
    data_on = [on_mask[i] for i in BIT_INDEXES]
    inv_on = [on_mask[i] for i in INV_INDEXES]

    if flag_a and not flag_b and not any(data_on) and not any(inv_on):
        return ChordKind.PREAMBLE, None, []

    if flag_a and flag_b and not any(data_on) and not any(inv_on):
        return ChordKind.SPACER, None, []

    if (not flag_a) and (not flag_b) and all(data_on) and all(inv_on):
        return ChordKind.END, None, []

    if not flag_a and not flag_b:
        byte_val = 0
        corrupted = []
        for idx, i in enumerate(range(1, 9)):
            bit_on = data_on[idx]
            inv_bit_on = inv_on[idx]
            if bit_on == inv_bit_on:
                corrupted.append(i)
                bit = 1 if bit_on else 0
            else:
                bit = 1 if bit_on else 0
            byte_val = (byte_val << 1) | bit
        return ChordKind.DATA, byte_val, corrupted

    return ChordKind.UNKNOWN, None, []


def text_to_bytes(s):
    return s.encode("utf-8")


def bytes_to_text(b):
    return b.decode("utf-8", errors="replace")


def bytes_to_hex(b):
    return b.hex() if isinstance(b, (bytes, bytearray)) else bytes(b).hex()


def hex_to_bytes(h):
    return bytes.fromhex(h)
