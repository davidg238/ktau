"""Residual-excited LPC for the board (#6): frame packing, an encoder, and an integer model of the board synth.

Usage:
  relp_codec.py encode <in-8k.wav> <out.relp> [--wav <check.wav>]   8 kHz mono 16-bit wav -> blob
  relp_codec.py tables <out.h>                                      write c/relpsynth/relp_tables.h
  relp_codec.py play <in.relp> <out.wav>                            render a blob with the integer model

Clip 2 of tools/relp_reference.py made into a format: the LPC filter of lpc_codec.py (same order, same
reflection-coefficient tables), driven by the voice's own residual instead of a pulse train. `synthesise` is the
specification of c/relpsynth/relp_synth.c: the C output must match it sample for sample
(tools/test_relp_codec.py checks this). The encoder is floating point and runs on the host only.

Blob: u16 frame count, u16 output scale (Q11 multiplier), then FRAME_BYTES per frame of HOP samples.
Frame, packed LSB first: gain (GAIN_BITS, 0 = silent), k1..k10 (lpc_codec.BITS), padding to HEAD_BYTES, then HOP
residual codes of RES_BITS each: magnitude index in the low bits, sign in the top bit (1 = negative).
Signal inside the synth is Q20 (1.0 = 1 << 20), coefficients Q15. The filter changes at the frame edge, with no
interpolation and no pre-emphasis, as in the reference clip.
"""
import os
import struct
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lpc_codec
import lpc_reference
import relp_reference

RATE = lpc_codec.RATE
ORDER = lpc_codec.ORDER
HOP = RATE * relp_reference.HOP_MS // 1000
WIN = HOP * 5 // 2                              # analysis window, centred on the hop
RES_BITS = relp_reference.BITS
GAIN_BITS = 6
HEAD_BYTES = (GAIN_BITS + sum(lpc_codec.BITS) + 7) // 8
FRAME_BYTES = HEAD_BYTES + (HOP * RES_BITS + 7) // 8
GAIN_TOP_DB, GAIN_STEP_DB = -6, 1.5             # residual RMS re full scale: top index -6 dB, index 1 -99 dB
N_GAIN = 1 << GAIN_BITS
N_LEVEL = 1 << (RES_BITS - 1)
SAT = lpc_codec.SAT

GAIN_Q20 = [0] + [int(round(10 ** ((GAIN_TOP_DB - GAIN_STEP_DB * (N_GAIN - 1 - i)) / 20) * (1 << 20)))
                  for i in range(1, N_GAIN)]
LEVEL_Q12 = [int(round(v * 4096)) for v in relp_reference.LEVELS[RES_BITS]]
KT = [lpc_codec.k_table(i) for i in range(ORDER)]


# ---- encoder (host, floating point) ----

