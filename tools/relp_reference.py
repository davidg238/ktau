#!/usr/bin/env python3
"""What would residual-excited LPC sound like? A listening test on the host (#6).

Usage: relp_reference.py "<text>" <out-dir>

Plain LPC drives its filter with a click train or noise, which is what sounds robotic. Residual-excited LPC keeps
the filter and stores what the filter could not predict (the residual) from the real voice, coarsely quantised,
and plays that through the filter instead. Writes 16 kHz mono clips, each peaking at the same level:

  1-lpc-8k.wav          plain LPC as c/lpcsynth plays it (8 kHz, order 10), the baseline
  2-relp-8k.wav         residual-excited, 8 kHz order 10, residual at BITS bits a sample
  3-relp-16k.wav        residual-excited, 16 kHz order 16, the same
  4-relp-16k-moved.wav  clip 3 with pitch raised and speech slowed, by overlap-adding the residual one pitch
                        period at a time: what a diphone synth must do to every piece it plays

and the same as raw s16le .pcm for c/pcmplay. Prints the stored size of each. Piper makes the source voice.
"""
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lpc_codec
import lpc_reference as ref

OUT_RATE = 16000
HOP_MS = 10
BITS = 3
PEAK = 29480                 # the level the canned LPC phrases peak at
PITCH, STRETCH = 1.15, 1.2   # clip 4: 15% higher, 20% slower
# Reconstruction levels for a unit-variance Laplacian source (Lloyd-Max), positive half.
LEVELS = {2: [0.42, 1.83], 3: [0.22, 0.81, 1.57, 2.99]}


