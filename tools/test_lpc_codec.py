"""Tests for lpc_codec.py and c/lpcsynth: run with `python3 -m unittest tools/test_lpc_codec.py` from the repo root.

Needs numpy and a host C compiler (cc). No Piper: the frames are random, so every index, voicing change and
saturation path is exercised."""
import os, random, struct, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'c', 'lpcsynth')
sys.path.insert(0, HERE)
import lpc_codec as C  # noqa: E402


def random_frames(n, seed):
    r = random.Random(seed)
    frames = []
    for j in range(n):
        g = 0 if j % 17 == 3 else r.randrange(1, 32)
        p = 0 if (j // 5) % 3 == 0 else r.randrange(1, 64)
        frames.append((g, p) + tuple(r.randrange(1 << b) for b in C.BITS))
    return frames


class LpcCodec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.tmp, 'host_render')
        subprocess.run(['cc', '-O2', '-Wall', '-Werror', '-o', cls.exe, os.path.join(SRC, 'host_render.c'),
                        os.path.join(SRC, 'lpc_synth.c')], check=True)

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
        # Loudest gain, all k at their most negative index: the lattice clips (~2,300 times in the model).
        frames = [(31, 1, 0, 0) + (0,) * (C.ORDER - 2)] * 6 + random_frames(10, 6)
        self.assertSame(C.synthesise(frames, 2048), self.render_c(C.pack(frames, 2048)), 'saturating')

    def test_short_blob_rejected(self):
        blob = C.pack(random_frames(3, 5), 2048)
        self.assertNotEqual(subprocess.run([self.exe], input=blob[:-1], capture_output=True).returncode, 0)

    def test_tables_header_is_current(self):
        with open(os.path.join(SRC, 'lpc_tables.h')) as f:
            self.assertEqual(f.read(), C.tables_header(), 'regenerate: tools/lpc_codec.py tables c/lpcsynth/lpc_tables.h')


if __name__ == '__main__':
    unittest.main()
