"""Tests for receiver.py's audio path: run with `python3 -m unittest server/test_receiver.py` from the repo root.

Needs the host liblc3 (see tools/lc3dec.py)."""
import math, os, struct, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import lc3dec  # noqa: E402
import receiver  # noqa: E402


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


if __name__ == '__main__':
    unittest.main()
