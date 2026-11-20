#!/usr/bin/env python3
"""Extract the audio clips a ktau program printed on the console and write them as WAV files.

Usage: clip2wav.py <serial-log> <out-prefix>

A clip is a line `CLIP BEGIN n=<k> rate=<hz>`, one base64 line per block of little-endian
int16 mono samples, and a line `CLIP END`. Each line may carry the logger's timestamp prefix;
the payload is the line's last word. Writes <out-prefix>-<k>.wav and prints one summary line per clip.
"""
import base64, binascii, math, re, struct, sys, wave

BEGIN = re.compile(r'CLIP BEGIN n=(\d+) rate=(\d+)')


def summary(n, rate, pcm):
    samples = struct.unpack('<%dh' % (len(pcm) // 2), pcm)
    peak = max((abs(s) for s in samples), default=0)
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0.0
    return 'clip %s: %g s peak=%d rms=%.0f' % (n, len(samples) / rate, peak, rms)


def main(log_path, prefix):
    clip = None  # [n, rate, bytearray, ok]
    with open(log_path, 'rb') as f:
        lines = f.read().decode('latin1').splitlines()
    for line in lines:
        m = BEGIN.search(line)
        if m:
            if clip:
                print('clip %s: no CLIP END, skipped' % clip[0])
            clip = [m.group(1), int(m.group(2)), bytearray(), True]
        elif clip and 'CLIP END' in line:
            n, rate, pcm, ok = clip
            if ok:
                with wave.open('%s-%s.wav' % (prefix, n), 'wb') as w:
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(bytes(pcm))
                print(summary(n, rate, pcm))
            else:
                print('clip %s: bad line, skipped' % n)
            clip = None
        elif clip and line.strip():
            try:
                clip[2] += base64.b64decode(line.split()[-1], validate=True)
            except (binascii.Error, ValueError):
                clip[3] = False
    if clip:
        print('clip %s: no CLIP END, skipped' % clip[0])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
