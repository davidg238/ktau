"""Reassembles the clips a ktau device streams, and the bytes of its wire (rung 7).

Big-endian. audio: clip:u16 | seq:u16 | 400 B of LC3 (one 100 ms block, seq from 0).
end: clip:u16 | 0xFFFF | blocks:u16 (sent 3 times). reply: clip:u16 | status:u8.
A clip finishes on its END, when the same source starts another clip, or after `idle_s` with nothing new.
"""
import collections, struct

ACTED, NO_SPEECH, FAILED = 0, 1, 2
BLOCK_BYTES = 400   # 10 LC3 frames of 40 B: 100 ms at 16 kHz, 32 kbit/s (rung 5).
MAX_BLOCKS = 100    # The device stops at 50 (5 s); this is the guard.
END_SEQ = 0xFFFF
REMEMBERED = 8      # Finished clip ids kept per source, so repeated ENDs and late blocks are dropped.

Clip = collections.namedtuple('Clip', 'src clip_id frames')  # frames: one per block, None where lost.


def encode_audio(clip_id, seq, lc3):
    return struct.pack('>HH', clip_id, seq) + lc3


def encode_end(clip_id, blocks):
    return struct.pack('>HHH', clip_id, END_SEQ, blocks)


def encode_reply(clip_id, status):
    return struct.pack('>HB', clip_id, status)


class _Open:
    def __init__(self, clip_id, now):
        self.clip_id, self.blocks, self.last = clip_id, {}, now

    def finish(self, src, count=None):
        if count is None:
            count = max(self.blocks) + 1 if self.blocks else 0
        return Clip(src, self.clip_id, [self.blocks.get(i) for i in range(count)])


class Assembler:
    def __init__(self, idle_s=1.5):
        self.idle_s = idle_s
        self.open = {}   # src -> _Open
        self.done = collections.defaultdict(lambda: collections.deque(maxlen=REMEMBERED))

    def feed(self, src, data, now):
        """Takes one datagram; returns the clips it finished (usually none)."""
        if len(data) < 4:
            return []
        clip_id, seq = struct.unpack_from('>HH', data)
        if clip_id in self.done[src]:
            return []
        out = []
        cur = self.open.get(src)
        if cur and cur.clip_id != clip_id:
            out.append(self._close(src))
            cur = None
        if seq == END_SEQ:
            if len(data) != 6:
                return out
            count = min(struct.unpack_from('>H', data, 4)[0], MAX_BLOCKS)
            out.append(self._close(src, count) if cur else Clip(src, clip_id, [None] * count))
            self.done[src].append(clip_id)
            return out
        if seq >= MAX_BLOCKS or len(data) != 4 + BLOCK_BYTES:
            return out
        if cur is None:
            cur = self.open[src] = _Open(clip_id, now)
        cur.blocks[seq] = bytes(data[4:])
        cur.last = now
        return out

    def expire(self, now):
        """Returns the clips that have heard nothing for `idle_s`."""
        stale = [src for src, c in self.open.items() if now - c.last > self.idle_s]
        return [self._close(src) for src in stale]

    def _close(self, src, count=None):
        cur = self.open.pop(src)
        self.done[src].append(cur.clip_id)
        return cur.finish(src, count)
