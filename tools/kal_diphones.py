"""A diphone voice for the board (#6): CMU kal's diphones in the residual-excited format of relp_codec.py.

Usage:
  kal_diphones.py build <out.kal>                         kal (from the installed Flite) -> diphone table, and
                                                          its notice beside it (<out>.COPYING)
  kal_diphones.py say <in.kal> <out.wav> <ph dur f0>...   phones -> wire bytes -> the integer model (8 kHz wav)
  kal_diphones.py wire <in.kal> <in.wire> <out.wav>       render wire bytes as the server sends them
  kal_diphones.py flite "<text>" <out-dir> <in.kal>      Flite's phones for <text>; Flite's own rendering, kal's
                                                          data played by our plan, and our table by our plan,
                                                          as 16 kHz wav + s16le pcm for c/pcmplay

Source: the CMU kal diphone database as shipped in Flite (Debian libflite1). Licence and authors:
licenses/flite-copyright (a copy of /usr/share/doc/libflite1/copyright); `build` writes it beside every table.
Modified from Flite: this tool reads kal's data and ports Flite's diphone_synth rule (cst_diphone.c,
cst_units.c) to integers, with its own codec and a substitution for missing diphones. kal stores one LPC frame
and one g721-coded residual per pitch period, 8 kHz order 10. `build` plays each diphone through Flite's own
filter as recorded (no pitch or duration change) and re-encodes that waveform with relp_codec.encode, so the
board needs one synth and one format. It keeps kal's pitch periods (one byte each) as the pitch marks.

Wire, WIRE_BYTES per phone, little endian: u8 phone (index into the table's phone list), u16 duration in ms,
u8 f0 in Hz at the phone's midpoint (linear between midpoints, held before the first and after the last).
The rule, as Flite's diphone_synth: diphone a-b plays its first half over the end of a and its second half over the
first half of b; target periods of RATE // f0 samples each take the source period nearest the proportional
position in that half, centred, truncated or zero-padded. A pair the table lacks, a-b, plays as a, a pause of
PAUSE_MS, b (with a's f0); if a-pau or pau-b is lacking too, pau-pau stands in for it.

`plan` and `render` are the specification of a later C synth and are integer-only. `render` of a plan that plays
every source period whole equals relp_codec.synthesise of the diphone's frames (tools/test_kal_diphones.py).

Table, little endian: u16 diphone count, u16 output scale (Q11, as relp_codec), u8 phone count, the phone names
NUL-separated, then per diphone (INDEX_BYTES) u8 phone a, u8 phone b, u16 first frame, u16 first period,
u8 periods in the first half, u8 in the second; then one u8 per period (samples); then FRAME_BYTES per frame. A
diphone's frame count is ceil(its samples / HOP).
"""
import ctypes
import os
import struct
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lpc_codec
import relp_codec
import relp_reference

RATE = relp_codec.RATE
HOP = relp_codec.HOP
INDEX_BYTES = 8
WIRE_BYTES = 4
PAUSE_MS = 20                       # the pause for a missing pair: Flite's shortest phone in the test sentence (dh, 21 ms)
NOTICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'licenses', 'flite-copyright')
G721_LEADIN = 8                     # CST_G721_LEADIN in Flite's cst_wave.h
LIB = '/usr/lib/x86_64-linux-gnu'
PEAK = relp_reference.PEAK


# ---- kal, read from the installed Flite ----

class _Entry(ctypes.Structure):
    _fields_ = [('name', ctypes.c_char_p), ('start', ctypes.c_ushort), ('pb', ctypes.c_ubyte), ('end', ctypes.c_ubyte)]


class _Db(ctypes.Structure):
    _fields_ = [('name', ctypes.c_char_p), ('n', ctypes.c_int), ('diphones', ctypes.POINTER(_Entry)),
                ('sts', ctypes.c_void_p)]