def lpc_frames(x, rate, order):
    """One predictor a[0..order] (a[0] = 1) per HOP_MS hop, from a window centred on the hop."""
    hop = rate * HOP_MS // 1000
    win = hop * 5 // 2
    pad = np.concatenate([np.zeros(win), x, np.zeros(win)])
    w = np.hamming(win)
    out = []
    for f in range(-(-len(x) // hop)):
        mid = win + f * hop + hop // 2
        seg = pad[mid - win // 2:mid - win // 2 + win] * w
        r = np.correlate(seg, seg, 'full')[win - 1:win + order]
        r[0] = r[0] * 1.0001 + 1e-9
        out.append(ref.levinson(r, order)[1])
    return out, hop


def residual(x, a, hop):
    order = len(a[0]) - 1
    xp = np.concatenate([np.zeros(order), x])
    return np.array([np.dot(a[n // hop], xp[n + order::-1][:order + 1]) for n in range(len(x))])


def synth(e, a_at):
    """All-pole filter; a_at(n) gives the predictor for output sample n."""
    order = len(a_at(0)) - 1
    y = np.zeros(len(e) + order)
    for n in range(len(e)):
        y[n + order] = e[n] - np.dot(a_at(n)[1:], y[n + order - 1::-1][:order])
    return y[order:]


def quantise(e, hop, bits):
    """A gain per hop and `bits` bits a sample. Returns the decoded residual."""
    levels = np.array(LEVELS[bits])
    out = np.zeros_like(e)
    for s in range(0, len(e), hop):
        seg = e[s:s + hop]
        gain = np.sqrt(np.mean(seg ** 2)) + 1e-9
        idx = np.argmin(np.abs(np.abs(seg[:, None]) / gain - levels[None, :]), axis=1)
        out[s:s + hop] = np.sign(seg) * levels[idx] * gain
    return out


def pitch_marks(x, e, rate, hop):
    """One mark per pitch period where the speech is voiced, every 5 ms where it is not:
    [(position, period, voiced)]."""
    win = 4 * hop
    periods = []
    for s in range(0, len(x), hop):
        seg = x[max(0, s - win // 2):s + win // 2 + hop]
        f0, strength = ref.pitch_of(seg, rate) if len(seg) > rate // 60 + 1 else (0.0, 0.0)
        voiced = strength > 0.35 and np.sqrt(np.mean(seg ** 2)) > 0.01
        periods.append(int(rate / f0) if voiced else 0)
    env = np.convolve(np.abs(e), np.ones(5) / 5, 'same')
    marks, pos = [], 0
    while pos < len(e):
        t = periods[min(pos // hop, len(periods) - 1)]
        if t == 0:
            marks.append((pos, rate // 200, False))
            pos += rate // 200
            continue
        lo, hi = max(0, pos - t // 5), min(len(e), pos + t // 5 + 1)
        if not marks or not marks[-1][2]:      # entering a voiced stretch: find the first pulse
            hi = min(len(e), pos + t)
        pos = lo + int(np.argmax(env[lo:hi]))
        marks.append((pos, t, True))
        pos += t
    return marks


def moved(e, marks, a, hop, pitch, stretch):
    """The residual with new pitch and duration (overlap-add of two-period grains), through the filter."""
    n_out = int(len(e) * stretch)
    out, wsum = np.zeros(n_out), np.zeros(n_out)
    positions = np.array([m[0] for m in marks])
    t_out = 0.0
    while t_out < n_out:
        pos, period, voiced = marks[int(np.argmin(np.abs(positions - t_out / stretch)))]
        lo, hi = max(0, pos - period), min(len(e), pos + period)
        w = np.hanning(2 * period + 1)[lo - (pos - period):hi - (pos - period)]
        grain = e[lo:hi] * w
        at = int(t_out) - (pos - lo)
        s, t = max(0, at), min(n_out, at + len(grain))
        out[s:t] += grain[s - at:t - at]
        wsum[s:t] += w[s - at:t - at]
        t_out += period / pitch if voiced else period
    out /= np.maximum(wsum, 0.5)
    return synth(out, lambda n: a[min(int(n / stretch) // hop, len(a) - 1)])


def to_out_rate(y, rate):
    if rate == OUT_RATE:
        return y
    with tempfile.TemporaryDirectory() as d:
        write_wav(f'{d}/a.wav', y, rate)
        subprocess.run(['sox', f'{d}/a.wav', '-r', str(OUT_RATE), f'{d}/b.wav'], check=True, capture_output=True)
        return ref.read_wav(f'{d}/b.wav')[0]


def write_wav(path, y, rate, peak=None):
    y = y * (peak / 32768 / np.max(np.abs(y))) if peak else y
    pcm = np.clip(np.round(y * 32768), -32768, 32767).astype('<i2').tobytes()
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return pcm


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    text, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([f'{lpc_codec.PIPER}/venv/bin/piper', '-m', f'{lpc_codec.PIPER}/voices/{lpc_codec.VOICE}.onnx',
                        '-f', f'{d}/src.wav'], input=text.encode(), check=True, capture_output=True)
        src = {}
        for rate in (8000, 16000):
            subprocess.run(['sox', f'{d}/src.wav', '-r', str(rate), '-c', '1', '-b', '16', f'{d}/{rate}.wav'],
                           check=True, capture_output=True)
            src[rate] = ref.read_wav(f'{d}/{rate}.wav')[0]
        frames = lpc_codec.encode_wav(f'{d}/8000.wav')
    blob = lpc_codec.pack(frames, lpc_codec.scale_for(frames))
    clips = [('1-lpc-8k', np.array(lpc_codec.synthesise(*lpc_codec.unpack(blob)), dtype=float) / 32768, 8000,
              f'{len(blob)} B')]
    for rate, order, name in ((8000, 10, '2-relp-8k'), (16000, 16, '3-relp-16k')):
        x = src[rate]
        a, hop = lpc_frames(x, rate, order)
        e = quantise(residual(x, a, hop), hop, BITS)
        y = synth(e, lambda n: a[n // hop])
        secs = len(x) / rate
        size = len(a) * lpc_codec.FRAME_BYTES + len(x) * BITS // 8
        clips.append((name, y, rate, f'about {size} B ({size / secs / 1000:.1f} KB a second)'))
    marks = pitch_marks(x, e, rate, hop)
    clips.append(('4-relp-16k-moved', moved(e, marks, a, hop, PITCH, STRETCH), rate,
                  f'same data as clip 3, pitch x{PITCH}, duration x{STRETCH}'))
    for name, y, rate, note in clips:
        pcm = write_wav(f'{out}/{name}.wav', to_out_rate(y, rate), OUT_RATE, PEAK)
        open(f'{out}/{name}.pcm', 'wb').write(pcm)
        print(f'{name}: {len(pcm) / 2 / OUT_RATE:.2f} s, {note}')


if __name__ == '__main__':
    main()
