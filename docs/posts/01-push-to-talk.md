# Push to talk: Toit on Zephyr → tailnet → LLM, and back

Draft, 2026-11-21. Raw material: `docs/journal/01`–`07`.

Hold the button on a thumb-sized board and say "remind me to buy milk". About three seconds after you let go, the
LED blinks twice and the note is on a machine at home. The board is a Seeed XIAO nRF54L15 Sense. The program on it
is 62 lines of [Toit](https://toitlang.org), running on Zephyr through [ztoit](https://github.com/davidg238/ztoit).

## The chain

```
 nRF54L15 │ button      held: LED on, record   │  LED
 (Toit)   │   ↓                                │   ▲  2 short: acted
          │ PDM mic     Zephyr's dmic driver   │   │  1 long: not acted
          │   ↓         a block every 100 ms   │   │
          │ LC3         liblc3: 400 B a block  │   │
          │   ↓                                │   │
          │ UDP/BLE     one L2CAP channel      │   │
──────────┼────────────────────────────────────┼───┼──────────────────
 tailnet  │ Pixel       rete's Android relay   │   │
          │   ↓                                │   │
          │ Tailscale                          │   │
──────────┼────────────────────────────────────┼───┼──────────────────
 server   │ receiver    reassembles the clip   │   │
          │   ↓                                │   │
          │ Whisper     speech to text         │   │
          │   ↓                                │   │
          │ LLM         on another tailnet     │   │
          │             host: note/say/none    │   │
          │   ↓                                │   │
          │ reply ─────────────────────────────┼───┘ one byte
```

- **The board** sends an END on release, then waits up to 30 s for the reply; no reply is 5 fast blinks.
- **The relay** holds a bonded link to the board and puts its datagrams on the tailnet. To the board it is just a
  network.
- **The receiver** is about 200 lines of Python. It evens out the level before Whisper, and the LLM may only pick
  from an allowlist of actions: `note`, `say` or `none`.

At the bench: 4 of 4 phrases acted as meant, a silent clip answered "no speech", and with the receiver stopped the
board gave up after 30 s and carried on. No audio block was lost. Release to blink took 2.9–3.3 s, and 2.7 s of
that is Whisper on the CPU.

## What went into C, and what stayed in Toit

The rule for the whole project was: the application stays in Toit, and C gets only what Toit can't reach. Each new
primitive is generic: it would work on another board with the same kind of device.

| Piece | C (in ztoit) | Toit |
|---|---|---|
| Microphone | 3 primitives over Zephyr's `dmic` API, ~100 lines | `zephyr.Microphone`, 42 lines |
| LC3 | 2 primitives over liblc3, 54 lines | `zephyr.Lc3Encoder`, 30 lines |
| Network | `udp_ble.cc` and rete's BLE transport, ported, ~690 lines | nothing new: `net.open`, `udp-open` |
| Button, LED | none: `gpio-keys` and `led` were already there | `zephyr.Key`, `zephyr.Led` |
| The app | none | 62 lines |

### The microphone: a Zephyr driver, used as it is

The XIAO's microphone is a PDM part, and Zephyr already has a driver behind its generic `dmic` API. So the Toit side
is three small primitives (start with a format and gain, read one block without waiting, stop) and a 42-line
`Microphone` class. They take any `dmic` device by its devicetree label; nothing in them is about this board.

The driver had some edges, and the primitives smooth them over so a Toit program gets an exception, not silence:

- **The first block after a start is the filter settling** (a peak near 15000 in a quiet room). Toit drops it.
- **Falling behind stops the microphone without an error.** When the driver's 4 blocks are full it stops, and
  `dmic_read` simply never returns another block. `read` now throws `MICROPHONE_STOPPED` after a second.
- **Stopping finishes the current block first**, and the driver refuses a new start until then. `start` retries, and
  takes the microphone over from a program that died without stopping it.

Compared with Zephyr's own C sample: 27 lines of Toit against 109 lines of C, no block to free by hand, and the
device chosen at run time rather than fixed at build time.

### LC3

Zephyr ships liblc3 as a module. Two primitives wrap it, and turning on the FPU for it was the main risk: from then on
the whole VM is built for the hardware-float ABI. It linked first time. Encoding takes 12.9 ms per 100 ms block, so
the board spends about 13 % of its time encoding. Through Whisper, the board's one microphone at 32 kbit/s scored the
same as a Bluetooth headset in a quiet room: 5/5 transcripts.

### UDP over Bluetooth LE

This was the hardest rung. The BLE transport came from [rete](https://github.com/davidg238/rete), my embedded fleet system, written in C. `udp_ble.cc` puts
Toit's ordinary `udp` primitives on top of it, beside the existing ones for Wi-Fi and Thread, so a Toit program can't
tell which link it has. What broke:

- the bond lived only in RAM until a settings backend (`CONFIG_ZMS`) was chosen;
- pairing overflowed a Bluetooth work-queue stack, because ztoit's Mbed TLS settings use the general ECC code;
- at Zephyr's default 30–50 ms connection interval the L2CAP receive path, one credit at a time, carried only 34 of
  50 blocks. At 7.5–15 ms it carried 50 of 50, at a median round trip of 75 ms.

A 10 s relay outage lost exactly the 10 s of datagrams, with no exception, and the link was back within a second of
the relay restarting.

## Zephyr 4.2 to 4.5: how hard was the upgrade?

ztoit ran on Zephyr 4.2. The XIAO nRF54L15 board only exists upstream in later releases, so this project moved to
4.5, in its own workspace beside the 4.2 one.

- **The board itself was easy.** Blinky and hello_world from the fresh 4.5 tree worked first time, flashed through
  the XIAO's on-board probe with no J-Link. The only problems were small: a module dropped from the manifest
  (`tinycrypt`), and the new tree needed its own Python venv.
- **The VM took four fixes, all from the move rather than the board,** and the first Toit `print` came 11 minutes
  after the first build:
  1. **Mbed TLS 4.** Zephyr 4.5 ships Mbed TLS 4 on TF-PSA-Crypto, and the headers the VM includes became private.
     The fix is ten forwarding headers and a conf chosen by Zephyr version. The VM sources are unchanged, and 4.2
     builds still use the old conf.
  2. **A name clash:** a Toit argument macro made a variable `_raw_current`, now a 4.5 kernel macro.
  3. **stdio:** 4.5 sends the VM down an `fwrite_unlocked` path that picolibc doesn't have.
  4. **A missing `CONFIG_LED`** in the new board conf.
- **One later cost** came from the same Mbed TLS change: the Bluetooth pairing stack overflow above.

So, not hard: under an hour of hands-on work from a fresh tree to Toit blinking the LED, most of it on Mbed TLS.
The 4.2 tree stays for now. The older boards (ESP32-C6, ESP32-WROOM-32, the nRF52840 dongle) move to 4.5 next, and
ztoit keeps only the one tree (ztoit #47).

## What it costs

| | Flash | RAM (static) |
|---|---|---|
| Zephyr blinky in C | 39 KB | 6.4 KB |
| ztoit, Toit VM, hello | 254 KB | 111 KB |
| The demo: VM, mic, LC3, BLE, app | 518 KB | 172 KB |

Of 1524 KB flash and 256 KB RAM. The Toit heap is 80 KB of that RAM, not yet tuned. liblc3 adds 92 KB of flash, and
Bluetooth 194 KB.

The whole ladder, from an unopened board to this demo, took three days (2026-11-19 to 2026-11-21), with
Claude Code doing the typing: 7 rungs, each with a plan, a demo, a journal entry and a review.

## Not in this demo

- **Battery.** The board runs on USB, and the BLE link is held at a short interval, which costs power. Sleep current
  and current per instruction are later work.
- **Speed.** Whisper on the CPU is 2.7 s of the 3 s; a smaller model or a GPU would cut it.
- **Tool calling.** The LLM picks one of three actions. More actions would earn real tool calling.

A separate short post covers the board's accelerometer, which went the other way: Zephyr's driver couldn't do what
was needed, so the driver is in Toit.