class _Sts(ctypes.Structure):
    _fields_ = [('sts', ctypes.c_void_p), ('frames', ctypes.c_void_p), ('lpc', ctypes.POINTER(ctypes.c_ushort)),
                ('res', ctypes.POINTER(ctypes.c_ubyte)), ('resi', ctypes.POINTER(ctypes.c_uint)),
                ('ressize', ctypes.POINTER(ctypes.c_ubyte)), ('num_sts', ctypes.c_int), ('channels', ctypes.c_int),
                ('rate', ctypes.c_int), ('coeff_min', ctypes.c_float), ('coeff_range', ctypes.c_float),
                ('codec', ctypes.c_char_p)]


def flite_libs():
    flite = ctypes.CDLL(f'{LIB}/libflite.so.1', mode=ctypes.RTLD_GLOBAL)
    for dep in ('libflite_cmulex.so.1', 'libflite_usenglish.so.1'):
        ctypes.CDLL(f'{LIB}/{dep}', mode=ctypes.RTLD_GLOBAL)
    return flite, ctypes.CDLL(f'{LIB}/libflite_cmu_us_kal.so.1', mode=ctypes.RTLD_GLOBAL)


def load_kal():
    """kal as numpy: {'names', 'units' [(start, pb, end)], 'lpc' (n, 10) float, 'res' [float array per period]}."""
    flite, kal = flite_libs()
    db = _Db.in_dll(kal, 'cmu_us_kal_db')
    sts = ctypes.cast(db.sts, ctypes.POINTER(_Sts)).contents
    assert sts.codec == b'g721' and sts.rate == RATE and sts.channels == lpc_codec.ORDER
    names = [db.diphones[i].name.decode() for i in range(db.n)]
    units = [(db.diphones[i].start, db.diphones[i].pb, db.diphones[i].end) for i in range(db.n)]
    n = sts.num_sts
    raw = np.ctypeslib.as_array(sts.lpc, (n * sts.channels,)).reshape(n, sts.channels).astype(float)
    lpc = raw / 65535.0 * sts.coeff_range + sts.coeff_min          # as Flite's lpc_resynth
    flite.cst_ulaw_to_short.restype = ctypes.c_short
    ulaw = np.array([flite.cst_ulaw_to_short(ctypes.c_ubyte(u)) for u in range(256)], dtype=float)
    flite.cst_g721_decode.restype = ctypes.POINTER(ctypes.c_ubyte)
    libc = ctypes.CDLL(None)
    res, got = [], ctypes.c_int()
    base = ctypes.addressof(sts.res.contents)
    for i in range(n):
        size = sts.ressize[i]
        p = flite.cst_g721_decode(ctypes.byref(got), (size + G721_LEADIN + 1) // 2,
                                  ctypes.c_void_p(base + sts.resi[i]))
        res.append(ulaw[np.ctypeslib.as_array(p, (got.value,))[G721_LEADIN:G721_LEADIN + size]])
        libc.free(p)
    stored = sts.resi[n - 1] + (sts.ressize[n - 1] + G721_LEADIN + 1) // 2 + n * sts.channels * 2
    return {'names': names, 'units': units, 'lpc': lpc, 'res': res, 'stored': stored}


