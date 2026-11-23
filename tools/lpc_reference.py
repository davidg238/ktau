"""Host reference for on-board LPC speech (#6): what LPC-coded speech at the device's bit rate sounds like.

Usage: lpc_reference.py <in.wav> <out.wav> [--rate 8000|16000] [--order N] [--rule-pitch]

Analyses natural speech into LPC frames (reflection coefficients, pitch, gain, voicing), quantises them roughly as
LPC-10 does, and resynthesises with a glottal-pulse / noise source through a lattice filter: the same loop a board
primitive would run. --rule-pitch replaces the measured pitch with a falling declination line, as a diphone synth
with rule prosody would produce. Join artefacts between diphones are not modelled, so this is an upper bound.
"""
import argparse
import wave

import numpy as np


def read_wav(path):
    with wave.open(path) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1, 'mono 16-bit wav expected'
        x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float64) / 32768
        return x, w.getframerate()


def write_wav(path, x, rate):
    y = np.clip(x / (np.max(np.abs(x)) + 1e-9) * 0.9, -1, 1)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((y * 32767).astype('<i2').tobytes())


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


def quantise(k, f0, gain_db):
    # LPC-10 style: k1,k2 as log-area ratios (finer near |k|=1), the rest linear with fewer bits for higher orders.
    q = k.copy()
    for i, ki in enumerate(k):
        bits = 6 if i < 2 else (5 if i < 4 else (4 if i < 8 else 3))
        if i < 2:
            lar = np.log((1 + ki) / (1 - ki + 1e-9) + 1e-9)
            step = 8.0 / (2 ** bits)
            lar = np.clip(np.round(lar / step) * step, -4, 4)
            q[i] = np.tanh(lar / 2)
        else:
            step = 2.0 / (2 ** bits)
            q[i] = np.clip(np.round(ki / step) * step, -0.98, 0.98)
    f0q = 0.0 if f0 == 0 else float(np.exp(np.round(np.log(f0) * 20) / 20))   # ~6 bits over 60-400 Hz
    gq = float(np.round(gain_db / 2) * 2)                                       # 2 dB steps, ~5 bits
    return q, f0q, gq


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
        frames.append(quantise(k, f0 if voiced else 0.0, 20 * np.log10(resid_rms + 1e-9)))
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


def glottal_pulse(n):
    """One unit-energy impulse per period of n samples: a flat excitation.

    The LPC filter is fitted to pre-emphasised speech, so it already carries the glottal spectral tilt and
    de-emphasis restores it. A shaped (Rosenberg) pulse applies that tilt a second time: 10-16 dB lost above
    1 kHz, heard as muffled (measured 2026-11-23 against the Piper source)."""
    d = np.zeros(n); d[0] = np.sqrt(n)
    return d


def synthesise(frames, hop, rate, seed=1):
    rng = np.random.default_rng(seed)
    order = len(frames[0][0])
    b = np.zeros(order + 1)                  # lattice state
    out = np.zeros(len(frames) * hop)
    phase_left = 0
    pulse, pi = np.zeros(1), 1
    prev = frames[0]
    for fi, cur in enumerate(frames):
        for n in range(hop):
            t = n / hop                      # interpolate parameters across the frame, as a board would per sample
            k = prev[0] * (1 - t) + cur[0] * t
            f0 = cur[1] if (prev[1] == 0 or cur[1] == 0) else prev[1] * (1 - t) + cur[1] * t
            g = 10 ** ((prev[2] * (1 - t) + cur[2] * t) / 20)
            if f0 > 0:
                if pi >= len(pulse):
                    pulse, pi = glottal_pulse(int(rate / f0)), 0
                e = pulse[pi] + 0.05 * rng.standard_normal(); pi += 1
            else:
                e = rng.standard_normal(); pi = len(pulse)
            f = e * g
            for i in range(order - 1, -1, -1):   # all-pole lattice
                f = f - k[i] * b[i]
                b[i + 1] = b[i] + k[i] * f
            b[0] = f
            out[fi * hop + n] = f
        prev = cur
    y = np.zeros_like(out)                   # de-emphasis
    for i in range(1, len(out)):
        y[i] = out[i] + 0.9375 * y[i - 1]
    return y


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--order', type=int, default=10)
    ap.add_argument('--rule-pitch', action='store_true')
    a = ap.parse_args()
    x, rate = read_wav(a.inp)
    frames, hop = analyse(x, rate, a.order)
    if a.rule_pitch:
        frames = rule_pitch(frames)
    write_wav(a.out, synthesise(frames, hop, rate), rate)
    bits = 6 * 2 + 5 * 2 + 4 * 4 + 3 * max(a.order - 8, 0) + 6 + 5 + 1
    print(f'{a.out}: {len(frames)} frames at {rate} Hz, order {a.order}, ~{bits} bits/frame '
          f'= {bits * rate / hop / 1000:.1f} kbit/s')


if __name__ == '__main__':
    main()
