"""Tests for relp_codec.py and c/relpsynth: run with `python3 -m unittest tools/test_relp_codec.py` from the repo root.

Needs numpy and a host C compiler (cc) with the address sanitiser. No Piper: the frames are random, so every
index and the saturation path are exercised; the encoder is checked on a made-up vowel."""
import os, random, struct, subprocess, sys, tempfile, unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'c', 'relpsynth')
sys.path.insert(0, HERE)
import lpc_codec  # noqa: E402
import relp_codec as C  # noqa: E402


def random_frames(n, seed):
    r = random.Random(seed)
    return [(0 if j % 17 == 3 else r.randrange(1, C.N_GAIN),) + tuple(r.randrange(1 << b) for b in lpc_codec.BITS)
            + ([r.randrange(1 << C.RES_BITS) for _ in range(C.HOP)],) for j in range(n)]


class RelpCodec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.tmp, 'host_render')
        subprocess.run(['cc', '-O2', '-Wall', '-Werror', '-fsanitize=address', '-I', os.path.join(SRC, '..', 'lpcsynth'),
                        '-o', cls.exe, os.path.join(SRC, 'host_render.c'), os.path.join(SRC, 'relp_synth.c')],
                       check=True)

    def render_c(self, blob):
        raw = subprocess.run([self.exe], input=blob, capture_output=True, check=True).stdout
        return list(struct.unpack('<%dh' % (len(raw) // 2), raw))

    def assertSame(self, want, got, what):
        self.assertEqual(len(got), len(want), what)
        first = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), None)
        self.assertIsNone(first, f'{what}: first difference at sample {first}')

    def test_pack_round_trip(self):
        frames = random_frames(50, 1)
        self.assertEqual(C.unpack(C.pack(frames, 1234)), (frames, 1234))
        self.assertEqual(len(C.pack(frames, 1)), 4 + 50 * C.FRAME_BYTES)

    def test_c_matches_model_sample_for_sample(self):
        for seed, scale in [(2, 2048), (3, 65535), (4, 300)]:
            frames = random_frames(120, seed)
            want = C.synthesise(frames, scale)
            got = self.render_c(C.pack(frames, scale))
            self.assertEqual(len(got), 120 * C.HOP)
            self.assertSame(want, got, f'seed {seed}')
            self.assertGreater(max(map(abs, got)), 1000, 'silent output would match trivially')

    def test_c_matches_model_when_saturating(self):
        # Loudest gain, largest level, all k at their most negative index: the lattice clips.
        loud = (C.N_GAIN - 1,) + (0,) * C.ORDER + ([C.N_LEVEL - 1] * C.HOP,)
        frames = [loud] * 6 + random_frames(10, 6)
        self.assertEqual(max(map(abs, C.synthesise(frames, raw=True))), C.SAT, 'the model must reach the clip')
        self.assertSame(C.synthesise(frames, 2048), self.render_c(C.pack(frames, 2048)), 'saturating')

    def test_short_blob_rejected(self):
        blob = C.pack(random_frames(3, 5), 2048)
        self.assertNotEqual(subprocess.run([self.exe], input=blob[:-1], capture_output=True).returncode, 0)

    def test_encoder_follows_the_input(self):
        # A made-up vowel: soft 120 Hz pulses and a little noise through a resonance, with a silent gap that must
        # stay silent. (Bare one-sample pulses overload the residual quantiser, whose top level is 3 x the hop's RMS.)
        rate, n = C.RATE, C.RATE
        e = np.zeros(n); e[::rate // 120] = 1.0
        e = np.convolve(e, [0.2, 0.5, 1, 0.7, 0.4, 0.2, 0.1], 'same') + 0.1 * np.random.default_rng(1).standard_normal(n)
        x = np.zeros(n)
        for i in range(2, n):
            x[i] = e[i] + 1.6 * x[i - 1] - 0.9 * x[i - 2]
        x *= 0.5 / np.max(np.abs(x))
        x[3000:4000] = 0
        frames = C.encode(x)
        self.assertEqual(len(frames), n // C.HOP)
        y = np.array(C.synthesise(frames)) / 32768
        snr = 10 * np.log10(np.sum(x ** 2) / np.sum((x - y) ** 2))
        self.assertGreater(snr, 9, f'SNR {snr:.1f} dB')
        self.assertEqual([f[0] for f in frames[38:50]], [0] * 12, 'silence encodes as gain 0')
        self.assertEqual(np.max(np.abs(y[3300:3900])), 0)

    def test_tables_header_is_current(self):
        with open(os.path.join(SRC, 'relp_tables.h')) as f:
            self.assertEqual(f.read(), C.tables_header(), 'regenerate: tools/relp_codec.py tables c/relpsynth/relp_tables.h')


if __name__ == '__main__':
    unittest.main()
