"""The on-board LPC speech format (#6): frame packing, dequantisation tables, and an integer model of the board synth.

Usage:
  lpc_codec.py phrase "<text>" <out.lpc> [--wav <check.wav>]   text -> Piper -> 8 kHz -> LPC phrase blob
  lpc_codec.py tables <out.h>                                  write c/lpcsynth/lpc_tables.h
  lpc_codec.py play <in.lpc> <out.wav>                         render a blob with the integer model

`synthesise` is the specification of c/lpcsynth/lpc_synth.c: same integer arithmetic, same noise generator, so the
C output must match it sample for sample (tools/test_lpc_codec.py checks this).

Blob: u16 frame count, u16 output scale (Q11 multiplier, from the phrase's peak), then FRAME_BYTES per frame.
Frame, packed LSB first: gain (5 bits, 0 = silent), pitch (6 bits, 0 = unvoiced), then k1..k10 (BITS).
Signal inside the synth is Q20 (1.0 = 1 << 20), coefficients Q15.
"""
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

RATE = 8000
ORDER = 10
HOP = 180                                       # 22.5 ms
BITS = [6, 6, 5, 5, 4, 4, 4, 4, 3, 3]           # per reflection coefficient; k1, k2 as log-area ratios
GAIN_BITS, PITCH_BITS = 5, 6
FRAME_BITS = GAIN_BITS + PITCH_BITS + sum(BITS)
FRAME_BYTES = (FRAME_BITS + 7) // 8
GAIN_TOP_DB = -18                               # gain index 31; 2 dB steps down to -78 at index 1
PITCH_LOG0 = 81                                 # pitch index i means f0 = exp((PITCH_LOG0 + i) / 20): 60 Hz up
DEEMPH_Q15 = 30720                              # 0.9375, matches the analysis pre-emphasis
SAT = (1 << 30) - 1
PIPER = os.path.expanduser('~/.local/share/piper')
VOICE = 'en_US-lessac-medium'


# ---- quantisation: analysis floats -> indices -> board values ----

def k_table(i):
    """Q15 values for coefficient i, one per index."""
    n, half = 1 << BITS[i], 1 << (BITS[i] - 1)
    if i < 2:
        lar = (np.arange(n) - half) * (8.0 / n)
        v = np.tanh(lar / 2)
    else:
        v = np.clip((np.arange(n) - half) * (2.0 / n), -0.98, 0.98)
    return [int(round(x * 32767)) for x in v]


def k_index(i, k):
    n, half = 1 << BITS[i], 1 << (BITS[i] - 1)
    if i < 2:
        lar = np.log((1 + k) / (1 - k + 1e-9) + 1e-9)
        return int(np.clip(np.round(lar / (8.0 / n)) + half, 0, n - 1))
    return int(np.clip(np.round(k / (2.0 / n)) + half, 0, n - 1))


GAIN_Q20 = [0] + [int(round(10 ** ((GAIN_TOP_DB - 2 * (31 - i)) / 20) * (1 << 20))) for i in range(1, 32)]
PERIOD = [0] + [int(round(RATE / np.exp((PITCH_LOG0 + i) / 20))) for i in range(1, 64)]
PULSE_Q8 = [int(round(np.sqrt(p) * 256)) for p in range(max(PERIOD) + 1)]   # sqrt(period): unit-energy pulse


def quantise(k, f0, gain_db):
    """One analysis frame (floats) -> index tuple (gain, pitch, k1..k10)."""
    g = 0 if gain_db < GAIN_TOP_DB - 61 else int(np.clip(np.round((gain_db - GAIN_TOP_DB) / 2) + 31, 1, 31))
    p = 0 if f0 <= 0 else int(np.clip(np.round(np.log(f0) * 20) - PITCH_LOG0, 1, 63))
    return (g, p) + tuple(k_index(i, k[i]) for i in range(ORDER))


def pack(frames, scale):
    out = bytearray(struct.pack('<HH', len(frames), scale))
    widths = [GAIN_BITS, PITCH_BITS] + BITS
    for f in frames:
        word, shift = 0, 0
        for v, w in zip(f, widths):
            word |= v << shift
            shift += w
        out += word.to_bytes(FRAME_BYTES, 'little')
    return bytes(out)


def unpack(blob):
    n, scale = struct.unpack_from('<HH', blob)
    widths = [GAIN_BITS, PITCH_BITS] + BITS
    frames = []
    for j in range(n):
        word = int.from_bytes(blob[4 + j * FRAME_BYTES:4 + (j + 1) * FRAME_BYTES], 'little')
        f = []
        for w in widths:
            f.append(word & ((1 << w) - 1))
            word >>= w
        frames.append(tuple(f))
    return frames, scale


# ---- the integer synth: the specification of lpc_synth.c ----

def cdiv(a, b):
    """C integer division (truncates toward zero)."""
    q = abs(a) // b
    return q if a >= 0 else -q


def sat(x):
    return SAT if x > SAT else (-SAT if x < -SAT else x)


