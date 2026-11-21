#!/usr/bin/env python3
"""Send an audio file to ktau's receiver exactly as the device does (rung 7), and print the reply.

Usage: sendclip.py <audio-file> <host> [--port 7700] [--clip N] [--drop SEQ,…] [--no-end]
       sendclip.py <audio-file> --write F.lc3          (encode only, for a host without liblc3)
       sendclip.py --read F.lc3 <host> …                (send an encoded dump)

ffmpeg decodes the file to 16 kHz mono; the host liblc3 encodes 10 ms frames of 40 B; each 100 ms block goes in
one datagram, one per 100 ms; then the END 3 times, 50 ms apart. Waits 30 s for the reply.
A dump is the blocks back to back (400 B each; a short last block is padded with silence before encoding).
"""
import argparse, os, socket, struct, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'server'))
import clips  # noqa: E402

STATUS = {clips.ACTED: 'ACTED', clips.NO_SPEECH: 'NO-SPEECH', clips.FAILED: 'FAILED', clips.REFUSED: 'REFUSED'}


def encode(path):
    import lc3dec
    pcm = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', '16000', '-f', 's16le', '-'],
                         capture_output=True, check=True).stdout
    pcm += b'\0' * (-len(pcm) % 3200)
    enc = lc3dec.lc3().Encoder(10000, 16000, libpath=lc3dec.LIBPATH)
    return b''.join(enc.encode(pcm[i:i + 320], 40, bit_depth=16) for i in range(0, len(pcm), 320))


def send(lc3, host, port, clip_id, drop, end):
    blocks = [lc3[i:i + clips.BLOCK_BYTES] for i in range(0, len(lc3), clips.BLOCK_BYTES)][:50]
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    addr = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_DGRAM, 0, socket.AI_V4MAPPED)[0][4]
    start = time.monotonic()
    for seq, b in enumerate(blocks):
        if seq not in drop:
            sock.sendto(clips.encode_audio(clip_id, seq, b), addr)
        time.sleep(max(0.0, start + (seq + 1) * 0.1 - time.monotonic()))
    released = time.monotonic()
    if end:
        for _ in range(3):
            sock.sendto(clips.encode_end(clip_id, len(blocks)), addr)
            time.sleep(0.05)
    sock.settimeout(30)
    try:
        while True:
            data, _ = sock.recvfrom(64)
            if len(data) == 3 and struct.unpack('>H', data[:2])[0] == clip_id:
                print('clip %d: %d sent, reply %s in %d ms' % (clip_id, len(blocks) - len(drop & set(range(len(blocks)))),
                      STATUS.get(data[2], data[2]), (time.monotonic() - released) * 1000))
                return
    except socket.timeout:
        print('clip %d: %d sent, no reply' % (clip_id, len(blocks)))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('audio', nargs='?')
    p.add_argument('host', nargs='?')
    p.add_argument('--port', type=int, default=7700)
    p.add_argument('--clip', type=int, default=int(time.time()) & 0xFFFF)
    p.add_argument('--drop', default='')
    p.add_argument('--no-end', action='store_true')
    p.add_argument('--write')
    p.add_argument('--read')
    a = p.parse_args()
    if a.read:
        a.host = a.host or a.audio
        lc3 = open(a.read, 'rb').read()
    else:
        lc3 = encode(a.audio)
    if a.write:
        open(a.write, 'wb').write(lc3)
        print('%s: %d blocks' % (a.write, len(lc3) // clips.BLOCK_BYTES))
        return
    drop = {int(s) for s in a.drop.split(',') if s}
    send(lc3, a.host, a.port, a.clip, drop, not a.no_end)


if __name__ == '__main__':
    main()
