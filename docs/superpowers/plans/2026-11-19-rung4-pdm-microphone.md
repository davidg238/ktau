# Rung 4: a PDM microphone primitive; a clip recorded and played back on the host — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toit records a 1 s clip from the XIAO's PDM microphone, prints it on the console, and a host script
turns the log into a WAV that plays on msi. Journal entry 4 records it.

**Architecture:**
- **The microphone:** one primitive group over Zephyr's `dmic` API, generic over any `dmic` device found by node
  label: `mic_start`, `mic_read`, `mic_stop`. The memory slab (the driver's block pool) is static in
  `zephyr.cc`, under `CONFIG_AUDIO_DMIC`. Fixed format, from the design: 16 kHz, 16-bit, mono, 100 ms blocks.
- **No blocking in C:** `mic_read` calls `dmic_read` with `K_NO_WAIT` and copies one block into a new ByteArray
  (or returns null). Toit's `Microphone.read` polls with a 10 ms sleep. This is the degenerate case; an
  event-driven read (like `zephyr.Key`) is a later change if rung 8's power numbers ask for it. Polling only runs
  while recording; the idle wait for a tap stays event-driven (rung 3).
- **The clip leaves by the console:** recording goes into memory first (printing at 115200 baud is slower than
  the 32 KB/s of audio), then Toit prints one base64 line per block between `CLIP BEGIN` and `CLIP END` lines.
  `tools/clip2wav.py` in ktau extracts it from the serial log and writes a WAV. Buffering is only for this rung.
  Streaming needs encoding: raw PCM is 256 kbit/s, and LC3 (rung 5) brings it to 32 kbit/s for BLE (rung 6).
- **The C check first:** Zephyr's `samples/drivers/audio/dmic` on the XIAO proves the pins, the power rail and
  which PDM channel (left or right) carries the microphone.

**Tech Stack:** Zephyr v4.5.0, SDK 1.0.1, the Toit fork (`zephyr-port`, now `a035bb0e`), fork SDK from
`tools/fork-sdk.sh`, openocd through the XIAO's CMSIS-DAP, Python 3 `wave` on the host, `aplay`.

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 4; Goals: Toit wherever possible, the C sample as first
check; Anti-goals: no hiding in C; Left to the builder: "Start at 16 kHz"). Board facts:
`~/zephyr-4.5/zephyr/boards/seeed/xiao_nrf54l15/` (`dmic_dev: &pdm20`, alias `dmic0`, `pdm_imu_pwr`).

## Global Constraints

- Environment for every 4.5 build: `source ~/workspace/ztoit/env.sh`, then
  `export PATH=~/zephyr-4.5/.venv/bin:$PATH ZEPHYR_BASE=~/zephyr-4.5/zephyr ZEPHYR_SDK_INSTALL_DIR=~/zephyr-sdk-1.0.1`.
  Never `west zephyr-export` 4.5; never register SDK 1.0.1.
- Board `xiao_nrf54l15/nrf54l15/cpuapp`. Console
  `/dev/serial/by-id/usb-Seeed_Studio_Seeed_Studio_XIAO_nrf54_CMSIS-DAP_E96922FA-if02`, 115200, logged by
  `tools/serial_log.py` (logger 2533704 already runs; check its PID before starting another); read with `grep -a`.