def synthesise(frames, scale=1 << 11, raw=False):
    """Index frames -> int16 samples (raw: the Q20 signal before scaling). Mirrors lpc_synth.c line for line."""
    kt = [k_table(i) for i in range(ORDER)]
    b = [0] * (ORDER + 1)
    rng = 0x12345678
    pos, period, y = 0, 0, 0
    out = []
    prev = frames[0]
    for cur in frames:
        kp = [kt[i][prev[2 + i]] for i in range(ORDER)]
        kc = [kt[i][cur[2 + i]] for i in range(ORDER)]
        gp, gc = GAIN_Q20[prev[0]], GAIN_Q20[cur[0]]
        pp, pc = PERIOD[prev[1]], PERIOD[cur[1]]
        for n in range(HOP):
            k = [kp[i] + cdiv((kc[i] - kp[i]) * n, HOP) for i in range(ORDER)]
            g = gp + cdiv((gc - gp) * n, HOP)
            rng ^= (rng << 13) & 0xFFFFFFFF
            rng ^= rng >> 17
            rng ^= (rng << 5) & 0xFFFFFFFF
            r16 = (rng >> 16) - 65536 if (rng >> 16) & 0x8000 else rng >> 16
            noise = (r16 * g * 56756) >> 30                 # unit variance: sqrt(3) * 32768 = 56756
            if pc:
                if pos >= period:
                    period = pp + cdiv((pc - pp) * n, HOP) if pp else pc
                    pos = 0
                e = ((g * PULSE_Q8[period]) >> 8 if pos == 0 else 0) + ((noise * 3277) >> 16)   # + 0.05 noise
                pos += 1
            else:
                e = noise
                pos = period                                 # the next voiced sample starts a pulse
            f = e
            for i in range(ORDER - 1, -1, -1):
                f = sat(f - ((k[i] * b[i]) >> 15))
                b[i + 1] = sat(b[i] + ((k[i] * f) >> 15))
            b[0] = f
            y = sat(f + ((DEEMPH_Q15 * y) >> 15))
            if raw:
                out.append(y)
                continue
            s = (y * scale) >> 16
            out.append(32767 if s > 32767 else (-32768 if s < -32768 else s))
        prev = cur
    return out


def scale_for(frames):
    """Q11 output scale that puts the phrase's peak at 90% of full scale."""
    peak = max(abs(y) for y in synthesise(frames, raw=True)) or 1
    return int(np.clip(0.9 * 32767 * 65536 / peak, 1, 65535))


# ---- tools ----

def tables_header():
    lines = ['/* Generated by tools/lpc_codec.py tables; do not edit. */', '#pragma once', '#include <stdint.h>', '',
             f'#define LPC_RATE {RATE}', f'#define LPC_ORDER {ORDER}', f'#define LPC_HOP {HOP}',
             f'#define LPC_FRAME_BYTES {FRAME_BYTES}', f'#define LPC_DEEMPH_Q15 {DEEMPH_Q15}', '',
             'static const uint8_t lpc_bits[LPC_ORDER] = {%s};' % ', '.join(map(str, BITS)),
             f'#define LPC_GAIN_BITS {GAIN_BITS}', f'#define LPC_PITCH_BITS {PITCH_BITS}']
    for i in range(ORDER):
        lines.append('static const int16_t lpc_k%d[%d] = {%s};' % (i, 1 << BITS[i], ', '.join(map(str, k_table(i)))))
    lines.append('static const int16_t *const lpc_k[LPC_ORDER] = {%s};' % ', '.join(f'lpc_k{i}' for i in range(ORDER)))
    lines.append('static const int32_t lpc_gain_q20[32] = {%s};' % ', '.join(map(str, GAIN_Q20)))
    lines.append('static const uint8_t lpc_period[64] = {%s};' % ', '.join(map(str, PERIOD)))
    lines.append('static const uint16_t lpc_pulse_q8[%d] = {%s};' % (len(PULSE_Q8), ', '.join(map(str, PULSE_Q8))))
    return '\n'.join(lines) + '\n'


def write_wav(path, samples):
    import wave
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(struct.pack('<%dh' % len(samples), *samples))


def encode_wav(path, rule_pitch=False):
    """8 kHz mono 16-bit wav -> index frames (natural pitch unless rule_pitch)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lpc_reference
    x, rate = lpc_reference.read_wav(path)
    assert rate == RATE, f'{path}: {rate} Hz, want {RATE}'
    raw, _ = lpc_reference.analyse(x, rate, ORDER)
    if rule_pitch:
        raw = lpc_reference.rule_pitch(raw)
    return [quantise(*f) for f in raw]


def phrase(text):
    with tempfile.TemporaryDirectory() as d:
        src, w8 = os.path.join(d, 'piper.wav'), os.path.join(d, '8k.wav')
        subprocess.run([f'{PIPER}/venv/bin/piper', '-m', f'{PIPER}/voices/{VOICE}.onnx', '-f', src],
                       input=text.encode(), check=True, capture_output=True)
        subprocess.run(['sox', src, '-r', str(RATE), '-c', '1', '-b', '16', w8], check=True, capture_output=True)
        frames = encode_wav(w8)
    return pack(frames, scale_for(frames))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'phrase':
        blob = phrase(sys.argv[2])
        open(sys.argv[3], 'wb').write(blob)
        print(f'{sys.argv[3]}: {len(blob)} B, {struct.unpack_from("<H", blob)[0] * HOP / RATE:.2f} s')
        if '--wav' in sys.argv:
            write_wav(sys.argv[sys.argv.index('--wav') + 1], synthesise(*unpack(blob)))
    elif cmd == 'tables':
        open(sys.argv[2], 'w').write(tables_header())
    elif cmd == 'play':
        write_wav(sys.argv[3], synthesise(*unpack(open(sys.argv[2], 'rb').read())))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
