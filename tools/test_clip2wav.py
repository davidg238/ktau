"""Tests for clip2wav.py: run with `python3 -m unittest tools/test_clip2wav.py` from the repo root."""
import base64, os, struct, subprocess, sys, tempfile, unittest, wave

HERE = os.path.dirname(os.path.abspath(__file__))


def block(samples):
    return base64.b64encode(struct.pack('<%dh' % len(samples), *samples)).decode()


class Clip2Wav(unittest.TestCase):
    def run_tool(self, log_text):
        d = tempfile.mkdtemp()
        log = os.path.join(d, 'serial.log')
        with open(log, 'w') as f:
            f.write(log_text)
        out = subprocess.run([sys.executable, os.path.join(HERE, 'clip2wav.py'), log, os.path.join(d, 'clip')],
                             capture_output=True, text=True, check=True).stdout
        return d, out

    def test_complete_clip_and_cut_off_clip(self):
        log = ('2026-11-19T21:00:00 noise before\n'
               '2026-11-19T21:00:01 CLIP BEGIN n=1 rate=16000\n'
               '2026-11-19T21:00:01 ' + block([0, 1000, -2000, 3]) + '\n'
               '2026-11-19T21:00:01 ' + block([4, -5, 6, 7]) + '\n'
               '2026-11-19T21:00:01 CLIP END\n'
               '2026-11-19T21:00:02 CLIP BEGIN n=2 rate=16000\n'
               '2026-11-19T21:00:02 ' + block([1, 2]) + '\n')
        d, out = self.run_tool(log)
        self.assertIn('clip 1: 0.0005 s peak=2000 rms=', out)
        self.assertIn('clip 2: no CLIP END, skipped', out)
        with wave.open(os.path.join(d, 'clip-1.wav')) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, 16000, 8))
        self.assertFalse(os.path.exists(os.path.join(d, 'clip-2.wav')))

    def test_bad_line_skips_the_clip(self):
        d, out = self.run_tool('CLIP BEGIN n=3 rate=16000\nnot*base64!\nCLIP END\n')
        self.assertIn('clip 3: bad line, skipped', out)
        self.assertFalse(os.path.exists(os.path.join(d, 'clip-3.wav')))


if __name__ == '__main__':
    unittest.main()
