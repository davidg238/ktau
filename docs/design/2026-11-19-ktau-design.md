# ktau — tap, speak, act: a Toit-on-Zephyr bring-up

Status: approved by David, 2026-11-19. Approach A.

## Why

ktau is a test of whether **Toit on Zephyr (ztoit) is useful**, run on a board ztoit has never seen. It also has to work
as a gadget: you tap it, speak a short instruction, and an LLM acts on it. Each step of the bring-up is written up as
it happens, and the write-up becomes a blog post: *bringing up an undefined board and its features with Toit on Zephyr*.

## The device and the path

Hardware: Seeed Studio XIAO nRF54L15 Sense, with its on-board PDM microphone and 6-axis IMU (tap detection).

1. A tap on the IMU raises its interrupt pin, and the nRF wakes from sleep.
2. The device records a short utterance from the PDM microphone and encodes it as LC3.
3. It sends the audio as UDP datagrams through rete's BLE relay on the Pixel (`rete/relay/android`), using the
   contract in `rete/protocol/RELAY-BLE.md`. The relay forwards the datagrams over Tailscale.
4. A receiver on the tailnet reassembles the audio, runs speech-to-text, and passes the text to an LLM, which acts on it.
5. The device goes back to sleep.

## Goals

- Every step is a **rung** of a ladder, each with a demo you can see. The application logic is in Toit wherever
  possible; C primitives inside ztoit handle what has to be in C.
- Every rung writes a **journal entry** recording:
  - what it took: time, lines of code, build size;
  - what broke;
  - the evidence: logs, measurements;
  - how the Toit way compares with Zephyr's C sample for the same feature.
  - the Claude tokens it cost, from `tools/tokens.py` over the rung's start and end times (David, 2026-11-19).
- At the end, a measured verdict on Toit on Zephyr: useful, not useful, or useful under these conditions.

## Non-goals

- A new phone app. rete's Android relay is the phone side.
- Production hardware. (The first prototype goes in an enclosure David already has.)
- Deep sleep (nRF System OFF). On nRF the device uses **ordinary sleep**: RAM, the VM and the BLE bond stay alive
  (David, 2026-11-19).
- iOS (Android first).

## Anti-goals: these would make it a failure even if it works

- Hiding the hard parts in C so the Toit side looks easy. The journal records what went into C, and why.
- A journal written after the fact. Entries are written at each rung, with the evidence of that day.

## Constraints

- **Power:** the first prototype uses two AAA cells in series (David, 2026-11-19); AAAA is the later, smaller option. Either way it is 3.0 V falling to about 2.0 V, fed to the 3V3 pin. A CR2032 can't supply the
  burst current for audio, and one AAAA is below the nRF54L15's 1.7 V minimum without a boost converter.
  - Out of scope since 2026-11-21 (ktau ends at rung 7); left for a battery-powered build: that the microphone and IMU run down to 2.0 V, and that feeding 3V3 does not
    back-power the XIAO's regulator or charger.
- **Zephyr:** ztoit's tree (`~/zephyr-esp32/zephyr`, Zephyr 4.2) supports the nRF54L15 SoC (`nrf54l15dk`) but has
  no `xiao_nrf54l15` board, although later Zephyr has one upstream (`boards/seeed/xiao_nrf54l15`,
  `-b xiao_nrf54l15/nrf54l15/cpuapp`). Rung 1 moves ztoit to a current Zephyr release in its own west workspace,
  and the board comes with it. Re-proving the C6, the WROOM-32 and the dongle on the new release is ztoit work,
  journalled as part of the bring-up story.
  The tree also carries an uncommitted nRF patch (see ztoit `FOCUS.md`).
- **Flashing:** the XIAO's on-board SAMD11 is a CMSIS-DAP probe: flash, debug and console over USB-C. David's J-Link
  is the fallback.
- **RAM:** the nRF54L15 has 256 KB of RAM for the VM, the BLE stack, the LC3 encoder and the audio buffers.
  This is the first thing to measure at rung 2.
