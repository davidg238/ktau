#!/usr/bin/env python3
"""Decode the LC3 clips a ktau program printed on the console and write them as WAV files.

Usage: lc3dec.py <serial-log> <out-prefix>

A clip is a line `LC3 BEGIN rate=<hz> frame-us=<us> frame-bytes=<b> frames=<k>`, base64 lines of LC3 frames back
to back, and a line `LC3 END`. Each line may carry the logger's timestamp prefix; the payload is the line's last
word. Clips are numbered in order from 1. Writes <out-prefix>-<n>.wav (mono, 16-bit) and prints one summary line
per clip, with f0, the strongest frequency between 50 and 4000 Hz.

Needs the host liblc3, built from the same source as the device's:
  cp -r ~/zephyr-4.5/modules/lib/liblc3 <scratch> && make -C <scratch>/liblc3
  cp <scratch>/liblc3/bin/liblc3.so ~/.local/lib/ktau/
(LIBLC3 overrides the library path; LC3_PY the directory holding liblc3's lc3.py.)
"""
import base64, binascii, importlib, math, os, re, struct, sys, wave

LIBPATH = os.environ.get('LIBLC3', os.path.expanduser('~/.local/lib/ktau/liblc3.so'))
LC3_PY = os.environ.get('LC3_PY', os.path.expanduser('~/zephyr-4.5/modules/lib/liblc3/python'))
BEGIN = re.compile(r'LC3 BEGIN rate=(\d+) frame-us=(\d+) frame-bytes=(\d+) frames=(\d+)')


def lc3():
    if LC3_PY not in sys.path:
        sys.path.insert(0, LC3_PY)
    return importlib.import_module('lc3')


def f0(samples, rate):
    """The strongest frequency, in 5 Hz steps (Goertzel over the first 0.25 s)."""
    xs = samples[:rate // 4]
    best, best_hz = -1.0, 0
    for hz in range(50, 4001, 5):
        w = 2 * math.pi * hz / rate
        c = 2 * math.cos(w)
        s1 = s2 = 0.0
        for x in xs:
            s1, s2 = x + c * s1 - s2, s1
        p = s1 * s1 + s2 * s2 - c * s1 * s2
        if p > best:
            best, best_hz = p, hz
    return best_hz


def summary(n, rate, pcm):
    samples = struct.unpack('<%dh' % (len(pcm) // 2), pcm)
    peak = max((abs(s) for s in samples), default=0)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
    return 'clip %d: %g s peak=%d rms=%.0f f0=%d' % (n, len(samples) / rate, peak, rms, f0(samples, rate))


def finish(n, header, data, prefix):
    rate, frame_us, frame_bytes, frames = header
    if data is None:
        return 'clip %d: bad line, skipped' % n
    if len(data) != frames * frame_bytes:
        return 'clip %d: %d frames, header says %d, skipped' % (n, len(data) // frame_bytes, frames)
    dec = lc3().Decoder(frame_us, rate, libpath=LIBPATH)
    pcm = b''.join(dec.decode(data[i:i + frame_bytes], bit_depth=16) for i in range(0, len(data), frame_bytes))
    with wave.open('%s-%d.wav' % (prefix, n), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return summary(n, rate, pcm)


def main(log_path, prefix):
    n, header, data = 0, None, None  # data: bytearray, or None after a bad line
    with open(log_path, 'rb') as f:
        lines = f.read().decode('latin1').splitlines()
    for line in lines:
        m = BEGIN.search(line)
        if m:
            if header:
                print('clip %d: no LC3 END, skipped' % n)
            n += 1
            header, data = tuple(int(g) for g in m.groups()), bytearray()
        elif header and 'LC3 END' in line:
            print(finish(n, header, data, prefix))
            header = None
        elif header and line.strip():
            try:
                if data is not None:
                    data += base64.b64decode(line.split()[-1], validate=True)
            except (binascii.Error, ValueError):
                data = None
    if header:
        print('clip %d: no LC3 END, skipped' % n)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
