"""Tests for receiver.py's audio path: run with `python3 -m unittest server/test_receiver.py` from the repo root.

Needs the host liblc3 (see tools/lc3dec.py)."""
import contextlib, io, math, os, struct, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import clips, kal_diphones, lc3dec  # noqa: E402
import receiver, speak  # noqa: E402
from test_act import Stub  # noqa: E402


def sine_block(hz, amp):
    """One 100 ms block (10 frames of 40 B) of a sine, encoded on the host."""
    enc = lc3dec.lc3().Encoder(10000, 16000, libpath=lc3dec.LIBPATH)
    pcm = struct.pack('<1600h', *(int(amp * 32767 * math.sin(2 * math.pi * hz * i / 16000)) for i in range(1600)))
    return b''.join(enc.encode(pcm[i:i + 320], 40, bit_depth=16) for i in range(0, 3200, 320))


class ReceiverAudioTest(unittest.TestCase):
    def test_lost_block_is_silence(self):
        b = sine_block(440, 0.25)
        samples = receiver.decode_clip([b, None, b])
        self.assertEqual(len(samples), 4800)
        self.assertEqual(max(abs(x) for x in samples[1600:3200]), 0.0)
        self.assertGreater(max(abs(x) for x in samples[3200:]), 0.1)

    def test_normalise_to_peak(self):
        samples = receiver.decode_clip([sine_block(440, 0.1)] * 3)
        out = receiver.normalise(samples)
        self.assertAlmostEqual(max(abs(x) for x in out), receiver.PEAK, places=5)

    def test_normalise_silence_stays_silent(self):
        self.assertEqual(list(receiver.normalise(receiver.decode_clip([None, None]))), [0.0] * 3200)


# The kal voice's phones, numbered as tools/kal_diphones.py build numbers them in the board's table.
PHONES = kal_diphones.kal_index(kal_diphones.load_kal())['phones']


class ReceiverHandleTest(unittest.TestCase):
    """Whatever goes wrong with one clip, handle() replies FAILED and the receiver lives on."""
    clip = clips.Clip(('::1', 1, 0, 0), 7, [None])
    table = {'phones': PHONES}  # all of the table speak.wire reads

    def handle(self, stt, content):
        stub = Stub(content)
        try:
            return receiver.handle(self.clip, stt, stub.url, '/nonexistent/notes.txt', self.table)
        finally:
            stub.close()

    def test_llm_null_content_fails(self):
        status, line, wire = self.handle(lambda s: ('hello', 0.1), None)
        self.assertEqual(status, clips.FAILED)
        self.assertIn('error', line)

    def test_none_is_refused_and_spoken(self):
        status, line, wire = self.handle(lambda s: ('turn on the lights', 0.1),
                                         '{"action":"none","text":"I cannot."}')
        self.assertEqual(status, clips.REFUSED)
        self.assertEqual([p for p, _, _ in kal_diphones.unpack_wire(self.table, wire)],
                         ['pau', 'ay', 'k', 'ae', 'n', 'aa', 't', 'pau'])

    def test_note_is_acted(self):
        with tempfile.TemporaryDirectory() as d:
            stub = Stub('{"action":"note","text":"milk"}')
            try:
                status, _, wire = receiver.handle(self.clip, lambda s: ('note milk', 0.1), stub.url, d + '/notes.txt',
                                                    self.table)
            finally:
                stub.close()
        self.assertEqual((status, wire), (clips.ACTED, b''))

    def test_say_replies_with_phones(self):
        status, line, wire = self.handle(lambda s: ('say hello', 0.1), '{"action":"say","text":"Hello there."}')
        self.assertEqual(status, clips.ACTED)
        phones = kal_diphones.unpack_wire(self.table, wire)
        self.assertEqual([p for p, _, _ in phones], ['pau', 'hh', 'ax', 'l', 'ow', 'dh', 'eh', 'r', 'pau'])
        self.assertTrue(all(ms > 0 and 50 < hz < 256 for _, ms, hz in phones))
        self.assertIn('speak 9/9 phones', line)
        self.assertLessEqual(len(clips.encode_reply(7, status, wire)), 4 + clips.BLOCK_BYTES)

    def test_long_say_is_cut_at_a_pause(self):
        text = 'One two three four five six seven eight nine ten, ' * 6
        status, line, wire = self.handle(lambda s: ('count', 0.1), '{"action":"say","text":"%s"}' % text)
        self.assertEqual(status, clips.ACTED)
        phones = kal_diphones.unpack_wire(self.table, wire)
        self.assertLessEqual(len(wire), clips.MAX_WIRE)
        self.assertEqual(phones[-1][0], 'pau')
        self.assertGreater(len(phones), speak.MAX_PHONES // 2)

    def test_phone_the_table_lacks_fails(self):
        stub = Stub('{"action":"say","text":"Hello there."}')
        try:
            status, line, wire = receiver.handle(self.clip, lambda s: ('say hello', 0.1), stub.url, '/nonexistent/n',
                                                 {'phones': ['pau', 'hh']})
        finally:
            stub.close()
        self.assertEqual((status, wire), (clips.FAILED, b''))
        self.assertIn('speak', line)

    def test_whisper_falls_back_to_the_cpu(self):
        class FakeWhisper(receiver.Whisper):
            def __init__(self, fallback):
                self.model, self.fallback = 'gpu', fallback

            def transcribe(self, model, samples):
                if model == 'gpu':
                    raise RuntimeError('CUDA failed with error out of memory')
                return model, 0.0
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(FakeWhisper('cpu')(b''), ('cpu', 0.0))
        self.assertIn('out of memory', out.getvalue())
        with self.assertRaises(RuntimeError):
            FakeWhisper(None)(b'')

    def test_stt_error_fails(self):
        def stt(samples):
            raise RuntimeError('whisper broke')
        status, line, wire = self.handle(stt, '{"action":"none","text":"x"}')
        self.assertEqual(status, clips.FAILED)
        self.assertIn('whisper broke', line)


if __name__ == '__main__':
    unittest.main()
