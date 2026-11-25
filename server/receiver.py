#!/usr/bin/env python3
"""ktau's receiver on the tailnet (rung 7): LC3 clips from the device → Whisper → the LLM → an action → a reply.

Usage: uv run -q --with faster-whisper --with numpy python -I server/receiver.py
         [--port 7700] [--llm http://z170:8080] [--model medium.en] [--notes ~/.local/state/ktau/notes.txt]
         [--table c/kalcheck/clips/kal-relp.bin]   (the diphone table in the board's flash; needs libflite)
         [--device cuda --gpu N]                   (Whisper on a GPU: server/receiver-gpu.sh sets up CUDA's libraries)

The wire is in clips.py. One clip at a time; datagrams arriving meanwhile wait in the socket. Per clip one line:
clip <id> from <src>: <blocks> blocks (<lost> lost) | stt <s> s "<text>" nsp=<p> | llm <s> s <action> "<text>"
  [| speak <spoken>/<made> phones] | <STATUS>
The text of a `say` or a `none` is spoken by the board: it goes back in the reply as phones (speak.py), cut to one
datagram.
"""
import argparse, array, os, socket, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import act, clips, lc3dec, speak  # noqa: E402

RATE, FRAME_US, FRAME_BYTES = 16000, 10000, 40   # rung 5's Lc3Encoder.
BLOCK_SAMPLES = RATE // 10                        # 100 ms per datagram.
PEAK = 0.9          # Levels are evened out here, not by device gain (design, Decided).
NO_SPEECH = 0.6     # Whisper scored silence ≈ 0.9 (journal 05).
STATUS = {clips.ACTED: 'ACTED', clips.NO_SPEECH: 'NO-SPEECH', clips.FAILED: 'FAILED', clips.REFUSED: 'REFUSED'}


def decode_clip(frames):
    """LC3 blocks (None where lost) → float samples in -1..1; a lost block is 100 ms of silence."""
    dec = lc3dec.lc3().Decoder(FRAME_US, RATE, libpath=lc3dec.LIBPATH)
    out = array.array('f')
    for block in frames:
        if block is None:
            out.extend([0.0] * BLOCK_SAMPLES)
        else:
            for i in range(0, len(block), FRAME_BYTES):
                out.extend(dec.decode(block[i:i + FRAME_BYTES]))
    return out


def normalise(samples):
    peak = max((abs(x) for x in samples), default=0.0)
    if peak == 0.0:
        return samples
    g = PEAK / peak
    return array.array('f', (x * g for x in samples))


class Whisper:
    """On a GPU, a clip the GPU fails on (it shares the card with the LLM and can run out of memory) is
    transcribed on the CPU instead, slower."""

    def __init__(self, model, device='cpu', gpu=0):
        import faster_whisper  # Only under uv; the tests above don't need it.
        self.model = faster_whisper.WhisperModel(model, device=device, device_index=gpu, compute_type='int8')
        self.fallback = None if device == 'cpu' else faster_whisper.WhisperModel(model, device='cpu',
                                                                                 compute_type='int8')

    def transcribe(self, model, samples):
        import numpy
        segments, _ = model.transcribe(numpy.frombuffer(samples, dtype=numpy.float32), language='en',
                                       vad_filter=False)
        segments = list(segments)
        text = ' '.join(s.text.strip() for s in segments).strip()
        return text, max((s.no_speech_prob for s in segments), default=1.0)

    def __call__(self, samples):
        """Returns (text, max no-speech probability)."""
        try:
            return self.transcribe(self.model, samples)
        except RuntimeError as e:
            if self.fallback is None:
                raise
            print('stt: on the cpu, the gpu failed: %s' % e, flush=True)
            return self.transcribe(self.fallback, samples)


def handle(clip, stt, llm, notes, table):
    """Returns (status, the line to print, the phones to speak). Any error in one clip is FAILED, so the receiver
    keeps running."""
    lost = sum(f is None for f in clip.frames)
    line = 'clip %d from %s: %d blocks (%d lost)' % (clip.clip_id, clip.src[0], len(clip.frames), lost)
    t = time.monotonic()
    stage = 'stt'
    try:
        text, nsp = stt(normalise(decode_clip(clip.frames)))
        line += ' | stt %.1f s "%s" nsp=%.2f' % (time.monotonic() - t, text, nsp)
        if not text or nsp >= NO_SPEECH:
            return clips.NO_SPEECH, line, b''
        t, stage = time.monotonic(), 'llm'
        answer = act.ask(text, llm)
        action, said = act.parse(answer)
        line += ' | llm %.1f s %s "%s"' % (time.monotonic() - t, action, said)
        act.run(action, said, notes)
        wire = b''
        if action in ('say', 'none'):
            t, stage = time.monotonic(), 'speak'
            wire, spoken, made = speak.wire(said, table)
            line += ' | speak %d/%d phones' % (spoken, made)
        if action == 'none':
            return clips.REFUSED, line, wire  # Nothing was done: the board's long blink, not "done" (David, 2026-11-21).
    except Exception as e:  # noqa: BLE001 - one bad clip must not stop the receiver.
        return (clips.FAILED, line + ' | %s %.1f s error: %s: %s' % (stage, time.monotonic() - t, type(e).__name__, e),
                b'')
    return clips.ACTED, line, wire


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=7700)
    p.add_argument('--llm', default='http://z170:8080')
    p.add_argument('--model', default='medium.en')
    p.add_argument('--notes', default=os.path.expanduser('~/.local/state/ktau/notes.txt'))
    p.add_argument('--device', default='cpu')
    p.add_argument('--gpu', type=int, default=0)
    p.add_argument('--table', default=os.path.join(HERE, '..', 'c', 'kalcheck', 'clips', 'kal-relp.bin'))
    a = p.parse_args()
    table = speak.load(a.table)
    stt = Whisper(a.model, a.device, a.gpu)
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    sock.bind(('::', a.port))
    sock.settimeout(0.25)
    asm = clips.Assembler()
    print('receiver: port %d, llm %s, whisper %s on %s' % (a.port, a.llm, a.model, a.device), flush=True)
    while True:
        try:
            data, src = sock.recvfrom(2048)
            done = asm.feed(src, data, time.monotonic())
        except socket.timeout:
            done = []
        for clip in done + asm.expire(time.monotonic()):
            status, line, wire = handle(clip, stt, a.llm, a.notes, table)
            print('%s | %s' % (line, STATUS[status]), flush=True)
            try:
                sock.sendto(clips.encode_reply(clip.clip_id, status, wire), clip.src)
            except OSError as e:
                print('clip %d: reply not sent: %s' % (clip.clip_id, e), flush=True)


if __name__ == '__main__':
    main()
