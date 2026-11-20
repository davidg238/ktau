# Rung 6: ztoit `net.udp` over BLE through the Pixel relay; an echo from a tailnet host — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Toit program on the XIAO opens `net`, sends UDP datagrams to `gw85224-01`'s echo server over the tailnet,
and reads the echoes back, with Bluetooth LE to the Pixel as the only link. Round trip and a real-time LC3-rate
stream are measured. Journal entry 6 records it.

**Architecture:**
- **The C check first:** `ktau/c/relaycheck` builds rete's `udp_ble.c` and `relay_frame.h` *in place* from
  `~/workspace/rete` (rete commit `2b8e9291`), with two stub headers for the seams it calls but this check
  doesn't need (`pulse_backend.h`, `radio_backend.h`). It pings the echo server once a second. This proves the
  XIAO's radio, bonding, the relay and the tailnet route before any Toit code is written.
- **The ztoit seam is a port, not a link:** Toit's UDP primitives (`udp_zephyr.cc`) run on an `EventSource`,
  not rete's pulse mailbox, and rete's radio on/off API isn't needed. So the fork gets `src/resources/udp_ble.cc`:
  the transport is rete's `udp_ble.c` (advertising, pair-once bonding, one L2CAP channel on PSM `0x0080`,
  one ring per socket), and the `udp` module primitives sit on top. It is compiled when
  `TOIT_ZEPHYR && CONFIG_BT && !CONFIG_NET_SOCKETS`, so the backend follows the radio, as in rete.
- **No Toit locks on the Bluetooth thread** (the keys lesson, `docs/design/zephyr-port.md`): `recv_cb` and the
  channel's `sent` callback only fill rings and give a semaphore. `BleUdpEventSource`'s own thread dispatches
  `UDP_READ`/`UDP_WRITE`, as `ZephyrKeyEventSource` does.
- **Addresses:** Toit hands the primitives 16-byte IPv6 addresses; the relay frame carries text. A small
  header-only codec, `ipv6_text.h`, writes the uncompressed form with no leading zeros
  (`fd7a:115c:a1e0:0:0:0:bf01:d921`) and parses that form and `::` forms. IPv6 only, like `udp_zephyr.cc`;
  a reply whose host isn't IPv6 text is dropped.
- **The frame codec** is rete's `relay_frame.h` copied verbatim into the fork. A host test checks it against
  the golden vector `rete/protocol/fixtures/relay/frame.hex` and that the copy matches rete's file byte for byte.
