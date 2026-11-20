# Rung 5: an LC3 encode primitive; clip size and encode time measured — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toit encodes the microphone's PCM as LC3 while it records, a host script decodes the clip to a WAV that
plays on msi, and the journal records clip size, encode time and RAM. Journal entry 5 records it.

**Architecture:**
- **The encoder:** one primitive group over Zephyr's `liblc3` module, with one static encoder in `zephyr.cc` under
  `CONFIG_LIBLC3`, like the microphone's static slab. Fixed format from the design: 16 kHz, 10 ms frames
  (160 samples, 320 B of PCM); bit rate set at setup, starting at 32 kbit/s (`lc3_frame_bytes` gives 40 B).
  Setting up again resets the one encoder; this is the microphone's "start takes over" rule.
- **One call per block:** `lc3_encode` takes a whole 100 ms block (10 frames) and returns the frames back to back.
  Frames are a fixed size, so the receiver splits them without framing.
- **Push to talk:** the board's user button (`usr_btn`, a gpio-keys child, so `zephyr.Key` with no new C) is held
  while speaking; the LED is on while the record window is open. The IMU tap was too easily set off by handling
  (journal 04, item 7; its threshold is already at 2 of 31), so it is left for later (David, 2026-11-20).
- **Encode while recording:** the demo encodes each block as it is read, so it has the shape rung 6's streaming
  needs. The stored clip is now LC3: at 32 kbit/s, 5 s is 20 KB, against the 48 KB of PCM that capped rung 4 at 1.5 s.
- **liblc3 needs the FPU,** which the XIAO build has off today. `CONFIG_FPU=y` and `CONFIG_FPU_SHARING=y` go into
  the board conf. This is the rung's main risk (Review Focus 1).
- **The C check first:** Zephyr has no standalone liblc3 sample (only Bluetooth audio ones), so ktau gets a small C
  app, `c/lc3check`, that encodes a generated 440 Hz sine and prints sizes and times.
- **Host decoding:** liblc3's own `python/lc3.py` over a host build of `liblc3.so` from the same module source.

**Tech Stack:** Zephyr v4.5.0, SDK 1.0.1, liblc3 (`~/zephyr-4.5/modules/lib/liblc3`, Kconfig `CONFIG_LIBLC3`),
the Toit fork (`zephyr-port`, now `a4eb6395`), fork SDK from `tools/fork-sdk.sh`, openocd through the XIAO's
CMSIS-DAP, Python 3 on the host, `aplay`, faster-whisper (`uv run --with faster-whisper --with numpy`).

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 5; Goals: Toit wherever possible, the C sample as first
check; Left to the builder: "Start at 16 kHz, 32 kbit/s, and let the measurements tune it"; Decided: audio streams
only after LC3). Rung 4: `docs/journal/04-pdm-microphone.md`.

## Global Constraints

- The environment, board, console, logger and flashing rules of the rung 4 plan apply unchanged
  (`docs/superpowers/plans/2026-11-19-rung4-pdm-microphone.md`, Global Constraints).