def kal_play(kal, periods):
    """Flite's lpc_resynth (float): [(kal period, target length)] -> samples, each residual centred as add_residual."""
    out, past = [], np.zeros(lpc_codec.ORDER)
    for j, size in periods:
        e = kal['res'][j]
        r = np.zeros(size)
        if len(e) < size:
            r[(size - len(e)) // 2:(size - len(e)) // 2 + len(e)] = e
        else:
            r[:] = e[(len(e) - size) // 2:(len(e) - size) // 2 + size]
        a = kal['lpc'][j]
        for v in r:
            v = v + np.dot(a, past)
            past = np.concatenate([[v], past[:-1]])
            out.append(v)
    return np.array(out)


# ---- the table ----

def split(name):
    a, b = name.split('-')
    return a, b


def kal_index(kal):
    """The table's diphones without frames, each with 'kal0', its first kal period. Cluster diphones (Flite's
    'b_-_l', chosen from syllable structure the wire does not carry) are left out."""
    plain = [(i, n) for i, n in enumerate(kal['names']) if '_' not in n]
    phones = sorted({p for _, n in plain for p in split(n)})
    diphones = []
    for i, name in plain:
        start, pb, end = kal['units'][i]
        a, b = split(name)
        diphones.append({'a': phones.index(a), 'b': phones.index(b), 'pb': pb, 'kal0': start,
                         'periods': [len(kal['res'][j]) for j in range(start, start + pb + end)]})
    return {'phones': phones, 'diphones': diphones}


def kal_periods(kal, table, periods):
    """A plan of the table played from kal's own data instead: [(kal period, target length)] for kal_play."""
    out = []
    for d, s0, _, tlen in periods:
        dp = table['diphones'][d]
        out.append((dp['kal0'] + list(np.cumsum([0] + dp['periods'])).index(s0), tlen))
    return out


def build(kal):
    """kal -> table: each diphone played as recorded through Flite's filter, then relp_codec.encode."""
    table = kal_index(kal)
    for d in table['diphones']:
        x = kal_play(kal, [(d['kal0'] + j, s) for j, s in enumerate(d['periods'])]) / 32768
        d['frames'] = relp_codec.encode(x)
    peak = max(max(abs(v) for v in relp_codec.synthesise(d['frames'], raw=True)) for d in table['diphones'])
    table['scale'] = min(0xffff, (PEAK << 16) // max(1, peak))
    return table


def pack(table):
    out = bytearray(struct.pack('<HHB', len(table['diphones']), table['scale'], len(table['phones'])))
    out += b'\0'.join(p.encode() for p in table['phones']) + b'\0'
    frame0 = period0 = 0
    for d in table['diphones']:
        out += struct.pack('<BBHHBB', d['a'], d['b'], frame0, period0, d['pb'], len(d['periods']) - d['pb'])
        frame0 += len(d['frames'])
        period0 += len(d['periods'])
    for d in table['diphones']:
        out += bytes(d['periods'])
    for d in table['diphones']:
        out += relp_codec.pack(d['frames'], 0)[4:]
    return bytes(out)


def write_table(path, table):
    """The table and, beside it as <path without extension>.COPYING, CMU's notice, marked as modified."""
    blob = pack(table)
    open(path, 'wb').write(blob)
    notice = (f'{os.path.basename(path)} is derived from the CMU kal diphone database as shipped in Flite, modified:\n'
              'each diphone re-encoded by tools/kal_diphones.py into the residual-excited format of\n'
              'tools/relp_codec.py. The licence and authors of the original follow.\n\n')
    open(os.path.splitext(path)[0] + '.COPYING', 'w').write(notice + open(NOTICE).read())
    return blob


def unpack(blob):
    n, scale, n_ph = struct.unpack_from('<HHB', blob)
    p = 5
    phones = []
    for _ in range(n_ph):
        e = blob.index(b'\0', p)
        phones.append(blob[p:e].decode())
        p = e + 1
    index = [struct.unpack_from('<BBHHBB', blob, p + i * INDEX_BYTES) for i in range(n)]
    p += n * INDEX_BYTES
    n_periods = sum(h1 + h2 for *_, h1, h2 in index)
    periods = list(blob[p:p + n_periods])
    p += n_periods
    diphones = []
    for a, b, f0, q0, h1, h2 in index:
        per = periods[q0:q0 + h1 + h2]
        nf = -(-sum(per) // HOP)
        frames, _ = relp_codec.unpack(struct.pack('<HH', nf, 0) +
                                      blob[p + f0 * relp_codec.FRAME_BYTES:p + (f0 + nf) * relp_codec.FRAME_BYTES])
        diphones.append({'a': a, 'b': b, 'periods': per, 'pb': h1, 'frames': frames})
    return {'phones': phones, 'diphones': diphones, 'scale': scale}


# ---- the integer model: plan (prosody -> periods) and render (periods -> samples) ----

def lookup(table, a, b):
    """Index of diphone a-b, or None if the table lacks it."""
    ph = table['phones']
    for i, d in enumerate(table['diphones']):
        if ph[d['a']] == a and ph[d['b']] == b:
            return i
    return None


def pack_wire(table, phones):
    """[(phone, dur_ms, f0_hz)] -> the bytes the server sends."""
    return b''.join(struct.pack('<BHB', table['phones'].index(p), ms, hz) for p, ms, hz in phones)


def unpack_wire(table, blob):
    return [(table['phones'][i], ms, hz) for i, ms, hz in struct.iter_unpack('<BHB', blob)]


def f0_at(t, mids, f0s):
    """f0 at sample t: linear between phone midpoints, held outside them. Integer, C division."""
    if t <= mids[0]:
        return f0s[0]
    for m0, m1, a, b in zip(mids, mids[1:], f0s, f0s[1:]):
        if t < m1:
            return a + lpc_codec.cdiv((b - a) * (t - m0), m1 - m0) if m1 > m0 else b
    return f0s[-1]


def plan(table, phones):
    """[(phone, dur_ms, f0_hz)] -> ([(diphone, source start, source length, target length)], [missing pairs 'a-b']),
    Flite's rule in integers. An unknown phone, an f0 of 0 or a table without pau-pau raises.

    A missing pair a-b becomes a, ('pau', PAUSE_MS, f0 of a), b; a missing a-pau or pau-b then plays pau-pau.

    Half-units: diphone a-b plays periods [0, pb) over [previous end, end of a) and [pb, n) over
    [end of a, midpoint of b). A target period starting at t in a half of target length T and source length S takes
    the source period whose start is nearest to (t - half start) * S // T, the first such on a tie; a t still before
    the half start (after a half with no periods) counts as the half start. The C port keeps two cursors over the
    phones instead of these lists. Only f0_at divides a signed number, with lpc_codec.cdiv; the rest are
    non-negative, so C division agrees."""
    for p, _, f0 in phones:
        if p not in table['phones']:
            raise KeyError(f'unknown phone {p}')
        if f0 < 1:
            raise ValueError(f'f0 {f0} for {p}')
    pau_pau = lookup(table, 'pau', 'pau')
    if pau_pau is None:
        raise KeyError('no diphone pau-pau')
    missing, filled = [], phones[:1]
    for p in phones[1:]:
        if lookup(table, filled[-1][0], p[0]) is None:
            missing.append(f'{filled[-1][0]}-{p[0]}')
            filled.append(('pau', PAUSE_MS, filled[-1][2]))
        filled.append(p)
    phones = filled
    ends, t = [], 0
    for _, ms, _ in phones:
        t += ms * RATE // 1000
        ends.append(t)
    mids = [(e0 + e1) // 2 for e0, e1 in zip([0] + ends, ends)]
    f0s = [f for _, _, f in phones]
    halves = []                                   # (diphone, first period, period count, target start, end)
    start = 0
    for i in range(len(phones) - 1):
        d = lookup(table, phones[i][0], phones[i + 1][0])
        d = pau_pau if d is None else d
        pb, n = table['diphones'][d]['pb'], len(table['diphones'][d]['periods'])
        halves.append((d, 0, pb, start, ends[i]))
        halves.append((d, pb, n - pb, ends[i], mids[i + 1]))
        start = mids[i + 1]
    out, t, h = [], 0, 0
    while h < len(halves):
        d, p0, np_, t0, t1 = halves[h]
        if t >= t1 or np_ == 0:
            h += 1
            continue
        period = RATE // f0_at(t, mids, f0s)
        per = table['diphones'][d]['periods']
        starts = [sum(per[:p0 + k]) for k in range(np_ + 1)]   # source sample starts, and the half's end
        u = starts[0] + (t - t0) * (starts[-1] - starts[0]) // (t1 - t0) if t > t0 else starts[0]
        k = next((k for k in range(np_) if abs(u - starts[k]) < abs(u - starts[k + 1])), np_ - 1)
        out.append((d, starts[k], per[p0 + k], period))
        t += period
    return out, missing


def render(table, periods, scale=None, raw=False):
    """[(diphone, source start, source length, target length)] -> int16 samples. Mirrors relp_codec.synthesise:
    each residual sample is played with the gain and filter of the source frame it comes from; padding plays zero
    through the filter last used. The lattice state runs on across periods and diphones."""
    scale = table['scale'] if scale is None else scale
    sat = lpc_codec.sat
    order, n_level = relp_codec.ORDER, relp_codec.N_LEVEL
    b = [0] * (order + 1)
    k, level, cur = [0] * order, [0] * n_level, None
    out = []
    for d, s0, slen, tlen in periods:
        frames = table['diphones'][d]['frames']
        if slen < tlen:
            lead, src, n_src = (tlen - slen) // 2, s0, slen
        else:
            lead, src, n_src = 0, s0 + (slen - tlen) // 2, tlen
        for j in range(tlen):
            f = 0
            if lead <= j < lead + n_src:
                p = src + j - lead
                fr = frames[p // HOP]
                if (d, p // HOP) != cur:
                    cur = (d, p // HOP)
                    k = [relp_codec.KT[i][fr[1 + i]] for i in range(order)]
                    level = [(relp_codec.LEVEL_Q12[m] * relp_codec.GAIN_Q20[fr[0]]) >> 12 for m in range(n_level)]
                c = fr[-1][p % HOP]
                f = -level[c & (n_level - 1)] if c & n_level else level[c & (n_level - 1)]
            for i in range(order - 1, -1, -1):
                f = sat(f - ((k[i] * b[i]) >> 15))
                b[i + 1] = sat(b[i] + ((k[i] * f) >> 15))
            b[0] = f
            if raw:
                out.append(f)
                continue
            s = (f * scale) >> 16
            out.append(32767 if s > 32767 else (-32768 if s < -32768 else s))
    return out


# ---- Flite as the reference ----

def flite_utt(text):
    """Flite's kal phones for text: ([(phone, dur_ms, f0_hz)], Flite's own 8 kHz samples, (its segment ends in s,
    its f0 targets [(s, Hz)])).
    f0 per phone is Flite's target contour at the phone's midpoint."""
    flite, kal = flite_libs()
    vp = ctypes.c_void_p
    for f, res, args in (('flite_synth_text', vp, [ctypes.c_char_p, vp]), ('utt_relation', vp, [vp, ctypes.c_char_p]),
                         ('relation_head', vp, [vp]), ('item_next', vp, [vp]),
                         ('item_feat_float', ctypes.c_float, [vp, ctypes.c_char_p]),
                         ('item_feat_string', ctypes.c_char_p, [vp, ctypes.c_char_p]),
                         ('utt_wave', vp, [vp]), ('cst_wave_save_riff', ctypes.c_int, [vp, ctypes.c_char_p])):
        getattr(flite, f).restype, getattr(flite, f).argtypes = res, args
    kal.register_cmu_us_kal.restype = vp
    flite.flite_init()
    utt = flite.flite_synth_text(text.encode(), kal.register_cmu_us_kal(None))

    def items(rel):
        it = flite.relation_head(flite.utt_relation(utt, rel))
        while it:
            yield it
            it = flite.item_next(it)
    segs = [(flite.item_feat_string(s, b'name').decode(), flite.item_feat_float(s, b'end')) for s in items(b'Segment')]
    targets = [(flite.item_feat_float(t, b'pos'), flite.item_feat_float(t, b'f0')) for t in items(b'Target')]
    phones, prev = [], 0.0
    for name, end in segs:
        mid = (prev + end) / 2
        f0 = float(np.interp(mid, [p for p, _ in targets], [f for _, f in targets]))
        phones.append((name, int(round((end - prev) * 1000)), int(round(f0))))
        prev = end
    with tempfile.TemporaryDirectory() as d:
        flite.cst_wave_save_riff(flite.utt_wave(utt), f'{d}/f.wav'.encode())
        x, rate = relp_reference.ref.read_wav(f'{d}/f.wav')
    assert rate == RATE
    return phones, x, (segs, targets)


def write_clip(out, name, samples):
    """8 kHz samples (float, any scale) -> <name>.wav and <name>.pcm at 16 kHz, peak PEAK."""
    y = np.asarray(samples, dtype=float)
    y = relp_reference.to_out_rate(y / (np.max(np.abs(y)) + 1e-9) * 0.5, RATE)
    pcm = relp_reference.write_wav(f'{out}/{name}.wav', y, relp_reference.OUT_RATE, PEAK)
    open(f'{out}/{name}.pcm', 'wb').write(pcm)
    return len(pcm) // 2 / relp_reference.OUT_RATE


def snr(ref, x):
    n = min(len(ref), len(x))
    ref, x = np.asarray(ref[:n], float), np.asarray(x[:n], float)
    x = x * np.dot(ref, x) / max(np.dot(x, x), 1e-9)        # best gain, so only the shape counts
    return 10 * np.log10(np.sum(ref ** 2) / max(np.sum((ref - x) ** 2), 1e-9))


def say(table, wire, path):
    """Wire bytes -> 8 kHz wav at path, logging any substituted pairs."""
    periods, missing = plan(table, unpack_wire(table, wire))
    if missing:
        print(f'substituted (a, pau, b): {" ".join(missing)}', file=sys.stderr)
    lpc_codec.write_wav(path, render(table, periods))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'build':
        kal = load_kal()
        table = build(kal)
        blob = write_table(sys.argv[2], table)
        nf = sum(len(d['frames']) for d in table['diphones'])
        np_ = sum(len(d['periods']) for d in table['diphones'])
        print(f'{sys.argv[2]}: {len(blob)} B ({len(blob) / 1024:.0f} KB): {len(table["diphones"])} diphones, '
              f'{len(table["phones"])} phones, {nf} frames ({nf * HOP / RATE:.0f} s), {np_} periods; '
              f'kal as stored in Flite {kal["stored"] / 1024:.0f} KB')
    elif cmd == 'say':
        table = unpack(open(sys.argv[2], 'rb').read())
        a = sys.argv[4:]
        phones = [(a[i], int(a[i + 1]), int(a[i + 2])) for i in range(0, len(a), 3)]
        say(table, pack_wire(table, phones), sys.argv[3])
    elif cmd == 'wire':
        say(unpack(open(sys.argv[2], 'rb').read()), open(sys.argv[3], 'rb').read(), sys.argv[4])
    elif cmd == 'flite':
        text, out, table_path = sys.argv[2], sys.argv[3], sys.argv[4]
        os.makedirs(out, exist_ok=True)
        phones, fl, _ = flite_utt(text)
        open(f'{out}/phones.txt', 'w').write(' '.join(f'{p} {d} {f}' for p, d, f in phones) + '\n')
        table = unpack(open(table_path, 'rb').read())
        wire = pack_wire(table, phones)
        open(f'{out}/phones.wire', 'wb').write(wire)
        pl, missing = plan(table, unpack_wire(table, wire))
        assert not missing, missing
        ours = render(table, pl)
        kal = load_kal()
        idx = kal_index(kal)
        assert [(d['a'], d['b'], d['periods']) for d in idx['diphones']] == \
            [(d['a'], d['b'], d['periods']) for d in table['diphones']], 'table not built from this kal'
        as_kal = kal_play(kal, kal_periods(kal, idx, pl))
        print('phones:', ' '.join(f'{p} {d} {f}' for p, d, f in phones))
        for name, y in (('1-flite-kal', fl), ('2-kal-our-plan', as_kal), ('3-relp-our-plan', ours)):
            print(f'{name}: {write_clip(out, name, y):.2f} s')
        print(f'SNR of 3 against 2 (the codec alone): {snr(as_kal, ours):.1f} dB')
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main()
