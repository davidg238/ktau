"""Tests for kal_diphones.py and c/kalsynth: run with `python3 -m unittest tools/test_kal_diphones.py` from the repo root.

The plan, render and C tests use small random tables, so they need only numpy and a host C compiler (cc) with the
address sanitiser; they never need the kal table. The kal tests need Flite's shared libraries
(Debian libflite1) and are skipped without them: they check the loader by playing an utterance with Flite's own
rule from our reading of kal and comparing it with what Flite itself renders."""
import os, random, re, struct, subprocess, sys, tempfile, unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lpc_codec  # noqa: E402
import relp_codec  # noqa: E402
import kal_diphones as K  # noqa: E402

HAVE_FLITE = os.path.exists(f'{K.LIB}/libflite_cmu_us_kal.so.1')
TEXT = 'I turned on the kitchen lights, and saved your note about the shopping.'


def random_frames(n, r):
    return [(r.randrange(1, relp_codec.N_GAIN),) + tuple(r.randrange(1 << b) for b in lpc_codec.BITS)
            + ([r.randrange(1 << relp_codec.RES_BITS) for _ in range(relp_codec.HOP)],) for _ in range(n)]


def random_table(seed, phones=('aa', 'pau', 's')):
    """Every diphone over phones, 4-14 periods of 40-120 samples, the first half 1-3 periods long."""
    r = random.Random(seed)
    diphones = []
    for a in range(len(phones)):
        for b in range(len(phones)):
            per = [r.randrange(40, 121) for _ in range(r.randrange(4, 15))]
            diphones.append({'a': a, 'b': b, 'pb': r.randrange(1, 4), 'periods': per,
                             'frames': random_frames(-(-sum(per) // relp_codec.HOP), r)})
    return {'phones': list(phones), 'diphones': diphones, 'scale': 1 << 9}


def whole(table, d):
    """The plan that plays diphone d as recorded: every period whole."""
    per = table['diphones'][d]['periods']
    return [(d, sum(per[:j]), p, p) for j, p in enumerate(per)]


class Table(unittest.TestCase):
    def test_pack_round_trip(self):
        t = random_table(1)
        self.assertEqual(K.unpack(K.pack(t)), t)

    def test_render_as_recorded_is_synthesise(self):
        """Every period whole, in order: the diphone's frames through relp_codec.synthesise, sample for sample."""
        t = random_table(2)
        for d in (0, 4, 8):
            per, frames = t['diphones'][d]['periods'], t['diphones'][d]['frames']
            want = relp_codec.synthesise(frames, t['scale'])[:sum(per)]
            self.assertEqual(K.render(t, whole(t, d)), want, f'diphone {d}')

    def test_render_centres(self):
        """A longer target pads half the difference before the source period; a shorter one drops it evenly."""
        t = random_table(3)
        per = t['diphones'][0]['periods']
        rec = K.render(t, whole(t, 0)[:1], raw=True)
        longer = K.render(t, [(0, 0, per[0], per[0] + 10)], raw=True)
        self.assertEqual(longer[5:5 + per[0]][:1], [rec[0]])     # first source sample lands after 5 of padding
        self.assertEqual(longer[:5], [0] * 5)
        shorter = K.render(t, [(0, 0, per[0], per[0] - 10)], raw=True)
        self.assertEqual(len(shorter), per[0] - 10)


class Plan(unittest.TestCase):
    def setUp(self):
        self.t = random_table(4)

    def test_periods_follow_f0(self):
        pl, _ = K.plan(self.t, [('pau', 100, 100), ('aa', 200, 100), ('pau', 100, 100)])
        self.assertEqual({p[3] for p in pl}, {K.RATE // 100})

    def test_length(self):
        """Output covers every phone but the last, and the last up to its middle, to within one period."""
        phones = [('pau', 100, 90), ('s', 70, 120), ('aa', 180, 110), ('pau', 100, 80)]
        want = sum(ms for _, ms, _ in phones[:-1]) * K.RATE // 1000 + phones[-1][1] * K.RATE // 2000
        got = sum(p[3] for p in K.plan(self.t, phones)[0])
        self.assertLessEqual(abs(got - want), K.RATE // 80)

    def test_sources_stay_in_their_half(self):
        phones = [('pau', 50, 90), ('aa', 300, 140), ('s', 40, 70), ('pau', 60, 80)]
        for d, s0, slen, _ in K.plan(self.t, phones)[0]:
            per = self.t['diphones'][d]['periods']
            self.assertIn(s0, list(np.cumsum([0] + per[:-1])))
            self.assertEqual(slen, per[list(np.cumsum([0] + per)).index(s0)])

    def test_f0_interpolates(self):
        self.assertEqual([K.f0_at(t, [100, 200], [80, 120]) for t in (0, 100, 150, 199, 500)], [80, 80, 100, 119, 120])
        self.assertEqual([K.f0_at(t, [100, 200], [120, 80]) for t in (150, 199)], [100, 81])   # C truncation

    def test_missing_pair_is_substituted(self):
        """aa-s missing: played as aa, pau, s, and reported; the pause adds PAUSE_MS."""
        t = self.t
        t['diphones'] = [d for d in t['diphones'] if (t['phones'][d['a']], t['phones'][d['b']]) != ('aa', 's')]
        phones = [('pau', 100, 100), ('aa', 100, 100), ('s', 100, 100), ('pau', 100, 100)]
        pl, missing = K.plan(t, phones)
        self.assertEqual(missing, ['aa-s'])
        names = [t['phones'][t['diphones'][d]['a']] + '-' + t['phones'][t['diphones'][d]['b']] for d, *_ in pl]
        self.assertIn('aa-pau', names)
        self.assertIn('pau-s', names)
        want = (300 + K.PAUSE_MS + 50) * K.RATE // 1000
        self.assertLessEqual(abs(sum(p[3] for p in pl) - want), K.RATE // 80)
        self.assertEqual(len(K.render(t, pl)), sum(p[3] for p in pl))

    def test_missing_pair_and_its_pause(self):
        """aa-s and pau-s both missing: pau-pau stands in for pau-s."""
        t = self.t
        gone = {('aa', 's'), ('pau', 's')}
        t['diphones'] = [d for d in t['diphones'] if (t['phones'][d['a']], t['phones'][d['b']]) not in gone]
        pl, missing = K.plan(t, [('aa', 100, 100), ('s', 100, 100)])
        self.assertEqual(missing, ['aa-s'])
        self.assertIn(K.lookup(t, 'pau', 'pau'), {p[0] for p in pl})

    def test_unknown_phone(self):
        with self.assertRaises(KeyError):
            K.plan(self.t, [('pau', 50, 90), ('ng', 50, 90)])

    def test_wire_round_trip(self):
        phones = [('pau', 220, 82), ('aa', 65535, 255), ('s', 0, 1)]
        wire = K.pack_wire(self.t, phones)
        self.assertEqual(len(wire), K.WIRE_BYTES * len(phones))
        self.assertEqual(wire[4:8], bytes([self.t['phones'].index('aa'), 0xff, 0xff, 0xff]))   # u8, u16 LE, u8
        self.assertEqual(K.unpack_wire(self.t, wire), phones)


def c_table(seed):
    """A random table with the cases the C must get right: missing pairs (aa-s, s-ng and pau-ng, so pau-pau stands
    in), a diphone with an empty first half (s-aa) and one with an empty second half (aa-pau)."""
    t = random_table(seed, ('aa', 'ng', 'pau', 's'))
    name = lambda d: (t['phones'][d['a']], t['phones'][d['b']])
    t['diphones'] = [d for d in t['diphones'] if name(d) not in {('aa', 's'), ('s', 'ng'), ('pau', 'ng')}]
    for d in t['diphones']:
        if name(d) == ('s', 'aa'):
            d['pb'] = 0
        if name(d) == ('aa', 'pau'):
            d['pb'] = len(d['periods'])
    return t


PHRASES = {
    'plain': [('pau', 120, 90), ('s', 80, 110), ('aa', 200, 130), ('ng', 90, 100), ('pau', 150, 70)],
    'missing': [('pau', 50, 100), ('aa', 100, 120), ('s', 100, 80), ('ng', 60, 90), ('pau', 40, 90), ('ng', 50, 60)],
    'pitch extremes': [('pau', 30, 1), ('aa', 300, 255), ('s', 200, 1), ('aa', 100, 255), ('pau', 50, 128)],
    'short': [('pau', 0, 100), ('aa', 1, 100), ('s', 0, 200), ('aa', 2, 50), ('ng', 1, 90), ('pau', 0, 90)],
    'long': [('pau', 20, 100), ('aa', 9000, 140), ('s', 4000, 60), ('pau', 65535 // 64, 90)],
    'empty halves': [('s', 100, 100), ('aa', 100, 100), ('pau', 100, 100), ('s', 50, 100), ('aa', 30, 90)],
    'one phone': [('aa', 100, 100)],
    'none': [],
}


class CSynth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.exe = os.path.join(cls.tmp, 'host_render')
        src = os.path.join(HERE, '..', 'c')
        subprocess.run(['cc', '-O2', '-Wall', '-Werror', '-fsanitize=address', '-I', f'{src}/relpsynth',
                        '-I', f'{src}/lpcsynth', '-o', cls.exe, f'{src}/kalsynth/host_render.c',
                        f'{src}/kalsynth/kal_synth.c', f'{src}/relpsynth/relp_synth.c'], check=True)
        cls.header = open(f'{src}/kalsynth/kal_synth.h').read()

    def render_c(self, table_blob, wire):
        """C output and the substituted count, or None if init rejected the input."""
        tp, wp = os.path.join(self.tmp, 't.bin'), os.path.join(self.tmp, 'w.bin')
        open(tp, 'wb').write(table_blob)
        open(wp, 'wb').write(wire)
        r = subprocess.run([self.exe, tp, wp], capture_output=True)
        if r.returncode == 1:
            return None
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        return list(struct.unpack('<%dh' % (len(r.stdout) // 2), r.stdout)), int(r.stderr.split()[1])

    def test_constants(self):
        for name, value in (('KAL_WIRE_BYTES', K.WIRE_BYTES), ('KAL_INDEX_BYTES', K.INDEX_BYTES),
                            ('KAL_PAUSE_MS', K.PAUSE_MS)):
            self.assertEqual(int(re.search(rf'#define {name} (\d+)', self.header).group(1)), value, name)

    def test_c_equals_model(self):
        for seed in (1, 2):
            t = c_table(seed)
            blob = K.pack(t)
            t = K.unpack(blob)
            for what, phones in PHRASES.items():
                with self.subTest(seed=seed, phrase=what):
                    pl, missing = K.plan(t, phones)
                    want = K.render(t, pl)
                    got, n_missing = self.render_c(blob, K.pack_wire(t, phones))
                    self.assertEqual(n_missing, len(missing))
                    self.assertEqual(len(got), len(want))
                    first = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), None)
                    self.assertIsNone(first, f'first difference at sample {first}')
        self.assertEqual(K.plan(t, PHRASES['missing'])[1], ['aa-s', 's-ng', 'pau-ng'])

    def test_rejects(self):
        t = c_table(3)
        blob, wire = K.pack(t), K.pack_wire(t, PHRASES['plain'])
        self.assertIsNotNone(self.render_c(blob, wire))
        for n in (0, 4, 7, 20, len(blob) - 1):
            self.assertIsNone(self.render_c(blob[:n], wire), f'table cut to {n}')
        self.assertIsNone(self.render_c(blob, wire[:-1]), 'wire not whole phones')
        self.assertIsNone(self.render_c(blob, bytes([len(t['phones']), 100, 0, 100])), 'unknown phone')
        self.assertIsNone(self.render_c(blob, bytes([0, 100, 0, 0])), 'f0 of 0')
        no_pp = dict(t, diphones=[d for d in t['diphones'] if (d['a'], d['b']) != (2, 2)])
        self.assertIsNone(self.render_c(K.pack(no_pp), wire), 'no pau-pau')
        with self.assertRaises(KeyError):
            K.plan(no_pp, PHRASES['plain'])
        with self.assertRaises(ValueError):
            K.plan(t, [('aa', 100, 0)])


class Notice(unittest.TestCase):
    def test_build_output_carries_notice(self):
        with tempfile.TemporaryDirectory() as d:
            blob = K.write_table(f'{d}/v.bin', random_table(5))
            self.assertEqual(open(f'{d}/v.bin', 'rb').read(), blob)
            notice = open(f'{d}/v.COPYING').read()
        self.assertIn('modified', notice.splitlines()[0])
        self.assertTrue(notice.endswith(open(K.NOTICE).read()))
        self.assertIn('Carnegie Mellon University', notice)


@unittest.skipUnless(HAVE_FLITE, 'needs libflite1')
class Kal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kal = K.load_kal()
        cls.phones, cls.flite, (cls.segs, cls.targets) = K.flite_utt(TEXT)

    def flite_rule(self):
        """Flite's f0_targets_to_pm and concat_units (cst_units.c), in float, on our reading of kal."""
        k, times, time, lpos, lf0 = self.kal, [], 0.0, 0.0, 120.0
        for pos, f0 in self.targets:
            if time != pos:
                m = (f0 - lf0) / (pos - lpos)
                while time < pos:
                    time += 1 / (lf0 + (time - lpos) * m)
                    times.append(int(K.RATE * time))
            lf0, lpos = f0, pos
        units = []
        for (n0, e0), (n1, e1) in zip(self.segs, self.segs[1:]):
            s, pb, e = k['units'][k['names'].index(f'{n0}-{n1}')]
            e0, e1 = np.float32(e0), np.float32(e1)
            units += [(s, s + pb, int(e0 * K.RATE)), (s + pb, s + pb + e, int((e0 + e1) / 2 * K.RATE))]
        seq, pm, ts = [], 0, 0
        for us, ue, te in units:
            m, ui = sum(len(k['res'][j]) for j in range(us, ue)) / (te - ts), 0.0
            while pm < len(times) and times[pm] <= te:
                isz, best = 0, ue - 1
                for j in range(us, ue):
                    if abs(ui - isz) < abs(ui - (isz + len(k['res'][j]))):
                        best = j
                        break
                    isz += len(k['res'][j])
                size = times[pm] - (times[pm - 1] if pm else 0)
                seq.append((best, size))
                ui += size * m
                pm += 1
            ts = te
        return K.kal_play(k, seq)

    def test_loader_matches_flite(self):
        """Flite's own rule on our reading of kal sounds like Flite (fixed point there, float here)."""
        y = self.flite_rule()
        self.assertEqual(len(y), len(self.flite))
        self.assertGreater(K.snr(self.flite, y), 30)

    def test_build_one_diphone(self):
        """A table built from kal plays a diphone as recorded within the codec's usual error."""
        idx = K.kal_index(self.kal)
        d = next(i for i, dp in enumerate(idx['diphones']) if idx['phones'][dp['a']] == 'aa'
                 and idx['phones'][dp['b']] == 'n')
        dp = idx['diphones'][d]
        x = K.kal_play(self.kal, [(dp['kal0'] + j, s) for j, s in enumerate(dp['periods'])])
        dp['frames'] = relp_codec.encode(x / 32768)
        t = {'phones': idx['phones'], 'diphones': [dp], 'scale': 1 << 11}
        t = K.unpack(K.pack(t))
        y = K.render(t, whole(t, 0), raw=True)
        self.assertGreater(K.snr(x, y), 8)


if __name__ == '__main__':
    unittest.main()
