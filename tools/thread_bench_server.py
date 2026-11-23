#!/usr/bin/env python3
# The peer for app/thread_bench.toit: UDP throughput and loss between a Thread node and this host.
# Run it on a host that is on the mesh (the border router), then boot the node: the node asks for
# a plan (H), runs it, reports, and asks for the next one, so the matrix lives here, not in flash.
#   thread_bench_server.py <port> <matrix>      matrix: a name in MATRICES
# One JSON line per run on stdout.
#
# The wire. First byte is the type; the second is the run id, except in H and P.
#   node -> H                              hello, give me a plan
#   peer -> P "id size up_n up_ms down_n down_ms"   (id 0: nothing to do)
#   node -> G id          peer -> A id     go / ack; the peer starts its downlink 200 ms after
#   both -> D id seq:u16 pad               data, `size` bytes in all
#   peer -> F id                           downlink finished (5 times)
#   node -> E id text     peer -> R id text  the node's counts / the peer's counts
import json
import socket
import sys
import threading
import time

# (size, up_n, up_ms, down_n, down_ms). Sizes are a 4 B header plus LC3 at 32 kbit/s
# (40 B per 10 ms): 44 B is one frame, 84 two, 404 ten (rung 7's datagram).
def audio(size, ms, seconds=20):
    n = seconds * 1000 // ms
    return [(size, n, ms, 0, 0), (size, 0, 0, n, ms), (size, n, ms, n, ms)]

MATRICES = {
    "smoke": [(84, 50, 20, 50, 20)],
    "audio": audio(44, 10) + audio(84, 20) + audio(404, 100),
    # Faster than audio, to find the ceiling: 2x, 4x and 8x the audio rate, each way.
    "ceiling": [(84, 1000, 10, 0, 0), (84, 1000, 5, 0, 0), (84, 1000, 2.5, 0, 0),
                (404, 300, 50, 0, 0), (404, 300, 25, 0, 0), (404, 300, 12.5, 0, 0),
                (84, 0, 0, 1000, 10), (84, 0, 0, 1000, 5), (84, 0, 0, 1000, 2.5),
                (404, 0, 0, 300, 50), (404, 0, 0, 300, 25), (404, 0, 0, 300, 12.5)],
}


class Run:
    def __init__(self, run_id, plan):
        self.id = run_id
        self.size, self.up_n, self.up_ms, self.down_n, self.down_ms = plan
        self.started = None
        self.reported = False
        self.seqs = set()
        self.dups = self.late = 0
        self.highest = -1
        self.first = self.last = None
        self.max_gap = 0.0

    def plan_text(self):
        return f"{self.id} {self.size} {self.up_n} {self.up_ms} {self.down_n} {self.down_ms}"

    def data(self, seq, now):
        if seq in self.seqs:
            self.dups += 1
            return
        self.seqs.add(seq)
        if seq < self.highest:
            self.late += 1
        self.highest = max(self.highest, seq)
        if self.first is None:
            self.first = now
        else:
            self.max_gap = max(self.max_gap, now - self.last)
        self.last = now

    def result(self, node_text):
        node = dict(field.split("=") for field in node_text.split())
        out = {"run": self.id, "size": self.size}
        if self.up_n:
            got = len(self.seqs)
            span = (self.last - self.first) if got > 1 else 0
            out.update(up_n=self.up_n, up_ms=self.up_ms, up_rx=got,
                       up_loss_pct=round(100 * (self.up_n - got) / self.up_n, 2),
                       up_dup=self.dups, up_late=self.late,
                       up_span_ms=round(span * 1000), up_max_gap_ms=round(self.max_gap * 1000),
                       up_kbit_s=round((got - 1) * self.size * 8 / span / 1000, 1) if span else 0,
                       node_sent_ms=int(node["sent_ms"]), node_send_err=int(node["send_err"]))
        if self.down_n:
            got = int(node["down_rx"])
            span = int(node["span_ms"])
            out.update(down_n=self.down_n, down_ms=self.down_ms, down_rx=got,
                       down_loss_pct=round(100 * (self.down_n - got) / self.down_n, 2),
                       down_late=int(node["late"]), down_span_ms=span,
                       down_max_gap_ms=int(node["max_gap_ms"]),
                       down_kbit_s=round((got - 1) * self.size * 8 / span, 1) if span else 0)
        return out


def send_down(sock, addr, run):
    packet = bytearray(run.size)
    packet[0], packet[1] = ord("D"), run.id
    start = time.monotonic() + 0.2
    for seq in range(run.down_n):
        wait = start + seq * run.down_ms / 1000 - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        packet[2], packet[3] = seq >> 8, seq & 0xFF
        sock.sendto(packet, addr)
    for _ in range(5):
        time.sleep(0.1)
        sock.sendto(bytes([ord("F"), run.id]), addr)


def main():
    port, plans = int(sys.argv[1]), MATRICES[sys.argv[2]]
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.bind(("::", port))
    print(f"thread_bench_server on [::]:{port}, {len(plans)} runs", file=sys.stderr, flush=True)
    index = 0
    run = Run(1, plans[0])
    node = None
    while True:
        data, addr = sock.recvfrom(2048)
        now = time.monotonic()
        kind = data[:1]
        if kind == b"H":
            if addr[0] != node:
                node = addr[0]
                print(f"thread_bench_server: node {node}", file=sys.stderr, flush=True)
            if run and run.reported:
                index += 1
                run = Run(index + 1, plans[index]) if index < len(plans) else None
                if not run:
                    print("thread_bench_server: matrix done", file=sys.stderr, flush=True)
            sock.sendto(b"P" + (run.plan_text() if run else "0 0 0 0 0 0").encode(), addr)
        elif not run or len(data) < 2 or data[1] != run.id:
            continue
        elif kind == b"G":
            # A G long after the start is a rerun (the node never got our R): count afresh.
            expected = max(run.up_n * run.up_ms, run.down_n * run.down_ms) / 1000 + 15
            if run.started is not None and now - run.started > expected:
                run = Run(run.id, plans[index])
            if run.started is None:
                run.started = now
                if run.down_n:
                    threading.Thread(target=send_down, args=(sock, addr, run), daemon=True).start()
            sock.sendto(bytes([ord("A"), run.id]), addr)
        elif kind == b"D" and len(data) >= 4:
            run.data(data[2] << 8 | data[3], now)
        elif kind == b"E":
            result = run.result(data[2:].decode())
            if not run.reported:
                run.reported = True
                print(json.dumps(result), flush=True)
            sock.sendto(bytes([ord("R"), run.id]) + f"up_rx={len(run.seqs)}".encode(), addr)


if __name__ == "__main__":
    main()
