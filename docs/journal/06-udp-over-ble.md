# 06 — UDP over Bluetooth LE, from Toit

Rung 6, 2026-11-20 to 2026-11-21.

## What we set out to do

Send UDP from Toit on the XIAO through rete's Bluetooth LE relay on the Pixel (`rete/protocol/RELAY-BLE.md`), over
Tailscale to `udp-echo6` on a tailnet host, and get the echo back. Measure round trips, and whether a stream at the
LC3 rate of rung 5 (one 400 B block per 100 ms) gets through. The first check is rete's own C transport,
`udp_ble.c`, built unchanged into a small program on the XIAO (`c/relaycheck`).

## What it took

- **Wall time:** about 15 minutes from the plan to everything built; about 2 h 20 min at the bench that night (the C
  check, then three breaks in the Toit build); about 1 h 30 min the next morning (the stream, the outage test).
- **Tokens (Claude Code):** 281 messages, 182 k output, 600 k cache-write, 30.8 M cache-read, from `tools/tokens.py
  2026-11-20T19:31:04Z 2026-11-21T18:54:51Z` (the whole rung, including a session that crashed and was recovered).
- **New in ztoit** (code lines, without comments):
  - `udp_ble.cc` (181 lines): Toit's `udp` primitives over the relay, beside `udp_zephyr.cc`, which stays for Wi-Fi
    and Thread. A build picks one.
  - `ble_udp_zephyr.cc/.h` (396 lines): rete's transport, ported: one bonded phone, one L2CAP channel, a ring of
    datagrams per socket.
  - `relay_frame.h` and `ipv6_text.h` (113 lines): the relay's frame header and IPv6 address text, header-only and
    tested on the host (82 lines of tests).
  - `network.toit`: `net.open` returns the BLE network when the build has it.
  - `prj_ble.conf`: 22 settings.
- **The Toit programs:** `app/rung6check.toit` (50 code lines): three checks, PASS or FAIL each. `app/rung6.toit` (71
  code lines): 20 pings, then a stream of 50 blocks of 400 B, one per 100 ms.

## What broke

1. **The bond lived only in RAM.** The board config turned on settings but chose no storage backend, so Zephyr fell
   back to `SETTINGS_NONE`. After a reset the phone still had the bond and the board didn't, and pairing failed every
   few seconds (`pairing failed (4)`, then `(9)`). Forgetting the board on the phone worked until the next reset.
   - **Fix:** `CONFIG_ZMS`, the settings backend for the nRF54L's RRAM. The bond now survives a reflash: the relay
     comes up in 200–400 ms with no pairing.
2. **A stack overflow at the first link.** The Toit build faulted in Bluetooth's long workqueue (`BT LW WQ`) the moment
   the phone connected. ztoit's Mbed TLS 4 config turns off the small P-256 code (p256-m), so pairing's key exchange
   runs on Mbed TLS's general ECC code, which needs more than the default 1400 B.
   - **Fix:** 4096 B for that workqueue, and 2048 B for the system workqueue (as rete's own config has).
3. **Every `udp-open` threw `UNIMPLEMENTED`.** The library opens a socket in two steps, create then bind;
   `udp_ble.cc` had only a one-step bind, copied from rete's C API.
   - **Fix:** `create_socket` and `bind_socket`, as `udp_zephyr.cc` has them. The checks then gave PASS, PASS, FAIL:
     the too-big check sent 1280 B, and Tailscale's path carries at most 1232 B (MTU 1280 less the IPv6 and UDP
     headers). The check now sends 1232 B.
4. **The stream fell behind.** 34 of 50 blocks came back, and the round trip grew by about 100 ms a block, to 4.5 s.
   Sends never blocked; the board was slow to *receive*. Zephyr's L2CAP receive path gives the phone one credit at a
   time, so each 400 B block (two radio packets) waits for credits between packets: about 4–5 connection events a
   block. The phone connected at 18.75 ms, and then the board's own Zephyr defaults asked for 30–50 ms. At 50 ms
   that's about 4 blocks a second, against 10.
   - **Fix:** the board asks for 7.5–15 ms. That costs radio power, and the board runs on USB. Asking for the short
     interval only while datagrams flow is ztoit #46.

**What went into C this rung, and why:**
- The transport. Bluetooth, the L2CAP channel and the bond are Zephyr's, in C; datagrams cross into Toit through the
  same `udp` primitives that Wi-Fi and Thread use, so a Toit program can't tell which link it has.
- The frame codecs, because the transport needs them before any Toit runs.

## Evidence

The C check, rete's `udp_ble.c` on the XIAO, 20 pings: `relaycheck: 20/20 echoed`, round trips 42–244 ms.

The Toit checks (2026-11-21 10:42):

```
ble: relay up in 806 ms
PASS echo-one
PASS two-sockets
PASS too-big
```

The demo, at the 15 ms interval (11:09):

```
pings: 20/20 echoed, rtt min 39 median 58 max 126 ms
stream: sent 50 echoed 50, rtt median 75 ms, lost []
```

| Connection interval | Stream | Median round trip |
|---|---|---|
| 50 ms | 34/50 | 2823 ms, still growing |
| 15 ms | 50/50 | 75 ms, steady |

The same stream sent from msi to the echo host: 50/50 at about 1 ms, so the loss was never on the tailnet.

**The relay going away.** A 30 s stream (300 blocks); about 15 s in, the relay app was stopped on the Pixel, and
started again 10 s later:

| | |
|---|---|
| Channel down, up | 11:53:05, 11:53:15 |
| Lost | blocks 158–261: 104 blocks, the 10.4 s of the outage |
| Outside the outage | none lost; 196 echoed, median 82 ms |
| Exceptions | none |
| Reconnect | link and channel up within about 1 s of starting the app |

A send while the channel is down is dropped, as UDP over a down link would be, so the program carries on.

## Sizes

| Build | FLASH | RAM (static) |
|---|---|---|
| C check `relaycheck` | 166172 B | 47212 B |
| ztoit + `rung5.toit` (rung 5) | 360912 B | 131400 B |
| ztoit + `rung6.toit` | 559800 B | 175880 B |

Bluetooth LE adds about 194 KB of flash and 43 KB of RAM; most of it is Zephyr's Bluetooth stack and its crypto.
Flash is now 70 % full.

## Toit vs C

| | C check `relaycheck` | Toit `rung6.toit` |
|---|---|---|
| Source | 44 code lines, pings only | 71 code lines, pings and the stream |
| Opening | `udp_open`, then wait for `net_link_up` | `net.open`, then `udp-open` |
| Addresses | the relay's IPv6 text, by hand | `net.SocketAddress` |
