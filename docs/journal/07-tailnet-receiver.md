# 07 — Tap, speak, act: the receiver on the tailnet

Rung 7, 2026-11-21.

## What we set out to do

Close the loop. Hold the button and speak; the board streams LC3 through the Pixel's BLE relay to a receiver on the
tailnet, which transcribes it, asks an LLM for one action, carries it out and replies; the board's LED says how it
went. The design asked for a small script first, levels evened out at the receiver rather than by gain on the device,
and clips Whisper marks as no speech dropped.

## What it took

- **Wall time:** about 1 h 20 min from the plan to the last bench press, about 10 min of it at the bench.
- **Tokens (Claude Code):** 62 messages, 48 k output, 235 k cache-write, 6.9 M cache-read, from `tools/tokens.py
  2026-11-21T19:48:49Z` (to the bench's end).
- **New in ztoit:** nothing. The board side is one Toit program over rung 5's and rung 6's primitives.
- **The Toit program:** `app/rung7.toit` (62 code lines): push to talk, each 100 ms block encoded and sent as it is
  read, an END datagram, a 30 s wait for the reply, and the LED.
- **The receiver** (Python, stdlib plus faster-whisper; code lines without comments):
  - `server/clips.py` (64): the wire and clip reassembly;
  - `server/act.py` (46): the LLM call and the action allowlist;
  - `server/receiver.py` (90): decode, normalise, Whisper, the LLM, the action, the reply;
  - `tools/sendclip.py` (70): sends an audio file exactly as the board does, so the receiver was proven before the
    bench;
  - tests: 187 lines, 19 tests, all on the host.
- **The LLM:** a llama.cpp server already running on another machine on the tailnet (Qwen3.6-35B-A3B, a
  mixture-of-experts model, 4-bit), OpenAI-compatible. It was published to the whole tailnet with `tailscale serve`,
  without restarting it. Thinking is off and the answer is constrained to JSON.

## The wire

UDP, big-endian, one datagram per 100 ms of audio (400 B of LC3 at 32 kbit/s, rung 5's rate):

| Datagram | Layout |
|---|---|
| audio | `clip:u16 \| seq:u16 \| 400 B LC3` |
| end | `clip:u16 \| 0xFFFF \| blocks:u16`, sent 3 times, 50 ms apart |
| reply | `clip:u16 \| status:u8`: 0 acted, 1 no speech, 2 failed |

A clip ends on its END, when the same sender starts another clip, or after 1.5 s of silence (all three ENDs lost).
A lost block becomes 100 ms of silence. The board starts its clip numbers at random, so a reboot doesn't reuse a
number the receiver has just finished.

The LED, the board's only user LED: lit while recording; 2 short blinks acted; 1 long blink no speech or failed; 5
fast blinks no reply in 30 s.

## What broke

1. **The first build failed at CMake:** `TOIT_SRC is not set`. The ztoit build needs its `env.sh` sourced; the rung 6
   recipe had it in the shell already. Not a code change, but a missing line in the recipe.
2. **The plan had a wrong number:** a lost block's silence as "320 samples a frame". A 10 ms frame at 16 kHz is 160
   samples; a lost block is 1600. The test caught it before any code was written.

Nothing broke on the board or the relay.

## Evidence

First on the host, from `tools/sendclip.py` (2.5 s of "turn on the kitchen lights"):

| Case | Result |
|---|---|
| Clean | ACTED, `none "I cannot control the lights."` |
| Block 3 dropped | `(1 lost)`, same transcript, ACTED |
| No END | ACTED, about 1.1 s later (the idle timeout) |
| 2 s of silence | NO-SPEECH, no-speech probability 0.83, no LLM call |
| LLM unreachable | FAILED, the receiver carries on |
| Sent from another tailnet host | ACTED in 3.3 s |

Then the bench (2026-11-21 14:04), the board held at the mouth:

```
clip 827 from …: 25 blocks (0 lost) | stt 2.7 s "Remind me to buy milk." nsp=0.03 | llm 0.4 s note "Buy milk" | ACTED
clip 828 from …: 40 blocks (0 lost) | stt 2.9 s "Note that the boiler service is due Tuesday" nsp=0.01 | llm 0.4 s note "Boiler service is due Tuesday" | ACTED
clip 829 from …: 28 blocks (0 lost) | stt 2.6 s "Say hello to David." nsp=0.02 | llm 0.3 s say "Hello, David!" | ACTED
clip 830 from …: 28 blocks (0 lost) | stt 2.6 s "turn on the kitchen lights" nsp=0.02 | llm 0.4 s none "I cannot control the lights." | ACTED
clip 831 from …: 31 blocks (0 lost) | stt 2.7 s "" nsp=1.00 | NO-SPEECH
```

and on the board:

```
clip 827: 25 sent, reply 0 in 3283 ms
clip 828: 40 sent, reply 0 in 3301 ms
clip 829: 28 sent, reply 0 in 3174 ms
clip 830: 28 sent, reply 0 in 3239 ms
clip 831: 31 sent, reply 1 in 2862 ms
clip 833: 23 sent, reply none in 30152 ms
```

- 5/5 phrases transcribed and acted as meant; both notes are in the notes file, and "Hello, David!" was spoken on the
  receiving machine.
- No block lost in any clip.
- **Release to blink: 2.9–3.3 s.** Whisper `medium.en` on the CPU takes about 2.7 s of that whatever the clip's
  length; the LLM takes 0.3–0.5 s. Whisper is the place to look for speed.
- Clip 833 was sent with the receiver stopped: 5 fast blinks after 30 s, and the board carried on.

## Sizes

| Build | FLASH | RAM (static) |
|---|---|---|
| ztoit + `rung6.toit` (rung 6) | 559800 B | 175880 B |
| ztoit + `rung7.toit` | 530124 B | 175880 B |

## Toit vs C

There is no Zephyr C sample for this rung: the work is on the receiver. On the board, rung 7 is rung 5's push to talk
with rung 6's socket in one 62-line program, and nothing new went into C. The wire's bytes are built in Toit with
`ByteArray` literals, and the reply wait is `with-timeout` around `receive`.

## Left

- Whisper's 2.7 s: a smaller model, or the GPU machine, would cut it. Not needed for the demo.
- Real tool calling, if a fourth action earns it (the design: "if it earns its place").
- Rung 8: battery, sleep current, and current per instruction.
