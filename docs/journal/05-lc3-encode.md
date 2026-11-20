# 05 — LC3, from Toit

Rung 5, 2026-11-20.

## What we set out to do

Encode the microphone's audio as LC3 on the XIAO, from Toit, and decode it on the host. Measure the clip size and the
encode time. Zephyr has a `liblc3` module but no standalone sample for it, so the first check is a small C program
of our own (`c/lc3check`). Streaming over BLE is rung 6.

## What it took

- **Wall time:** about 35 minutes from the plan to the last clip, plus about 10 minutes at the bench.
- **Tokens (Claude Code):** 60 messages, 44 k output, 71 k cache-write, 9.0 M cache-read, from `tools/tokens.py
  2026-11-20T18:46:15Z 2026-11-20T19:20:05Z` (execution only).
- **New in ztoit:**
  - Two LC3 primitives (54 lines of C): set up the one encoder at a bit rate, and encode whole 10 ms frames.
  - `zephyr.Lc3Encoder` in Toit (30 lines): `--bitrate` (32 kbit/s by default), `frame-bytes`, `encode`.
  - Board conf: 3 settings (`CONFIG_FPU`, `CONFIG_FPU_SHARING`, `CONFIG_LIBLC3`).
- **The Toit program:** `app/rung5.toit` (34 code lines): push to talk. Holding the user button records, with the
  LED lit; each 100 ms block is encoded as it is read; on release, or after 5 s, the clip is printed. On the host,
  `tools/lc3dec.py` (90 lines, with tests) decodes the console log to WAV files with liblc3's own Python binding.
- **The trigger changed from a tap to a button.** Handling the board set off taps (journal 04), and the tap
  threshold is already as low as it goes. The user button is a `gpio-keys` device, so `zephyr.Key` reads it with no
  new C. The tap stays for later, perhaps as a double tap.

## What broke

1. **The FPU was off.** liblc3 needs it, and the XIAO build had never turned it on. Turning it on (with FPU sharing
   between threads) was the rung's main risk: the whole VM is compiled for the hardware-float ABI from then on.
   - **Check:** the probe printed `2.0.sqrt` before and after encoding: `1.414213562373095` both times. The build
     linked first time.
2. **A bad bit rate was accepted.** `lc3_frame_bytes` clamps an out-of-range bit rate to the nearest valid frame
   size instead of failing, so the first range check could never fire. The break-check caught it (`--bitrate=1000`
   gave a working encoder).
   - **Fix:** the primitive checks the bit rate against liblc3's `LC3_MIN_BITRATE` and `LC3_MAX_BITRATE` itself.
3. **An older encoder kept encoding after a newer one took over** (found in review). There is one encoder state, so
   a second `Lc3Encoder` at 64 kbit/s made the first one return 80-byte frames while its `frame-bytes` still said 40.
   - **Fix:** each setup gets a new generation; an older encoder's `encode` throws `ALREADY_CLOSED`, like a
     microphone taken over by a new `start`.

**What went into C this rung, and why:**
- The codec. It is liblc3, as Zephyr ships it, and Toit calls it once per 100 ms block.
- The encoder's state (2600 B), held static, like the microphone's block pool. There is one encoder; a new
  `Lc3Encoder` takes it over.
- **Stack:** liblc3 used 3464 B of stack in the C check. A Toit interpreter thread has 8 KB, so the margin is
  about 4.5 KB less the FPU's saved registers. Zephyr's stack guard would fault an overrun rather than let it
  corrupt memory.

## Evidence

The C check, a 440 Hz sine encoded on the XIAO at 32 kbit/s and decoded on msi:

```
lc3check: encoder-mem=2600 frame-bytes=40 enc-us min=1179 avg=1284 max=1380 stack-used=3464 of 8192
clip 1: 1 s peak=17998 rms=12627 f0=440
```

The same sine from Toit: `blocks=10 bytes=4000`, 12.9 ms per 100 ms block, decoded at f0=440.

At the bench, the board held 3–5 cm from the mouth, the same phrase five times, then once silent. Every block was
encoded in 12.5–12.9 ms on average (14.2 ms at most), so encoding takes about 13 % of the time and recording never
fell behind. Peaks reached 18205 of 32767 at +10 dB, so the gain stays.

Then the same phrase five times on a Bluetooth headset (Android's recorder), and every clip through Whisper
`medium.en` on msi:

| | Transcripts | Mean log-probability | Speech RMS |
|---|---|---|---|
| Headset | 5/5 "turn on the kitchen lights" | −0.41 to −0.47 | −35 to −24 dBFS |
| XIAO, LC3 at 32 kbit/s | 5/5 "turn on the kitchen lights" | −0.44 to −0.54 | −29 to −25 dBFS |
| XIAO, silent clip | "you" (no-speech probability 0.89) | −0.95 | |

Held close in a quiet room, the board's one microphone through LC3 is about as good as the headset for
speech-to-text. The headset's noise cancelling matters in noise, which this test didn't have. Whisper makes up a word
for a silent clip, so rung 7's receiver drops a clip whose no-speech probability is high.

## Sizes

| Build | FLASH | RAM (static) |
|---|---|---|
| C check `lc3check` (with a 32 KB sine buffer) | 137756 B | 53016 B |
| ztoit + `rung4.toit` (rung 4) | 264504 B | 128464 B |
| ztoit + `rung5.toit` | 360912 B | 131400 B |

liblc3 adds about 92 KB of flash. RAM grows by 2.9 KB, mostly the encoder state.

A clip is 4000 B per second at 32 kbit/s, against 32000 B of PCM. The 5 s limit is the demo's choice now, not the
heap's: rung 4 ran out of heap at 2 s.

## Toit vs C

| | C check `lc3check` | Toit `rung5.toit` |
|---|---|---|
| Source | 52 lines (47 code), a sine only | 34 code lines, button, microphone and LC3 |
| Encoder state | the caller declares the memory and sets it up | `Lc3Encoder`; the memory is inside ztoit |
| Frames | one call per 10 ms frame | one call per 100 ms block; frames come back to back |
| Bad input | undefined | `INVALID_ARGUMENT` for a cut frame or a bad bit rate |
| Time per 10 ms of audio | 1.28 ms | 1.29 ms |