def encode(x):
    """Samples in [-1, 1) at RATE -> frames [(gain, k1..k10 indices, [HOP residual codes])]."""
    n_frames = -(-len(x) // HOP)
    pad = np.concatenate([np.zeros(WIN), x, np.zeros(WIN + HOP)])
    w = np.hamming(WIN)
    b = np.zeros(ORDER + 1)
    levels = np.array(LEVEL_Q12) / 4096
    frames = []
    for f in range(n_frames):
        mid = WIN + f * HOP + HOP // 2
        seg = pad[mid - WIN // 2:mid - WIN // 2 + WIN] * w
        r = np.correlate(seg, seg, 'full')[WIN - 1:WIN + ORDER]
        r[0] = r[0] * 1.0001 + 1e-9
        ki = [lpc_codec.k_index(i, k) for i, k in enumerate(lpc_reference.levinson(r, ORDER)[0])]
        k = [KT[i][ki[i]] / 32768 for i in range(ORDER)]
        # The lattice inverse of the synth filter: it keeps the synth's own state, so the two stay exact inverses
        # across the change of coefficients at a frame edge.
        e = np.zeros(HOP)
        for n in range(HOP):
            v = pad[WIN + f * HOP + n]
            nb = np.empty(ORDER + 1)
            nb[0] = v
            for i in range(ORDER):
                nb[i + 1] = b[i] + k[i] * v
                v = v + k[i] * b[i]
            b = nb
            e[n] = v
        rms = np.sqrt(np.mean(e ** 2))
        db = 20 * np.log10(rms + 1e-12)
        g = int(np.clip(np.round((db - GAIN_TOP_DB) / GAIN_STEP_DB) + N_GAIN - 1, 0, N_GAIN - 1))
        if g == 0:
            codes = [0] * HOP
        else:
            mag = np.argmin(np.abs(np.abs(e)[:, None] / (GAIN_Q20[g] / (1 << 20)) - levels[None, :]), axis=1)
            codes = [int(m) | (N_LEVEL if v < 0 else 0) for m, v in zip(mag, e)]
        frames.append((g,) + tuple(ki) + (codes,))
    return frames


# ---- packing ----

def pack(frames, scale):
    out = bytearray(struct.pack('<HH', len(frames), scale))
    widths = [GAIN_BITS] + lpc_codec.BITS
    for f in frames:
        word, shift = 0, 0
        for v, wd in zip(f[:-1], widths):
            word |= v << shift
            shift += wd
        out += word.to_bytes(HEAD_BYTES, 'little')
        word = 0
        for j, c in enumerate(f[-1]):
            word |= c << (j * RES_BITS)
        out += word.to_bytes(FRAME_BYTES - HEAD_BYTES, 'little')
    return bytes(out)


def unpack(blob):
    n, scale = struct.unpack_from('<HH', blob)
    widths = [GAIN_BITS] + lpc_codec.BITS
    frames = []
    for j in range(n):
        p = 4 + j * FRAME_BYTES
        word = int.from_bytes(blob[p:p + HEAD_BYTES], 'little')
        f = []
        for wd in widths:
            f.append(word & ((1 << wd) - 1))
            word >>= wd
        word = int.from_bytes(blob[p + HEAD_BYTES:p + FRAME_BYTES], 'little')
        codes = [(word >> (i * RES_BITS)) & ((1 << RES_BITS) - 1) for i in range(HOP)]
        frames.append(tuple(f) + (codes,))
    return frames, scale


# ---- the integer synth: the specification of relp_synth.c ----

def synthesise(frames, scale=1 << 11, raw=False):
    """Frames -> int16 samples (raw: the Q20 signal before scaling). Mirrors relp_synth.c line for line."""
    sat = lpc_codec.sat
    b = [0] * (ORDER + 1)
    out = []
    for fr in frames:
        k = [KT[i][fr[1 + i]] for i in range(ORDER)]
        level = [(LEVEL_Q12[m] * GAIN_Q20[fr[0]]) >> 12 for m in range(N_LEVEL)]
        for c in fr[-1]:
            f = -level[c & (N_LEVEL - 1)] if c & N_LEVEL else level[c & (N_LEVEL - 1)]
            for i in range(ORDER - 1, -1, -1):
                f = sat(f - ((k[i] * b[i]) >> 15))
                b[i + 1] = sat(b[i] + ((k[i] * f) >> 15))
            b[0] = f
            if raw:
                out.append(f)
                continue
            s = (f * scale) >> 16
            out.append(32767 if s > 32767 else (-32768 if s < -32768 else s))
    return out


# ---- tools ----

def tables_header():
    return '\n'.join([
        '/* Generated by tools/relp_codec.py tables; do not edit. */', '#pragma once', '#include <stdint.h>', '',
        f'#define RELP_HOP {HOP}', f'#define RELP_RES_BITS {RES_BITS}', f'#define RELP_GAIN_BITS {GAIN_BITS}',
        f'#define RELP_HEAD_BYTES {HEAD_BYTES}', f'#define RELP_FRAME_BYTES {FRAME_BYTES}',
        f'#define RELP_N_LEVEL {N_LEVEL}', '',
        'static const int32_t relp_gain_q20[%d] = {%s};' % (N_GAIN, ', '.join(map(str, GAIN_Q20))),
        'static const int16_t relp_level_q12[RELP_N_LEVEL] = {%s};' % ', '.join(map(str, LEVEL_Q12))]) + '\n'


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'encode':
        x, rate = lpc_reference.read_wav(sys.argv[2])
        assert rate == RATE, f'{sys.argv[2]}: {rate} Hz, want {RATE}'
        blob = pack(encode(x), 1 << 11)
        open(sys.argv[3], 'wb').write(blob)
        print(f'{sys.argv[3]}: {len(blob)} B, {len(x) / RATE:.2f} s')
        if '--wav' in sys.argv:
            lpc_codec.write_wav(sys.argv[sys.argv.index('--wav') + 1], synthesise(*unpack(blob)))
    elif cmd == 'tables':
        open(sys.argv[2], 'w').write(tables_header())
    elif cmd == 'play':
        lpc_codec.write_wav(sys.argv[3], synthesise(*unpack(open(sys.argv[2], 'rb').read())))
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
