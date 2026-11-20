"""Tests for lc3dec.py: run with `python3 -m unittest tools/test_lc3dec.py` from the repo root.

Needs the host liblc3 (see lc3dec.py's docstring)."""
import base64, math, os, struct, subprocess, sys, tempfile, unittest, wave

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lc3dec  # noqa: E402


def sine_frames(hz, seconds, frame_bytes=40):
    """A sine at half scale, encoded on the host: a list of LC3 frames."""
    enc = lc3dec.lc3().Encoder(10000, 16000, libpath=lc3dec.LIBPATH)
    n = int(16000 * seconds)
    pcm = struct.pack('<%dh' % n, *(int(16383 * math.sin(2 * math.pi * hz * i / 16000)) for i in range(n)))
    return [enc.encode(pcm[i:i + 320], frame_bytes, bit_depth=16) for i in range(0, len(pcm), 320)]


class Lc3Dec(unittest.TestCase):
    def run_tool(self, log_text):
        d = tempfile.mkdtemp()
        log = os.path.join(d, 'serial.log')
        with open(log, 'w') as f:
            f.write(log_text)
        out = subprocess.run([sys.executable, os.path.join(HERE, 'lc3dec.py'), log, os.path.join(d, 'clip')],
                             capture_output=True, text=True, check=True).stdout
        return d, out

    def test_sine_clip_and_cut_off_clip(self):
        frames = sine_frames(440, 0.5)
        lines = ['2026-11-20T19:00:00 noise before',
                 '2026-11-20T19:00:01 LC3 BEGIN rate=16000 frame-us=10000 frame-bytes=40 frames=50']
        for i in range(0, 50, 10):
            lines.append('2026-11-20T19:00:01 ' + base64.b64encode(b''.join(frames[i:i + 10])).decode())
        lines += ['2026-11-20T19:00:01 LC3 END',
                  '2026-11-20T19:00:02 LC3 BEGIN rate=16000 frame-us=10000 frame-bytes=40 frames=10',
                  '2026-11-20T19:00:02 ' + base64.b64encode(b''.join(frames[:10])).decode()]
        d, out = self.run_tool('\n'.join(lines) + '\n')
        self.assertIn('clip 1: 0.5 s', out)
        f0 = int(out.split('f0=')[1].split()[0])
        self.assertLessEqual(abs(f0 - 440), 10)
        self.assertIn('clip 2: no LC3 END, skipped', out)
        with wave.open(os.path.join(d, 'clip-1.wav')) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getnframes()), (16000, 1, 8000))
        self.assertFalse(os.path.exists(os.path.join(d, 'clip-2.wav')))

    def test_frame_count_mismatch_and_bad_base64(self):
        frames = sine_frames(440, 0.1)
        log = ('LC3 BEGIN rate=16000 frame-us=10000 frame-bytes=40 frames=20\n'
               + base64.b64encode(b''.join(frames)).decode() + '\nLC3 END\n'
               'LC3 BEGIN rate=16000 frame-us=10000 frame-bytes=40 frames=10\n'
               '!!notbase64!!\nLC3 END\n')
        _, out = self.run_tool(log)
        self.assertIn('clip 1: 10 frames, header says 20, skipped', out)
        self.assertIn('clip 2: bad line, skipped', out)


if __name__ == '__main__':
    unittest.main()
