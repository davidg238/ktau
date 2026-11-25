#!/usr/bin/env python3
"""The three canned phrases as the TTS original (16 kHz) and through LC3 at 16, 24 and 32 kbit/s (#6).

Usage: lc3_reference.py     (from the repo root; writes samples/lc3-phrases-2026-11-24/)

Writes a .wav of each to listen to, and the raw LC3 frames (10 ms, back to back) as .lc3 for c/lc3play. Needs
the host liblc3 (see lc3dec.py) and Piper.
"""
import os, subprocess, sys, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lc3dec, lpc_codec
OUT = 'samples/lc3-phrases-2026-11-24'
os.makedirs(OUT, exist_ok=True)
PHRASES = {'i-cant-reach-the-server': "I can't reach the server.", 'note-saved': 'Note saved.',
           'battery-low-please-charge-me-soon': 'Battery low, please charge me soon.'}
def write(path, pcm):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm)
for name, text in PHRASES.items():
    src = f'{OUT}/{name}-piper.wav'
    subprocess.run([f'{lpc_codec.PIPER}/venv/bin/piper', '-m', f'{lpc_codec.PIPER}/voices/{lpc_codec.VOICE}.onnx',
                    '-f', src + '.tmp.wav'], input=text.encode(), check=True, capture_output=True)
    pcm = subprocess.run(['sox', src + '.tmp.wav', '-r', '16000', '-c', '1', '-b', '16', '-t', 'raw', '-'],
                         check=True, capture_output=True).stdout
    os.remove(src + '.tmp.wav')
    import struct
    xs = struct.unpack('<%dh' % (len(pcm) // 2), pcm)
    g = 29480 / max(map(abs, xs))                 # the level the LPC phrases peak at
    pcm = struct.pack('<%dh' % len(xs), *(int(x * g) for x in xs))
    pcm += b'\0' * (-len(pcm) % 640)
    write(f'{OUT}/{name}-0-original.wav', pcm)
    secs = len(pcm) / 32000
    for kbps, nbytes in ((16, 20), (24, 30), (32, 40)):
        enc = lc3dec.lc3().Encoder(10000, 16000, libpath=lc3dec.LIBPATH)
        dec = lc3dec.lc3().Decoder(10000, 16000, libpath=lc3dec.LIBPATH)
        frames = [enc.encode(pcm[i:i + 320], nbytes, bit_depth=16) for i in range(0, len(pcm), 320)]
        write(f'{OUT}/{name}-lc3-{kbps}k.wav', b''.join(dec.decode(f, bit_depth=16) for f in frames))
        open(f'{OUT}/{name}-{kbps}k.lc3', 'wb').write(b''.join(frames))
        print(f'{name}: {secs:.2f} s, LC3 {kbps} kbit/s = {sum(map(len, frames))} B')