- Never halt a running nRF (ztoit #23). Flashing is fine.
- A container's file name must be a C identifier (`rung4_probe.toit`, not `rung4-probe.toit`; journal 03).
- The microphone and the IMU share `pdm_imu_pwr` (P0.01, boot-on). Rung 3's IMU setup must keep working.
- A fork commit is followed by `tools/fork-sdk.sh`; `tools/sdk-id.sh` must agree on node and host (ztoit #24),
  and ztoit's `west.yml` pin moves to the new fork commit.
- The C6 on 4.2 must still build after the fork change (`build-i38-c6` recipe; build only, do not flash it).
- Public text (journal, ztoit and fork commits): run ktau's `git grep -n -i -f .private/public-text.txt`.
- ztoit commits say `refs #41`. No push until `/conclude`.
- Record the rung's start time (UTC) before Task 1, for `tools/tokens.py` in Task 4.

## Review Focus

1. **Toit falls behind and the slab runs dry** (a GC pause, or printing while recording). Expected: the driver
   reports an overrun, which reaches Toit as an exception from `read`, not silent gaps in the clip. Task 3, step 4
   (print each block while recording, once, and see what happens).
2. **A second recording after `stop`** finds blocks left in the driver's queue. Expected: `mic_stop` drains and
   frees every queued block, so the second clip starts clean. Task 3, step 3 records two clips.
3. **The wrong PDM channel** gives a clip of near-silence that looks like success. Expected: `clip2wav.py`
   prints peak and RMS, and a quiet clip vs a spoken clip differ by a clear margin. Task 1, step 3 and Task 3,
   step 3.
4. **The heap cannot hold the clip** (32000 B in an 80 KB Toit heap). Expected: a 1 s clip fits; if not, a
   `MALLOC_FAILED` is a journal finding and the clip shortens, not a reason to grow the C buffer. Task 3, step 3.
5. **The fork change breaks the 4.2 builds** (`CONFIG_AUDIO_DMIC` off on the C6). Expected: the primitives
   compile to `UNSUPPORTED`, and the C6 build still links. Task 2, step 5.

---

### Task 1: The C check — Zephyr's dmic sample on the XIAO

**Files:** none committed (build in `~/zephyr-4.5/build-dmic`).

- [ ] **Step 1:** Build `~/zephyr-4.5/zephyr/samples/drivers/audio/dmic` for the board (no XIAO overlay is
  needed: the board already has `dmic0`); record FLASH/RAM.
- [ ] **Step 2:** Flash, read the console. Expected: the mono (left) and stereo transfers each log their blocks
  without a read error. A failure is a board finding, journalled, and stops the rung.
- [ ] **Step 3: Find the channel.** The sample only logs block counts, so add a temporary print of each block's
  peak absolute sample (not committed). Ask David to speak near the board. Expected: the left channel's
  peak rises with speech (or, if it stays near zero, the right channel's does). Record which; Task 2 uses it.
- [ ] **Step 4: Console speed, for information only.** Rebuild hello_world with `&uart20 { current-speed = <921600>; }`
  and run it with the logger at 921600 (stop logger 2533704 by PID first, restart it at 115200 after). Expected:
  either clean text or garbage; record which in the journal. Raw PCM in base64 needs about 341 kbit/s, so this tells
  whether the console could carry it live. The plan does not change: the clip is still buffered, and streaming waits
  for LC3 (rung 5) and BLE (rung 6).
- [ ] **Step 5:** Note the sample's source size (lines, code lines) for the journal's Toit-vs-C table.

### Task 2: ztoit — the microphone primitives and `zephyr.Microphone`

**Files:**
- Modify (fork): `src/primitive.h` (`MODULE_ZEPHYR`: add `PRIMITIVE(mic_start, 1)`, `PRIMITIVE(mic_read, 1)`,
  `PRIMITIVE(mic_stop, 1)`), `src/resources/zephyr.cc`, `lib/zephyr.toit`
- Modify (ztoit): `zephyr/boards/xiao_nrf54l15_nrf54l15_cpuapp.conf`, `west.yml`

**Interfaces:**
- Produces (C), all on `device_at(device)` with `is_dmic` (`DEVICE_API_IS(dmic, dev)`) or `WRONG_OBJECT_TYPE`,
  and `UNSUPPORTED` without `CONFIG_AUDIO_DMIC`:
  - `zephyr.mic_start(device:int)`: `dmic_configure` at 16000 Hz, 16-bit, one channel on the PDM channel found
    in Task 1, block size 3200 B (100 ms), from a static slab of 4 blocks; then `DMIC_TRIGGER_START`.
    Errors: `os_error(-ret)`.
  - `zephyr.mic_read(device:int) -> ByteArray|null`: `dmic_read(…, K_NO_WAIT)`; on a block, copy it into a new
    ByteArray (`MALLOC_FAILED` if that fails, after freeing the block), free the block, return it; on `-EAGAIN`,
    null; any other error, `os_error(-ret)` (this is where an overrun surfaces).
  - `zephyr.mic_stop(device:int)`: `DMIC_TRIGGER_STOP`, then read with `K_NO_WAIT` and free until empty.
- Produces (Toit, `lib/zephyr.toit`): `class Microphone` — `constructor label/string`; `static RATE ::= 16000`;
  `start -> none`; `read -> ByteArray` (one 100 ms block of little-endian int16 samples; polls `mic_read`,
  sleeping 10 ms when it returns null); `stop -> none`.
- Produces (conf): `CONFIG_AUDIO=y`, `CONFIG_AUDIO_DMIC=y`.

- [ ] **Step 1: Write the failing check.** `app/rung4_probe.toit` in ktau: `zephyr.Microphone "pdm20"`, `start`,
  read 10 blocks, `stop`, print `blocks=10 bytes=$total peak=$peak` (peak absolute int16 over all blocks).
- [ ] **Step 2:** Build ztoit with the probe as the container on the current fork. Expected: fails to compile
  (`Microphone` not in `zephyr`).
- [ ] **Step 3:** Implement the primitives, the Toit class and the conf as above. Commit the fork; run
  `tools/fork-sdk.sh`; check `tools/sdk-id.sh` agrees; move ztoit's `west.yml` pin.
- [ ] **Step 4:** Build, flash, read the console. Expected: `blocks=10 bytes=32000`, and a peak that rises when
  David speaks during it (run twice: quiet, then speaking).
- [ ] **Step 5:** Break-checks: `zephyr.Microphone "i2c30"` then `start` throws `WRONG_OBJECT_TYPE`. Then build
  the C6 on 4.2 (build only). Expected: links.
- [ ] **Step 6: Commit.** Fork: `Zephyr: PDM microphone primitives and zephyr.Microphone`. ztoit:
  `XIAO nRF54L15: audio conf, fork pin (refs #41)`.

### Task 3: ktau — record a clip in Toit; play it back on the host

**Files:**
- Create: `app/rung4.toit` (the demo), `tools/clip2wav.py`; delete `app/rung4_probe.toit`.

**Interfaces:**
- Consumes: `zephyr.Microphone` (Task 2); `zephyr.Key "imu_int1"` and `Lsm6ds3` (rung 3).
- Produces: the console format `CLIP BEGIN n=<k> rate=16000`, then one base64 line per block, then `CLIP END`.
  `tools/clip2wav.py <log> <out-prefix>` writes `<out-prefix>-<k>.wav` (16 kHz, mono, 16-bit) for every
  complete clip in the log, and prints `clip <k>: <seconds> s peak=<p> rms=<r>` for each. A clip without its
  `CLIP END`, or a line that is not valid base64, is reported and skipped.

- [ ] **Step 1:** Write `clip2wav.py`, and test it on a log written by hand: one clip of two lines, one cut-off
  clip. Expected: one WAV, one skipped-clip message.
- [ ] **Step 2:** `rung4.toit`: print `ktau rung 4`; set up the IMU as rung 3; loop: wait for a tap; LED on;
  record 10 blocks into a list; LED off; print the clip.
- [ ] **Step 3:** Build with `-DCONTAINERS=$HOME/workspaceToit/ktau/app/rung4.toit`, flash. Ask David to tap,
  stay quiet for the clip, then tap and speak a short phrase. Run `clip2wav.py` on the serial log; play both with
  `aplay`. Expected: two WAVs, the spoken one recognisable to David and its RMS clearly above the quiet one's
  (record both numbers).
- [ ] **Step 4:** Break-check: print each block as it is read, once. Record what happens (an overrun error, or
  none at 115200 baud), then restore.
- [ ] **Step 5: Commit** (ktau): `Rung 4: Toit records the PDM microphone; a clip plays back on the host`.

### Task 4: Journal entry 4

**Files:** Create `docs/journal/04-pdm-microphone.md`, in the layout of entry 03.

- [ ] **Step 1:** Record: wall time; tokens (`tools/tokens.py <start> <end>`); FLASH/RAM vs rung 3 (the slab's
  12.8 KB shows up here); what broke; the evidence from Task 3 step 3 (the `clip2wav.py` lines); Toit vs the C
  sample (lines, where the buffer handling lives); **what went into C and why** (the `dmic` calls and the slab,
  which Zephyr's API needs static; the copy into Toit memory); the polling read, and why it is the first cut.
- [ ] **Step 2:** Public-text check, commit (ktau), and a one-line comment on ztoit #41.
