"""Host reference for on-board LPC speech (#6): what LPC-coded speech at the device's bit rate sounds like.

Usage: lpc_reference.py <in.wav> <out.wav> [--rule-pitch]     (in.wav: 8 kHz mono 16-bit)

Analyses natural speech into LPC frames (reflection coefficients, pitch, gain, voicing). lpc_codec.py quantises
them and resynthesises with its integer model of the board synth. --rule-pitch replaces the measured pitch with a
falling declination line, as a diphone synth with rule prosody would produce. Join artefacts between diphones are
not modelled, so this is an upper bound.
"""
import argparse
import wave

import numpy as np


def read_wav(path):
    with wave.open(path) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1, 'mono 16-bit wav expected'
        x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float64) / 32768
        return x, w.getframerate()


def levinson(r, order):
    """Autocorrelation -> reflection coefficients k[1..order] and prediction error."""
    a = np.zeros(order + 1); a[0] = 1.0
    k = np.zeros(order)
    err = r[0] + 1e-12
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        ki = -acc / err
        a[1:i] = a[1:i] + ki * a[i - 1:0:-1]
        a[i] = ki
        k[i - 1] = ki
        err *= (1 - ki * ki)
    return k, a, err


def pitch_of(seg, rate):
    """Autocorrelation pitch on a centre-clipped, low-passed segment: (f0 or 0, strength)."""
    lo, hi = int(rate / 400), int(rate / 60)
    c = 0.3 * np.max(np.abs(seg))
    s = np.where(seg > c, seg - c, np.where(seg < -c, seg + c, 0.0))
    r = np.correlate(s, s, 'full')[len(s) - 1:]
    if r[0] <= 0 or hi >= len(r):
        return 0.0, 0.0
    lag = lo + int(np.argmax(r[lo:hi]))
    return rate / lag, r[lag] / r[0]


def analyse(x, rate, order, frame_ms=22.5):
    hop = int(rate * frame_ms / 1000)
    win = int(hop * 1.33)
    pre = np.append(x[0], x[1:] - 0.9375 * x[:-1])
    w = np.hamming(win)
    frames = []
    for start in range(0, len(x) - win, hop):
        seg = pre[start:start + win] * w
        r = np.correlate(seg, seg, 'full')[win - 1:win + order]
        r[0] *= 1.0001                                   # white-noise correction keeps the filter stable
        k, a, err = levinson(r, order)
        resid_rms = np.sqrt(max(err, 1e-12) / win)
        f0, strength = pitch_of(x[start:start + win], rate)
        energy = np.sqrt(np.mean(x[start:start + win] ** 2))
        zcr = np.mean(np.abs(np.diff(np.sign(x[start:start + win])))) / 2
        voiced = strength > 0.35 and energy > 0.01 and zcr < 0.25
        frames.append((k, f0 if voiced else 0.0, 20 * np.log10(resid_rms + 1e-9)))
    return frames, hop


def rule_pitch(frames, top=210.0, bottom=150.0):
    """Replace measured pitch with declination per breath group (voiced runs split by >= 200 ms of silence)."""
    voiced = [f0 > 0 for _, f0, _ in frames]
    groups, start, gap = [], None, 0
    for i, v in enumerate(voiced + [False] * 10):
        if v:
            start = i if start is None else start; gap = 0
        elif start is not None:
            gap += 1
            if gap >= 9:
                groups.append((start, i - gap)); start = None
    out = list(frames)
    for s, e in groups:
        n = max(e - s, 1)
        for i in range(s, e + 1):
            if out[i][1] > 0:
                t = (i - s) / n
                f = top - (top - bottom) * t - (25 if t > 0.85 else 0)   # declination, then a final fall
                out[i] = (out[i][0], f, out[i][2])
    return out


def main():
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import lpc_codec
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--rule-pitch', action='store_true')
    a = ap.parse_args()
    frames = lpc_codec.encode_wav(a.inp, a.rule_pitch)
    lpc_codec.write_wav(a.out, lpc_codec.synthesise(frames, lpc_codec.scale_for(frames)))
    bits = lpc_codec.FRAME_BITS
    print(f'{a.out}: {len(frames)} frames, {bits} bits/frame = {bits * lpc_codec.RATE / lpc_codec.HOP / 1000:.1f} kbit/s')


if __name__ == '__main__':
    main()