- **Send rules** (from rete, adapted to Toit): channel down → the datagram is dropped and `send` returns as if
  sent (UDP semantics; rete's rule). No TX buffer free → would-block; the `sent` callback dispatches
  `UDP_WRITE` and Toit retries. Too big → `EMSGSIZE`. `MAX_DATAGRAM` stays 1280 (as `udp_zephyr.cc`), so
  `SDU_MTU` is `RELAY_FRAME_HDR_MAX + 1280`.
- **`net.open`:** `link-kind` answers a third kind, BLE (3), under `CONFIG_BT`. `BleModule.connect` waits for
  the relay's channel (a new `zephyr.ble-ready` primitive) with a 30 s timeout and throws on timeout. Disconnect
  doesn't touch the radio: the bond and advertising stay.
- **The demo** (`ktau/app/rung6.toit`): 20 pings of 16 B, one a second, then a stream of 50 datagrams of 400 B
  at one per 100 ms (one 100 ms block of LC3 at 32 kbit/s, rung 5's rate). It prints round trips and losses.

**Tech Stack:** Zephyr v4.5.0, SDK 1.0.1 (`~/zephyr-4.5`), Zephyr's own BLE controller for the nRF54L15, the
Toit fork (`wip-plan2-fix-a`, pushed as `zephyr-port`, now `3dbabffb`), rete at `2b8e9291`, the Android relay
(`rete/relay/android`) on the Pixel 10 Pro, Tailscale, `udp-echo6` on `gw85224-01` (`fd7a:115c:a1e0::bf01:d921`,
port 7777).

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 6; "The BLE seam"; Decided: Android and rete's relay).
The wire: `~/workspace/rete/protocol/RELAY-BLE.md`. Rete's design: `rete/docs/design/2026-10-23-439-ble-relay-design.md`.

## Global Constraints

- The environment, board, console, logger and flashing rules of the rung 5 plan apply unchanged
  (`docs/superpowers/plans/2026-11-20-rung5-lc3-encode.md`, Global Constraints).
- Never halt a running nRF (ztoit #23). Flashing is fine.
- A fork commit is followed by `tools/fork-sdk.sh`; `tools/sdk-id.sh` must agree on node and host (ztoit #24);
  ztoit's `west.yml` pin moves to the new fork commit; a new primitive goes in the host compiler's primitive list.
- The C6 on 4.2 must still build after the fork change (`build-i38-c6` recipe; build only, don't flash).
  A Thread build must still pick `udp_zephyr.cc`, not `udp_ble.cc`.
- Rete is read, never changed, by this rung. A bug found in rete's code is filed in rete, `found-during ztoit#41`.
- Public text: run ktau's `git grep -n -i -f .private/public-text.txt`. No addresses other than the tailnet
  echo host's in public text.
- ztoit commits say `refs #41`. No push until `/conclude`.
- **The bench needs David** (bench call sound): the Pixel's Tailscale on (it was offline on 2026-11-20), the relay
  app running, rete's own BLE node powered off (the relay takes the first node it finds), and the Just Works
  pairing accepted on the phone.

## Review Focus

1. **A stale bond on the Pixel.** If the XIAO's settings are erased after bonding, the phone still holds the old
   keys and pairing fails. Expected: the console says the channel was refused; the journal records the fix
   ("forget the device" on the phone). Task 1 records this once on purpose.
2. **The relay drops mid-stream** (phone out of range, app killed). Expected: sends keep returning, datagrams
   are dropped, receives time out, and the stream resumes once the relay reconnects; nothing throws. Task 4 tests it.
3. **A datagram over 1280 B.** Expected: `EMSGSIZE` thrown to Toit, not a truncated frame. Task 3 tests it.
4. **Two sockets at once.** Expected: each gets only its own replies (one ring per socket). Task 3 tests it.
5. **RAM on the XIAO.** The BT host, controller and buffers on top of rung 5's LC3 and 80 KB heap. Expected:
   it links, and the rung 5 demo still runs in the same image. Task 3 records the `zephyr.stat` delta.

---

### Task 1: The C check — rete's `udp_ble.c` on the XIAO, pinging through the relay

**Files:**
- Create: `ktau/c/relaycheck/CMakeLists.txt`, `prj.conf`, `src/main.c`, `src/stub/pulse_backend.h`,
  `src/stub/radio_backend.h`, `src/stub/oevm.h` (whatever `udp_ble.c` includes that this check stubs).

**Interfaces:**
- Consumes: rete's `udp_backend.h` seam: `udp_open`, `udp_socket_bind`, `udp_send`, `udp_receive`, `net_link_up`.
- Produces: the bench evidence that the radio, bonding, relay and tailnet route work; the RAM/flash of BLE alone.

- [ ] **Step 1:** `CMakeLists.txt` compiles `~/workspace/rete/nodus/oevm/src/backend/zephyr/udp_ble.c` in place
  (path through a `RETE` CMake variable defaulting to `$ENV{HOME}/workspace/rete`), include path first
  `src/stub`, then rete's `nodus/oevm/src`. `pulse_post_isr_value` is a no-op stub. `prj.conf` takes the
  Bluetooth block of `rete/nodus/oevm/zephyr/prj_dk_ble.conf` (lines 22–45) with `CONFIG_BT_DEVICE_NAME="ktau"`,
  plus `CONFIG_SETTINGS`, `CONFIG_ZMS` (or NVS, whichever the nRF54L15 settings backend needs), `CONFIG_FLASH`.
- [ ] **Step 2:** `main.c`: `udp_open()`; bind port 0; wait for `net_link_up()` printing `relay: waiting` every
  5 s; then every second send `ping N` to `fd7a:115c:a1e0::bf01:d921` port 7777, poll `udp_receive` for up to
  1 s, print `echo N rtt=<ms>` or `lost N`. Stop after 20.
- [ ] **Step 3:** Build: `west build -b xiao_nrf54l15/nrf54l15/cpuapp -d ~/zephyr-4.5/build-relaycheck c/relaycheck`.
  Expected: links. Record flash and RAM from the build's memory report.
- [ ] **Step 4:** Bench (David, see Global Constraints): flash, accept pairing on the Pixel. Expected on the
  console: `20` lines `echo N`, no more than 1 lost. Save the log to `ktau-rung6-relaycheck-20261120.log`.
- [ ] **Step 5:** Review Focus 1, once: erase the storage partition, reboot. Expected: pairing fails; record the
  console line and the phone's message, then "forget device" on the Pixel and re-pair. Echoes resume.
- [ ] **Step 6:** Commit in ktau: `git add c/relaycheck && git commit -m "Rung 6: the C check, rete's udp_ble.c on the XIAO through the Pixel relay"`.

### Task 2: The codecs in the fork — `relay_frame.h` and `ipv6_text.h`, host-tested

**Files:**
- Create (fork): `src/resources/relay_frame.h` (verbatim copy of rete's `nodus/oevm/src/relay_frame.h` at
  `2b8e9291`), `src/resources/ipv6_text.h`.
- Create (ztoit): `tests/host/test_ble_codecs.cc`, `tools/test-host.sh` (compiles with `g++ -std=c++17
  -I<fork>/src/resources` and runs).

**Interfaces:**
- Produces: `int ipv6_format(const uint8_t addr[16], char* out, size_t cap)` → length written (without NUL),
  or -1 if `cap` is too small; `int ipv6_parse(const char* text, size_t len, uint8_t out[16])` → 0, or -1 if
  not IPv6 text. Rete's `relay_frame_put_header` / `relay_frame_parse` / `struct relay_frame` unchanged.

- [ ] **Step 1: Write the failing tests** in `test_ble_codecs.cc`:
  - `golden_vector_parses`: parse the bytes of `frame.hex` (read from `$RETE/protocol/fixtures/relay/frame.hex`)
    → `local_port == 16970`, `remote_port == 6969`, host `fd7a:115c:a1e0::1`, payload `hi`.
  - `golden_vector_builds`: `relay_frame_put_header` with those values plus `hi` equals the vector's bytes.
  - `format_drops_leading_zeros`: `fd7a:115c:a1e0::bf01:d921` → `"fd7a:115c:a1e0:0:0:0:bf01:d921"`.
  - `parse_round_trips`: parse(format(x)) == x for that address, `::1`, `::`, and all-`ffff`.
  - `parse_compressed`: `"fd7a:115c:a1e0::1"` → the same 16 bytes as the uncompressed form.
  - `parse_rejects`: `"100.87.217.33"`, `"1:2:3"`, `"1::2::3"`, `"12345::"`, `"g::"`, and `""` → -1.
  - `format_short_buffer`: `cap` 10 → -1.
  - `copy_matches_rete`: the fork's `relay_frame.h` is byte-identical to `$RETE/nodus/oevm/src/relay_frame.h`.
- [ ] **Step 2:** `tools/test-host.sh` → FAIL (`ipv6_text.h` missing).
- [ ] **Step 3:** Implement `ipv6_text.h` (header-only, `static inline`, no libc beyond `<stdint.h>`/`<stddef.h>`).
- [ ] **Step 4:** `tools/test-host.sh` → all PASS. Break one thing (change one byte of the fork copy), confirm
  `copy_matches_rete` fails, restore.
- [ ] **Step 5:** Commit the fork (`Relay frame and IPv6 text codecs for the BLE seam`), then ztoit
  (`Host test for the BLE codecs (refs #41)`).

### Task 3: `udp_ble.cc` — Toit's `udp` primitives over the relay; `net.open` over BLE

**Files:**
- Create (fork): `src/resources/udp_ble.cc`, `src/event_sources/ble_udp_zephyr.h`, `.cc`.
- Modify (fork): `src/resources/zephyr.cc` (`link_kind` answers 3 under `CONFIG_BT`; new `ble_ready`),
  `src/primitive.h` (the `ble_ready` entry), the host compiler's primitive list,
  `system/extensions/zephyr/network.toit` (`LINK-BLE_ ::= 3`, `BleModule`, `link-name_` → `"ble"`).
- Create (ztoit): `zephyr/prj_ble.conf` (the Task 1 Bluetooth block). Modify: `west.yml` pin.

**Interfaces:**
- Consumes: Task 2's `ipv6_format`, `ipv6_parse`, `relay_frame_*`.
- Produces: the stock Toit `net.udp` API working on a `-DEXTRA_CONF_FILE=prj_ble.conf` build;
  `#primitive.zephyr.ble-ready` → bool (relay channel open).

- [ ] **Step 1: Write the failing check** `ktau/app/rung6-unit.toit` (on the board; there is no BLE on the host):
  - `echo-one`: open `net`, one socket, send `"x"` to the echo host → receive `"x"` within 2 s.
  - `two-sockets`: two sockets each send their own text → each receives only its own (Review Focus 4).
  - `too-big`: sending 1281 B throws `EMSGSIZE` (Review Focus 3); 1280 B echoes back whole.
  - Prints `PASS <name>` / `FAIL <name>: <why>`.
- [ ] **Step 2:** Build ztoit for the XIAO with `prj_ble.conf` before the fork change → `net.open` throws
  (no link kind) — the expected failure. Record the line.
- [ ] **Step 3:** Implement. Port rete's transport as is (pair once, one connection, one channel, rings of
  `RING_BYTES / MAX_SOCKS`), keeping its comments' reasons and citing rete `2b8e9291`. Primitive shapes follow
  `udp_zephyr.cc`: `receive` returns null when the socket's ring is empty and the event source re-arms;
  `send` follows the send rules in Architecture. Drop rete's `radio_set`/`net_link_doorbell`; `ble_ready` is
  `chan_up`. Rete's `udp.c` 2048 B buffer becomes `MAX_DATAGRAM` 1280.
- [ ] **Step 4:** `tools/fork-sdk.sh`; `tools/sdk-id.sh` agrees; pin moves. Build the XIAO image with both the
  rung 5 app and `rung6-unit` as containers. Record `zephyr.stat` against `build-rung5` (Review Focus 5).
- [ ] **Step 5:** Flash; the bond from Task 1 survives (same storage partition). Expected: three `PASS` lines,
  and the rung 5 push-to-talk still records (one phrase).
- [ ] **Step 6:** C6 4.2 `build-i38-c6` builds; its link map has `udp_zephyr`, not `udp_ble`.
- [ ] **Step 7:** Commit the fork (`udp over Bluetooth LE to a relay (udp_ble.cc); net.open over BLE`), then
  ztoit (`prj_ble.conf; fork pin: UDP over BLE (refs #41)`), then ktau (`Rung 6: unit checks on the board`).

### Task 4: The demo, the measurements, journal 06

**Files:**
- Create (ktau): `app/rung6.toit`, `docs/journal/06-udp-over-ble.md`.

- [ ] **Step 1:** `rung6.toit`: the 20 pings (print `echo N rtt=<ms>`, then min/median/max and losses), then the
  stream: 50 × 400 B at 100 ms, each carrying its sequence number; a reader counts echoes for 3 s after the
  last send and prints `stream: sent 50 echoed K, rtt median <ms>`.
- [ ] **Step 2:** Bench run. Expected: pings ≥ 19/20; stream ≥ 48/50. Save the log.
- [ ] **Step 3:** Review Focus 2: during a second stream run David stops the relay app for ~10 s and starts it
  again. Expected: no exception; the losses cover the gap only; echoes resume. Record the reconnect time.
- [ ] **Step 4:** Journal 06, rung 5's layout: what it took (time, lines of C and Toit, flash/RAM delta), what
  broke, the evidence (round trips, stream counts, reconnect time, the stale-bond fix). Run the public-text grep.
- [ ] **Step 5:** Commit ktau (`Rung 6: Toit echoes through the Pixel relay; journal 06`). Comment on ztoit #41
  (≤ 5 lines, the numbers and the pins).
