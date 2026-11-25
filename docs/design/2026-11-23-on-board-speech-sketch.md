# On-board speech: an LPC diphone synth on the nRF54L15 (#6)

Status: sketch by Claude, 2026-11-23; **adopted by David the same day** (the two modes below, S1–S4).

## Why

David wants the device as self-contained as practical, accepting lower quality: speech is a great UI. #6 as filed
streams Piper audio from the server as LC3 (32 kbit/s, needs rx-on over Thread, ztoit #53). An on-board synth speaks
with no server, and when the server does help it sends phonemes (tens of bytes), not audio.

## What it sounds like

`tools/lpc_reference.py` turns natural speech into the frames this synth would play, and plays them back the way
the board would: a lattice filter driven by a flat impulse train or noise. Samples are in
`samples/lpc-reference-2026-11-23/` (git-ignored): Piper, then LPC at 8 kHz order 10 (~2.5 kbit/s) with natural
pitch, with rule pitch, and at 16 kHz order 16 with rule pitch. Whisper `small.en` transcribes all three LPC versions
word for word. David's ear (2026-11-23): **8 kHz with natural pitch sounds best** — real pitch outweighs the extra
treble of 16 kHz. This is an **upper bound**: real diphones add audible joins. Rule pitch sounds flat and monotone.

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
| Flash | diphones ~60–80 KB, canned phrases ~30 KB, code ~20 KB (lexicon ~100–200 KB only if S5) |
| RAM | synth state < 1 KB; I2S double buffer 2 × 20 ms at 16 kHz ≈ 1.3 KB |
| CPU | order-16 lattice at 16 kHz ≈ 0.5 M multiply-adds a second: a few percent of the 128 MHz M33 |

## Two modes: server prosody online, canned speech offline

Natural pitch is what makes the 8 kHz sample sound best, and a diphone synth cannot invent it. So:

- **Server reachable:** the server runs Piper's front end and sends, per phone, the phoneme, its duration and a
  pitch target or two (~4 bytes a phone; a sentence still fits one 404 B datagram). The board only looks up
  diphones and synthesises: close to the natural-pitch sample. No lexicon or prosody rules on the board.
- **No server:** the board has no LLM reply to speak anyway; it only says its own things ("can't reach the
  server", "battery low", the time) — the Echo pattern. Store those as **canned LPC phrases** encoded from Piper
  with natural pitch: ~300 B a second, so 50 phrases of ~2 s ≈ 30 KB. Numbers and times by joining canned word
  clips, as talking clocks do.

This drops the on-board lexicon, letter-to-sound rules and rule prosody (~100–200 KB, and the hardest Toit work)
unless a need for free text with no server turns up.

## The wire seam with the server

When the LLM writes the reply, the server sends **phonemes with duration and pitch** (~4 bytes a phone, above): a
sentence fits in one datagram of under 404 B. The #6 bench lost 0% of 404 B downlink datagrams with ztoit's
sleepy defaults, so speech replies no longer need ztoit #53's rx-on. Phonemes in mean the board needs no lexicon. The LC3 path stays for when quality matters more than independence.

## A ladder

| Step | Demo |
|---|---|
| S1 | Host: `lpc_reference.py` (done, the samples above) |
| S1b | Host (done): the frame format in `tools/lpc_codec.py` (55 bits a frame, ~300 B a second); the integer synth `c/lpcsynth/` matches its Python model sample for sample (`tools/test_lpc_codec.py`); `lpc_codec.py phrase` makes canned phrases |
| S2 | Board: a canned LPC phrase in flash ("can't reach the server") plays through I2S and the MAX98357A; the C primitive measured. This alone is the offline mode |
| S2 status | Done on the bench 2026-11-24: `c/phrasecheck` plays the three canned phrases from flash (312–711 B each); David: "a little robotic, but quite clean". The synth costs about 46 ms of CPU a second of speech. I2S must run at 16 kHz on the crystal with `i2c22` disabled (`docs/hookup.md`). Still to do: the Toit primitive (ztoit) |
| S3 | Host: diphone table built from the source voice; a host synth speaks phoneme strings (tune the joins here) |
| S4 | Board: phonemes + duration + pitch from the server over Thread → speech |
| S5 | Only if needed: free text with no server (on-board lexicon, letter-to-sound, rule prosody) |

## Open

- The diphone voice's licence; whether its voice (kal is a male US speaker, recorded 1990s) is acceptable.
- Joins: interpolate log-area ratios or line spectral pairs across a boundary; LSPs interpolate more safely.
- Cheap quality steps if wanted: mixed excitation (a voicing decision per band, as MELP does). Not a shaped glottal pulse: the LPC filter already carries the tilt, and adding it twice muffled the first samples.
- I2S on the XIAO's pins (#6's unchecked list).

## Addendum 2026-11-24: LC3 heard next to LPC on the board

`c/lc3play` plays "I can't reach the server" three ways through the MAX98357A, level-matched, same TTS source.

| Version | Blob | CPU a second of speech | Worst 20 ms block | David, three listens |
|---|---|---|---|---|
| LPC (this sketch) | 438 B | 47 ms | 1.0 ms | "a little robotic, but quite clean" |
| LC3 16 kbit/s | 3120 B | 49 ms | 1.2 ms | "very good" |
| LC3 32 kbit/s | 6240 B | 54 ms | 1.3 ms | "very good", not told apart from 16 |

- LC3 costs no more CPU than LPC; the price is size, 2 KB a second at 16 kbit/s against about 0.3 KB.
- Proposed, not yet decided: canned phrases as LC3 at 16 kbit/s (50 phrases of 2 s ≈ 200 KB). LC3 cannot serve
  the phoneme path (no pitch or duration to control); for S3 compare waveform or residual-excited diphones with
  plain LPC by ear before choosing.
- Log: `samples/lc3play-2026-11-24.log`; host copies, with a 24 kbit/s one and the original, in
  `samples/lc3-phrases-2026-11-24/` (both git-ignored).

## Addendum 2026-11-24: residual-excited LPC heard on the board

David wants unlimited phrases, so the phoneme path has to sound better than plain LPC. `tools/relp_reference.py`
keeps the LPC filter and plays the voice's own residual through it (3 bits a sample, a gain per 10 ms);
`c/pcmplay` plays its clips through the MAX98357A.

| Clip | Stored size | David |
|---|---|---|
| 1 plain LPC, 8 kHz order 10 | 0.3 KB a second | baseline |
| 2 residual-excited, 8 kHz order 10 | 3.7 KB a second | |
| 3 residual-excited, 16 kHz order 16 | 6.7 KB a second | "the best" |
| 4 clip 3 with pitch ×1.15, duration ×1.2 (overlap-add of the residual) | as 3 | |

- David's ear, three listens: clip 3 best; clip 2 "90+%" of clip 3; clip 4 "85%" of clip 3.
- **Decided (David, 2026-11-24): the demo starts from clip 2** — residual-excited LPC at 8 kHz, order 10, 3 bits a
  sample. It replaces plain LPC as the synth for the phoneme path. The demo uses standard modules; it is not
  tuned for the best voice.
- **For the write-up:** say how to improve it and let readers hear what a little flash buys: publish clips 1 to 4
  side by side with their sizes (plain LPC 0.3, 8 kHz residual 3.7, 16 kHz residual 6.7 KB a second), and the
  LC3 clips above for canned speech. Check the TTS voice's licence before publishing any clip.
- Cost: a diphone set of about 3 minutes is roughly 0.7 MB at clip 2's rate, 1.2 MB at clip 3's; the chip has
  1524 KB in all. Untried: 2 bits a sample, a decimated residual.
- Open: the diphone source and its licence (above); how joins sound; the price of moving pitch at 8 kHz (clip 4
  was made at 16 kHz).
- Next: a frame format and an integer C synth for clip 2, checked against the Python model as `c/lpcsynth` is.

## Addendum 2026-11-24: diphone voice licences (first look, not legal advice)

| Source | Terms as found | For a public repo |
|---|---|---|
| CMU kal diphones, as shipped in Flite | Flite's CMU licence: use, modify, distribute and sell, keeping the copyright notice and authors' names, marking modifications (`/usr/share/doc/libflite1/copyright`, kal is not among its exceptions) | usable, with the notice |
| Pieces cut from the TTS voice in use (Piper `en_US-lessac-medium`) | the voice is trained on the Blizzard 2013 Lessac data, reported as research / non-commercial; the dataset licence text itself was not read | no: cutting the output into diphones does not change whose voice it is |
| Pieces cut from Piper `en_US-ljspeech` | model card: LJ Speech, public domain | usable; a different, female voice; not installed here |
| David's own recording | his | usable |

- Heard on the board (`c/pcmplay`): Flite speaking the test phrase with kal at 8 and at 16 kHz, after our 8 kHz
  residual clip. Flite's kal is itself a residual-excited LPC diphone synth, so it previews the technique with
  its joins. Clips: `samples/kal-2026-11-24/`.
- **Decided (David, 2026-11-24): build the diphones from CMU kal.** Heard three times on the board: "fine for a
  limited flash demo". Keep CMU's copyright notice and authors' names with anything derived from it.
