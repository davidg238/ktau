# On-board speech: an LPC diphone synth on the nRF54L15 (#6)

Status: sketch by Claude, 2026-11-23, for David to check. Nothing here is decided.

## Why

David wants the device as self-contained as practical, accepting lower quality: speech is a great UI. #6 as filed
streams Piper audio from the server as LC3 (32 kbit/s, needs rx-on over Thread, ztoit #53). An on-board synth speaks
with no server, and when the server does help it sends phonemes (tens of bytes), not audio.

## What it sounds like

`tools/lpc_reference.py` turns natural speech into the frames this synth would play, and plays them back the way
the board would: a lattice filter driven by a flat impulse train or noise. Samples are in
`samples/lpc-reference-2026-11-23/` (git-ignored): Piper, then LPC at 8 kHz order 10 (~2.5 kbit/s) with natural
pitch, with rule pitch, and at 16 kHz order 16 with rule pitch. Whisper `small.en` transcribes all three LPC versions
almost word for word ("saves" for "saved" in the first, "Not" for "Note" in the third). This is an **upper bound**:
real diphones add audible joins, and rule prosody loses emphasis. Expect the Speak & Spell to early-DECtalk range.

## The chain

| Step | Where | What |
|---|---|---|
| Text normalisation | Toit | numbers, times, units ("3:20" → "twenty past three") |
| Text → phonemes | Toit | lexicon lookup, letter-to-sound rules for words the lexicon lacks |
| Prosody | Toit | per-phone duration; pitch as declination per phrase, accents on stressed syllables, a rise for questions |
| Diphone lookup | Toit | phone pair → frame run in the diphone table, stretched or squeezed to the duration |
| Synthesis | C primitive | per sample: interpolate parameters, pulse or noise, lattice filter; 16-bit PCM to I2S |
| Output | Zephyr I2S | MAX98357A, as #6 already plans |

The split follows the anti-goal: the language work is in Toit, where it reads well, and only the per-sample loop
is C (it runs 8,000–16,000 times a second). The journal records why that loop is C.

## The diphone table

- **Source:** an existing, freely licensed diphone voice, for example the CMU kal diphones that Festival and Flite
  use, re-encoded to LPC frames by an offline tool on msi. **Check the licence before anything derived from it
  goes in the public repo.** Fallbacks: David records the ~1,800 nonsense carrier words himself (about an hour,
  and a good post), or diphones cut from Piper output (also needs a licence check on the voice).
- **Frame:** 22.5 ms; reflection coefficients (k1, k2 as log-area ratios), pitch, gain, voicing; ~56 bits at order
  10, ~74 at order 16 (`lpc_reference.py`'s quantiser).
- **Size (estimate):** ~1,800 diphones × ~0.1 s ≈ 3 minutes ≈ 8,000 frames ≈ 56 KB at order 10, ~75 KB at order 16.
  Flash isn't the constraint.

## The lexicon

- **Estimate:** the commonest 10–20k words of CMUdict, packed (prefix-shared, 5-bit phones) at roughly 100–200 KB,
  plus the NRL letter-to-sound rules (a few KB) for the rest. Measure the miss rate on the LLM's actual replies
  before sizing it.

## Budget (estimates, to measure)

| | Estimate |
|---|---|
| Flash | diphones ~60–80 KB, lexicon ~100–200 KB, code ~20 KB |
| RAM | synth state < 1 KB; I2S double buffer 2 × 20 ms at 16 kHz ≈ 1.3 KB |
| CPU | order-16 lattice at 16 kHz ≈ 0.5 M multiply-adds a second: a few percent of the 128 MHz M33 |

## The wire seam with the server

When the LLM writes the reply, the server sends **phonemes with stress marks** (ARPAbet, ~2 bytes a phone): a
sentence fits in one datagram of under 404 B. The #6 bench lost 0% of 404 B downlink datagrams with ztoit's
sleepy defaults, so speech replies no longer need ztoit #53's rx-on. Phonemes in also mean the board's lexicon can
come later. The LC3 path stays for when quality matters more than independence.

## A ladder

| Step | Demo |
|---|---|
| S1 | Host: `lpc_reference.py` (done, the samples above) |
| S2 | Board: a fixed LPC frame stream in flash plays through I2S and the MAX98357A; the C primitive measured |
| S3 | Host: diphone table built from the source voice; a host synth speaks phoneme strings (tune the joins here) |
| S4 | Board: phonemes from the server over Thread → speech |
| S5 | Board: text → speech with the on-board lexicon and rules; device messages ("battery low") with no server |

## Open

- The diphone voice's licence; whether its voice (kal is a male US speaker, recorded 1990s) is acceptable.
- Joins: interpolate log-area ratios or line spectral pairs across a boundary; LSPs interpolate more safely.
- Cheap quality steps if wanted: mixed excitation (a voicing decision per band, as MELP does). Not a shaped glottal pulse: the LPC filter already carries the tilt, and adding it twice muffled the first samples.
- I2S on the XIAO's pins (#6's unchecked list).