- Never halt a running nRF (ztoit #23). Flashing is fine.
- A fork commit is followed by `tools/fork-sdk.sh`; `tools/sdk-id.sh` must agree on node and host (ztoit #24),
  and ztoit's `west.yml` pin moves to the new fork commit. A new primitive also needs its entry in the host
  compiler's primitive list (journal 04, item 6).
- The C6 on 4.2 must still build after the fork change (`build-i38-c6` recipe; build only, do not flash it).
- Public text (journal, ztoit and fork commits): run ktau's `git grep -n -i -f .private/public-text.txt`.
- `samples/` in ktau holds David's own recording: never commit it.
- ztoit commits say `refs #41`. No push until `/conclude`.
- Rung start time: 2026-11-20T18:46:15Z (for `tools/tokens.py` in Task 4).

## Review Focus

1. **Turning the FPU on breaks the VM build or corrupts floats** (an ABI mismatch with the Toit libraries, or FPU
   registers not saved across threads). Expected: the build links, and a Toit float computation printed before
   and after encoding gives the same digits. Task 2, step 4.
2. **liblc3 overruns the Toit thread's stack.** Expected: the C check measures its stack use
   (`k_thread_stack_space_get`), and the ztoit build has room for it; a fault here is a journal finding. Task 1,
   step 2 and Task 2, step 4.
3. **Encoding can't keep up with recording,** so the driver overruns and `read` throws `MICROPHONE_STOPPED`.
   Expected: encoding a 100 ms block takes well under 100 ms; the demo's 5 s clips record without that error.
   Task 3, step 3.
4. **Button bounce ends a recording early** (gpio-keys debounce is 1 ms since rung 3, set for the tap pulse).
   Expected: a clip lasts as long as the button is held, to within one 100 ms block. Task 3, step 3.
5. **Wrong byte order or sample format** gives noise that still decodes. Expected: the 440 Hz sine decodes on the
   host with its strongest frequency within 10 Hz of 440. Task 1, step 3 and Task 2, step 4.

---

### Task 1: The C check — `c/lc3check` on the XIAO

**Files:** Create `c/lc3check/{CMakeLists.txt,prj.conf,src/main.c}` in ktau; create `tools/lc3dec.py`.

**Interfaces:**
- Produces: the console format `LC3 BEGIN rate=16000 frame-us=10000 frame-bytes=<n> frames=<k>`, one base64 line
  per 10 frames, `LC3 END`. Task 3's demo prints the same format.
- Produces: `tools/lc3dec.py <log> <out-prefix>`: decodes every complete `LC3 BEGIN…END` block with liblc3's
  `lc3.py` to `<out-prefix>-<k>.wav` (16 kHz, mono, 16-bit) and prints `clip <k>: <seconds> s peak=<p> rms=<r>
  f0=<Hz>` (f0 is the strongest FFT bin). An incomplete block, or bad base64, is reported and skipped.

- [ ] **Step 1:** Build the host library: `make -C ~/zephyr-4.5/modules/lib/liblc3` (output under its `bin/`;
  build out of tree into the scratchpad if the Makefile allows). Write `lc3dec.py` with a test on a log written by
  hand (one sine clip encoded on the host with `lc3.py`, one cut-off clip). Expected: one WAV with f0≈440, one
  skipped message.
- [ ] **Step 2:** `main.c`: `CONFIG_FPU=y`, `CONFIG_LIBLC3=y`; generate 1 s of a 440 Hz sine at half scale,
  encode it at 32 kbit/s in 10 ms frames; print `sizeof(lc3_encoder_mem_16k_t)`, encode time per frame
  (min/avg/max µs from `k_cycle_get_32`), and the main thread's unused stack; print the frames in the format above.
  Record FLASH/RAM.
- [ ] **Step 3:** Flash, log, run `lc3dec.py`, play the WAV. Expected: f0 within 10 Hz of 440, 100 frames of
  40 B, and a clean tone to the ear.
- [ ] **Step 4:** Note the C source size (lines, code lines) for the journal's Toit-vs-C table. Commit (ktau):
  `Rung 5: the C check, LC3 on the XIAO; host decoder`.

### Task 2: ztoit — the LC3 primitives and `zephyr.Lc3Encoder`

**Files:**
- Modify (fork): `src/primitive.h` (`MODULE_ZEPHYR`: `PRIMITIVE(lc3_setup, 1)`, `PRIMITIVE(lc3_encode, 1)`),
  `src/resources/zephyr.cc`, `lib/zephyr.toit`, the host compiler's primitive list.
- Modify (ztoit): `zephyr/boards/xiao_nrf54l15_nrf54l15_cpuapp.conf`, `west.yml`.

**Interfaces:**
- Produces (C), `UNSUPPORTED` without `CONFIG_LIBLC3`:
  - `zephyr.lc3_setup(bitrate:int) -> int`: `lc3_frame_bytes(10000, bitrate)`; outside 20..400 B is
    `INVALID_ARGUMENT`. Then `lc3_setup_encoder(10000, 16000, 0, &static_mem)`; returns the frame bytes.
  - `zephyr.lc3_encode(pcm:Blob) -> ByteArray`: not set up, or a length that is not a positive multiple of 320,
    is `INVALID_ARGUMENT`; else one `lc3_encode(…, LC3_PCM_FORMAT_S16, …, stride 1, …)` per frame into a new
    ByteArray of `frames × frame-bytes` (`MALLOC_FAILED` if that fails).
- Produces (Toit, `lib/zephyr.toit`): `class Lc3Encoder` — `static RATE ::= 16000`, `static FRAME-US ::= 10_000`,
  `constructor --bitrate/int=32_000`; `frame-bytes -> int`; `encode pcm/ByteArray -> ByteArray`. The class
  comment says there is one encoder: a new `Lc3Encoder` resets it.
- Produces (conf): `CONFIG_FPU=y`, `CONFIG_FPU_SHARING=y`, `CONFIG_LIBLC3=y`.

- [ ] **Step 1: Write the failing check.** `app/rung5_probe.toit` in ktau: print a float computation
  (`(2.0).sqrt` to 15 digits); build 1 s of a 440 Hz sine in a ByteArray; encode it in 100 ms blocks, timing each
  with `Time.monotonic-us`; print the float again, `blocks=10 bytes=<n> enc-us min/avg/max`, and the clip in Task 1's
  format.
- [ ] **Step 2:** Build ztoit with the probe as the container on the current fork. Expected: fails to compile
  (`Lc3Encoder` not in `zephyr`).
- [ ] **Step 3:** Implement the primitives, the class and the conf. Commit the fork; `tools/fork-sdk.sh`;
  `tools/sdk-id.sh` agrees; move the pin.
- [ ] **Step 4:** Build (record FLASH/RAM against rung 4), flash, log, `lc3dec.py`. Expected: both float lines
  identical; `bytes=4000`; f0 within 10 Hz of 440; per-block time recorded.
- [ ] **Step 5:** Break-checks: `encode` of 321 B and of 0 B throw `INVALID_ARGUMENT`; `--bitrate=1000` throws
  `INVALID_ARGUMENT`. Then build the C6 on 4.2 (build only). Expected: links.
- [ ] **Step 6: Commit.** Fork: `Zephyr: LC3 encode primitives and zephyr.Lc3Encoder`. ztoit:
  `XIAO nRF54L15: FPU and liblc3, fork pin (refs #41)`.

### Task 3: ktau — push to talk, encode while recording; decode on the host

**Files:** Create `app/rung5.toit`; delete `app/rung5_probe.toit`.

**Interfaces:**
- Consumes: `zephyr.Microphone` (rung 4), `zephyr.Key`, `zephyr.Led`, `zephyr.Lc3Encoder` (Task 2), Task 1's console format
  and `lc3dec.py`.

- [ ] **Step 1:** `rung5.toit`: print `ktau rung 5`; loop: `button.wait-for-press` (`zephyr.Key "usr_btn"`);
  LED on; `Microphone.start`; read and encode each block, keeping the LC3 bytes, while `button.pressed` and fewer
  than 50 blocks (5 s); `stop`; LED off; print the clip and `encode-us min/avg/max`; `button.wait-for-release`.
  No IMU setup in this rung.
- [ ] **Step 2:** Build with `-DCONTAINERS=$HOME/workspaceToit/ktau/app/rung5.toit`, flash.
- [ ] **Step 3: At the bench (David):** hold the board 3–5 cm in front of the mouth, hold the button while
  speaking; five times the same short phrase, then once silent; then one press held about 2 s and one held past
  5 s (clip lengths recorded). Run `lc3dec.py`. Expected: no `MICROPHONE_STOPPED`; peaks below 32000
  (if they clip, rebuild at gain 0 dB and repeat; record which); extra clips from handling are counted.
- [ ] **Step 4:** David records the same phrase five times on the headset (Android recorder) into `samples/`.
  Run faster-whisper medium.en on all eleven XIAO clips and the five headset clips; record each transcript and its
  mean log-probability. This compares the two microphones; it is not a pass/fail.
- [ ] **Step 5: Commit** (ktau): `Rung 5: Toit encodes LC3 while recording; clips decode on the host`.

### Task 4: Journal entry 5

**Files:** Create `docs/journal/05-lc3-encode.md`, in the layout of entry 04.

- [ ] **Step 1:** Record: wall time; tokens (`tools/tokens.py 2026-11-20T18:46:15Z <end>`); FLASH/RAM vs rung 4
  (the encoder memory and the FPU); what broke; the evidence (the `lc3dec.py` lines, encode times, the Whisper
  table); clip size (PCM vs LC3); Toit vs the C check; **what went into C and why** (the codec, and its state held
  static).
- [ ] **Step 2:** Public-text check, commit (ktau), and a one-line comment on ztoit #41.