- **nRF rule:** never halt a running nRF (ztoit #23). Read it unhalted.
- **The BLE seam:** `rete/nodus/oevm/src/backend/zephyr/udp_ble.c` handles one bonded relay and datagrams up to
  its `SDU_MTU`. A node bonds with exactly one relay.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | A bring-up ladder in reader order, Toit wherever it can go, Zephyr's C sample as each rung's first check | The comparison comes almost free; things that might fail late (BLE, RAM) aren't tested first |
| B | Build everything in C, then port to Toit | Cleanest side-by-side, but double the work, and the blog becomes a port story |
| C | The same ladder, ordered by risk (BLE and microphone first) | Problems surface early, but there's nothing to show early on and the story reads out of order |

## The ladder

| Rung | Demo | Where the work lands |
|---|---|---|
| 1 | Board definition for `xiao_nrf54l15`; Zephyr C blinky and console | ztoit (board files) |
| 2 | ztoit VM boots; Toit `print` and the LED; RAM measured | ztoit |
| 3 | IMU tap detection set up from Toit over I2C; a tap wakes a sleeping Toit task | ktau app, ztoit if I2C or GPIO primitives are missing |
| 4 | PDM microphone primitive; a clip recorded and played back on the host | ztoit primitive, ktau app |
| 5 | LC3 encode primitive (Zephyr `liblc3`); clip size and encode time measured | ztoit primitive |
| 6 | ztoit `net.udp` over `udp_ble.c` through the Pixel relay; echo to a tailnet host | ztoit (network seam) |
| 7 | Tailnet receiver → speech-to-text → LLM → action | ktau server |
| 8 | ~~Battery: current measured in sleep and per instruction; lifetime estimate~~ Out of scope: ktau ends at rung 7 (Decided, 2026-11-21) | — |

## Where things live

- **ztoit:** board files, primitives, the BLE network seam, and its issues. This is ztoit's readiness work.
- **`~/workspaceToit/ktau`** (new repo):
  - the Toit app;
  - the tailnet receiver;
  - `docs/journal/` (one entry per rung, the blog's raw material);
  - this design.

## Decided

- Approach A (David, 2026-11-19).
- Toit owns the IMU: Zephyr's `st,lsm6dsl` driver has no tap trigger, so tap setup is a Toit driver over one I2C
  primitive (David, 2026-11-19; journal 03).
- ktau is a public repo under MIT, published as one fresh commit after a public-text review (David, 2026-11-19).
- Ordinary sleep, not deep sleep, on nRF (David, 2026-11-19).
- Audio streams only after encoding: raw PCM is 256 kbit/s, so rung 4 buffers a clip and streaming starts with LC3
  (rung 5) over BLE (rung 6) (David, 2026-11-19; journal 04).
- Microphone gain is fixed at +10 dB; levels are evened out at the rung 7 receiver, not by gain control on the
  device. Gain doesn't improve speech over noise at 1 m (David asked for the near/far measurement, 2026-11-19;
  journal 04).
- Push to talk on the board's user button (`usr_btn`), with the LED lit while recording; the IMU tap is too easily
  set off by handling and waits, perhaps as a double tap. For the demo the board is held at the mouth (David,
  2026-11-20; journal 05).
- The receiver (rung 7) drops a clip whose Whisper no-speech probability is high: Whisper writes "you" for silence
  (journal 05).
- Android and rete's relay for the phone side (David, 2026-11-19).
- ktau ends at rung 7 as a demonstration: push to talk over BLE and Tailscale to an LLM on the tailnet. Battery
  (rung 8) is out of scope. Two posts in `docs/posts/`: the push-to-talk chain (with the Zephyr 4.2 → 4.5 move), and
  the IMU driver in Toit against Zephyr's (David, 2026-11-21).
- Rung 7 starts as a small script: receive, speech-to-text, LLM, print or carry out a simple action. Real
  tool-calling comes later, if it earns its place (David, 2026-11-19).
- The blog and journal are public, so the public-text rules apply (David, 2026-11-19).
- Zephyr: upgrade rather than backport. A new Zephyr release goes in a separate west workspace, so ztoit's working
  boards stay on 4.2 until they're re-proven there (David asked "why not upgrade", 2026-11-19).
- First prototype: two AAA cells in an enclosure David has (David, 2026-11-19); still to confirm with the 2.0 V check.
- Rung 7's receiver runs on msi; the LLM is the llama.cpp server on the z170, served to the tailnet with
  `tailscale serve` (David, 2026-11-21; journal 07). Headless Claude stays an option for later.
- Rung 7's action is a JSON pick from an allowlist (`note`, `say`, `none`) plus a reply to the board; the one user LED
  answers: 2 short blinks done, 1 long blink not done, a refusal included (David, 2026-11-21; journal 07).
- The audio wire, one datagram per 100 ms block with an END sent 3 times, is in `server/clips.py` (journal 07).

## Calls made in the design (Claude, 2026-11-19; David to check)

- **The BLE link stays up while the device sleeps.** This makes tap-to-first-datagram fast and matches how the rete
  relay holds its link. The cost of the connection interval is unmeasured: ktau runs on USB. Dropping the link and reconnecting on a
  tap is the fallback, if the measurements say so.
- **A RAM shortfall at rung 2 is a finding, not a reason to stop.** It is journalled, then trimmed (VM heap, BT
  buffers). The board stays the XIAO: moving to the C6 would defeat the purpose.
- **The relay is rete's existing Pixel relay** (in use since rete #439). Its throughput for 32 kbit/s of audio
  is measured at rung 6.
- **ktau builds through ztoit's tree:** the Toit app is a container passed to the ztoit build (`-DCONTAINERS=`), and
  the board files and primitives are ztoit commits. ktau holds the app source, not a copy of the SDK.
- **The IMU interrupt pin** is found from the backported devicetree at rung 3. If it isn't wake-capable, that is a
  journal finding.

## Left to the builder

- How audio is split into datagrams, and how the end of an utterance is marked.
- The LC3 frame size and bit rate. Start at 16 kHz, 32 kbit/s, and let the measurements tune it.
- Board file details (pinctrl, flashing method), found at rung 1 from Seeed's material.
- How the journal entries are laid out.

## Addendum, 2026-11-22: the reply path goes over Thread (#6)

- **David prefers Thread to the phone relay** for the speech reply (#6), so the device works anywhere in the house
  without a phone, provided Thread carries the audio both ways.
- **Measured, one hop** (#6, comment of 2026-11-22; `app/thread_bench.toit`, `tools/thread_bench_server.py`): it
  does, one direction at a time, in rung 7's 100 ms datagrams, and only with the node rx-on-when-idle. As ztoit
  attaches it (sleepy, polling) the downlink is under the audio rate: ztoit #53.
- **Follows from the numbers:** the exchange is talk, then reply, never both at once at 32 kbit/s; datagrams stay
  at 100 ms of audio (smaller ones lose more).
- **Not yet measured:** more than one hop, other rooms, LC3 decode time on the board.

## Addendum, 2026-11-23: on-board speech sketch (#6)

- David asked for the device to speak on its own, at lower quality if need be. Claude's sketch of an LPC diphone
  synth is in `2026-11-23-on-board-speech-sketch.md`.
- **Adopted** (David, 2026-11-23): it replaces the LC3 reply path. The server sends phonemes with duration and
  pitch; offline the board plays canned LPC phrases. ztoit #53 no longer blocks the reply.

## Addendum, 2026-11-25: rung 8, the spoken answer (#6)

Decided by David at the bench; the record of the day is `docs/journal/08-spoken-answer.md`.

- **Rung 8 is in the demo:** the reply carries phones and the board speaks them. `say` and `none` are both spoken,
  one sentence of at most 15 words (the prompt in `server/act.py`); a reply is one datagram (`MAX_WIRE`).
- **Two links, one at a time:** Thread at home, or a phone's BLE relay and the tailnet. The firmware is built with
  one; the app is the same (`app/rung8.toit`, `app/rung8ble.toit`).
- **The server is one machine,** the z170: the receiver, Whisper `small.en` on the smaller GPU with a CPU fallback,
  and the LLM on localhost. The LAN hop from the border router is plain UDP, as the post's security table says;
  moving it onto the tailnet was looked at and left.
- **A clip is at most 30 s** (`MAX-BLOCKS`; `MAX_BLOCKS` is the server's guard).
- **A fatal error restarts the board** (`CONFIG_RESET_ON_FATAL_ERROR`), a workaround for #7, not a fix.
