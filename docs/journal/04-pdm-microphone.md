# 04 — The microphone, from Toit

Rung 4, 2026-11-19.

## What we set out to do

Record the XIAO's PDM microphone from Toit and play the recording back on the host. Zephyr's C sample for the
microphone is the first check. The clip is held in memory and then printed on the console, because the console at
115200 baud is slower than the audio. Streaming waits for LC3 (rung 5) and BLE (rung 6).

## What it took

- **Wall time:** about an hour from the C sample to the last clip, plus the plan written before it. Much of it was
  at the bench: speaking, tapping, listening to the playback.
- **Tokens (Claude Code):** 111 messages, 68 k output, 272 k cache-write, 15.8 M cache-read, from `tools/tokens.py
  2026-11-20T04:23:07Z 2026-11-20T05:21:34Z` (execution only).
- **New in ztoit:**
  - Three microphone primitives (about 100 lines of C): start (format and gain), read one block without waiting, and stop.
    They work with any Zephyr `dmic` device found by its devicetree label.
  - `zephyr.Microphone` in Toit (42 lines): `start`, `read` (one 100 ms block), `stop`, and `--gain-db`.
  - Board conf: 2 settings (`CONFIG_AUDIO`, `CONFIG_AUDIO_DMIC`). No overlay change: the board already
    describes the microphone (`pdm20`).
- **The Toit program:** `app/rung4.toit` (27 code lines): after a tap, it records 1.5 s while the LED is lit, then
  prints the clip. On the host, `tools/clip2wav.py` (51 lines, with tests) turns the console log into WAV files.

## What broke

1. **The first block after a start is the filter settling:** its peak is about 14900 in a quiet room, in the C
   sample and in Toit alike. Toit drops it. The level keeps falling for a few hundred ms after that.
2. **Falling behind stops the microphone without an error.** When its 4 blocks are all full, Nordic's driver stops
   the PDM, but `dmic_read` reports nothing; it just never returns another block.
   - **Fix:** `Microphone.read` throws `MICROPHONE_STOPPED` when no block arrives for a second. The break-check
     (printing each block while recording) gets 4 blocks, then that exception.
3. **Stopping takes a moment.** The driver stops at the end of the current block, and until then it refuses to be
   set up again. `mic_start` returns false while it is busy, and `start` tries again every 10 ms.
4. **Two seconds didn't fit.** A 2 s clip (64000 B) ran out of the 80 KB Toit heap (`ALLOCATION_FAILED`). The clip is
   now 1.5 s. The heap stays the same size: rungs 5 and 6 need the RAM, and streaming does away with the stored clip.
5. **The first clips were too quiet.** The gain started at the hardware default. David heard his voice, but faintly.
   `--gain-db` was added and measured (below), and the demo now uses +10 dB.
6. **The host compiler has its own list of primitives.** New primitives also need an entry in the compiler's
   type table, or `toit.compile` fails to link.
7. **Handling the board counts as taps.** Picking it up gave 5 extra clips. Resting on the bench, it gave one clip
   per tap. Taps during recording and printing are cleared, not queued.

8. **A new owner found the last one's leftovers.** The code review found that `start` didn't clean up after a
   recording that ended without `stop` (a program that died, say). The next start had only 2 free blocks and stopped
   after 3 of 15. Starting twice also broke the next read (3 of 5).
   - **Fix:** `start` takes the microphone over: it stops whatever is running and frees every leftover block first,
     and throws `MICROPHONE_BUSY` if the driver isn't ready within a second. Rerun: 15 of 15, and 5 of 5.

## Evidence

The C sample (`samples/drivers/audio/dmic`), with a print of each block's peak added: about 60 to 430 in a quiet
room, and 2000 to 7200 while David spoke, on the left channel. In the stereo run the right channel copies the left,
so there is one microphone, and Toit records the left channel.

The Toit probe: 20 recordings in a row, each 10 blocks and 32000 B, so stopping and starting again works. The peak
was about 340 in quiet and up to 19887 while David talked close to the board. Opening `i2c30` as a microphone throws
`WRONG_OBJECT_TYPE`.

Gain, with David counting aloud and a spoken cue before each phase. Each cell is two 1.5 s recordings:

| Gain | Quiet RMS | 10 cm RMS (peak) | 1 m RMS |
|---|---|---|---|
| 0 dB | 71–141 | 286–337 (1880) | 132–146 |
| +10 dB | 244–254 | 751–1595 (8065) | 319–514 |
| +20 dB | 755–827 | 2073–4653 (18558) | 1190–1320 |

The gain raises the noise as much as the speech. At 1 m, speech is only 1.5 to 2 times the noise at any gain, so the
gain only decides the headroom. +10 dB leaves about 12 dB of headroom at 10 cm. A shout at 10 cm could still clip.
A gain that adjusts itself is left out: the receiver (rung 7) can even out the level of a whole utterance at no cost
to the device. How speech-to-text copes with a speaker 1 m away is a question for rung 7.

The demo at +10 dB: one tap, then a 1.5 s clip.

```
clip 1: 1.5 s peak=6612 rms=1176
```

Played back on the host, David heard his voice: "quality 70%".

Console speed, for information: the console runs cleanly at 921600 baud (2000 of 2000 test lines intact, about
81 KB/s). That is about twice what raw audio in base64 needs (about 43 KB/s), so the console could carry a live
stream. It stays at 115200; streaming will go over BLE, after LC3.

## Sizes

| Build | FLASH | RAM (static) |
|---|---|---|
| C sample `dmic` | 53468 B | 85752 B |
| ztoit + `rung3.toit` (rung 3) | 273708 B | 115632 B |
| ztoit + `rung4.toit` | 277176 B | 128464 B |

12800 B of the new RAM is the driver's 4 blocks of 100 ms. The C sample's RAM is mostly its own capture buffer.

## Toit vs C

| | C sample `dmic` | Toit `rung4.toit` |
|---|---|---|
| Source | 154 lines (109 code) | 27 code lines, plus the 42-line `Microphone` |
| Blocks | `dmic_read` waits for one; the caller frees it | `read` returns a ByteArray; nothing to free |
| Falling behind | the driver stops quietly | an exception, `MICROPHONE_STOPPED` |
| Which device | fixed at build time (devicetree alias `dmic0`) | a label at run time; a wrong one throws `WRONG_OBJECT_TYPE` |

**What went into C this rung, and why:**
- The `dmic` calls and the block pool. Zephyr's API wants a static memory slab, and a block has to go back to it
  as soon as it is read. The C copies each block into a Toit ByteArray and frees it straight away.
- Nothing about the board or the use: the primitives take any `dmic` device. The format (16 kHz, 16-bit, mono, 100 ms)
  is fixed in C for now, because rung 5's LC3 encoder wants 16 kHz. The gain is set from Toit.

**The read polls.** `read` asks every 10 ms while recording. It is the simple first version. Waiting for a tap is
still event-driven, so the board polls only while it is recording. Rung 8 measures whether recording needs an
event-driven read.
