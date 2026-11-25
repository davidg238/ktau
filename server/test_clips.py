"""Tests for clips.py: run with `python3 -m unittest server/test_clips.py` from the repo root."""
import os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clips import Assembler, encode_audio, encode_end, encode_reply, MAX_BLOCKS, ACTED, NO_SPEECH, FAILED  # noqa: E402

SRC = ('fd7a::1', 4000, 0, 0)
OTHER = ('fd7a::2', 4000, 0, 0)


def block(n):
    return bytes([n]) * 400


class ClipsTest(unittest.TestCase):
    def feed_blocks(self, a, clip, seqs, src=SRC, now=0.0):
        out = []
        for s in seqs:
            out += a.feed(src, encode_audio(clip, s, block(s)), now)
        return out

    def test_end_finishes(self):
        a = Assembler()
        self.assertEqual(self.feed_blocks(a, 1, [0, 1, 2]), [])
        clips = a.feed(SRC, encode_end(1, 3), 0.0)
        self.assertEqual(len(clips), 1)
        c = clips[0]
        self.assertEqual((c.src, c.clip_id), (SRC, 1))
        self.assertEqual(c.frames, [block(0), block(1), block(2)])

    def test_duplicate_end_ignored(self):
        a = Assembler()
        self.feed_blocks(a, 1, [0, 1, 2])
        got = []
        for _ in range(3):
            got += a.feed(SRC, encode_end(1, 3), 0.0)
        self.assertEqual(len(got), 1)

    def test_lost_block_is_none(self):
        a = Assembler()
        self.feed_blocks(a, 1, [0, 2])
        c, = a.feed(SRC, encode_end(1, 3), 0.0)
        self.assertEqual(c.frames, [block(0), None, block(2)])

    def test_lost_end_expires(self):
        a = Assembler()
        self.feed_blocks(a, 1, [0, 1], now=10.0)
        self.assertEqual(a.expire(11.4), [])
        c, = a.expire(11.6)
        self.assertEqual(c.frames, [block(0), block(1)])
        self.assertEqual(a.expire(20.0), [])

    def test_new_clip_finishes_old(self):
        a = Assembler()
        self.feed_blocks(a, 5, [0, 1])
        got = self.feed_blocks(a, 6, [0])
        self.assertEqual([(c.clip_id, len(c.frames)) for c in got], [(5, 2)])
        self.assertEqual(a.feed(SRC, encode_end(5, 2), 0.0), [])  # A late END for the old clip.

    def test_two_sources_apart(self):
        a = Assembler()
        a.feed(SRC, encode_audio(1, 0, block(1)), 0.0)
        a.feed(OTHER, encode_audio(1, 0, block(2)), 0.0)
        a.feed(SRC, encode_audio(1, 1, block(3)), 0.0)
        c1, = a.feed(SRC, encode_end(1, 2), 0.0)
        c2, = a.feed(OTHER, encode_end(1, 1), 0.0)
        self.assertEqual(c1.frames, [block(1), block(3)])
        self.assertEqual(c2.frames, [block(2)])

    def test_short_or_bad_ignored(self):
        a = Assembler()
        self.assertEqual(a.feed(SRC, b'\x00\x01\x00', 0.0), [])
        self.assertEqual(a.feed(SRC, encode_audio(1, 0, b'x' * 399), 0.0), [])
        self.assertEqual(a.expire(100.0), [])

    def test_cap(self):
        a = Assembler()
        self.assertEqual(a.feed(SRC, encode_audio(1, MAX_BLOCKS, block(0)), 0.0), [])
        self.assertEqual(a.expire(100.0), [])

    def test_end_shorter_than_blocks_seen(self):
        # An END is the count of blocks sent; frames past it are dropped, frames up to it padded.
        a = Assembler()
        self.feed_blocks(a, 1, [0])
        c, = a.feed(SRC, encode_end(1, 2), 0.0)
        self.assertEqual(c.frames, [block(0), None])

    def test_wire_bytes(self):
        self.assertEqual(encode_audio(0x0102, 3, b'')[:4], b'\x01\x02\x00\x03')
        self.assertEqual(encode_end(0x0102, 7), b'\x01\x02\xff\xff\x00\x07')
        self.assertEqual(encode_reply(0x0102, FAILED), b'\x01\x02\x02')
        self.assertEqual((ACTED, NO_SPEECH, FAILED), (0, 1, 2))


if __name__ == '__main__':
    unittest.main()
