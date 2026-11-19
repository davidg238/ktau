# Rung 1: the XIAO nRF54L15 on Zephyr 4.5 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The XIAO nRF54L15 Sense runs Zephyr's C blinky and hello_world from a new Zephyr v4.5.0 workspace. It is flashed through its on-board CMSIS-DAP probe, and journal entry 1 records the result.

**Architecture:**
- A second west workspace, `~/zephyr-4.5`, holds upstream v4.5.0, which already defines `xiao_nrf54l15`.
- ztoit's `~/zephyr-esp32` (v4.2, with its uncommitted nRF patch) is not touched.
- No ztoit or Toit code changes in this rung. Rung 2 moves ztoit onto 4.5.

**Tech Stack:**
- Zephyr v4.5.0 with Zephyr SDK 1.0.1 (v4.5.0's `SDK_VERSION`).
- west, and openocd from the SDK. The board's default runner is openocd with CMSIS-DAP; J-Link is the fallback.

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 1, Constraints, Decided).

## Global Constraints

- Never halt a running nRF to read it (ztoit #23). Flashing resets it, which is fine. Read state through the
  console, or unhalted.
- Serial ports are named by `/dev/serial/by-id/…`, never `ttyACMn`.
- Every build in this rung sets `ZEPHYR_BASE=$HOME/zephyr-4.5/zephyr` explicitly. Do not run
  `west zephyr-export` for 4.5: `~/.cmake/packages/Zephyr` already holds a registration, and ztoit's
  `find_package(Zephyr … HINTS $ENV{ZEPHYR_BASE})` must keep resolving to 4.2 when `ZEPHYR_BASE` is unset.
- The journal is public: the public-text rules apply.
- Commits end with the session's Co-Authored-By and Claude-Session lines. No push until `/conclude`, and the ktau
  remote is created only with David's approval.

## Review Focus

1. **A fresh board with protected or factory-locked flash.** `west flash` fails with an access-port error.
   Expected: a mass erase (`nrf54l_mass_erase` through openocd, or `west flash --recover` with J-Link), then the
   flash succeeds. Task 2, step 3 handles it.
2. **The two Zephyr trees mixing.** A 4.5 build picks up the 4.2 tree, or the reverse. Expected: the build log's
   `-- Zephyr version:` line says `4.5.0` for every rung-1 build. Task 1 step 4 checks it, and Task 2 step 6
   rebuilds one ztoit board to prove 4.2 is untouched.
3. **SDK 0.17.4 picked up by a 4.5 build.** Expected: cmake reports SDK 1.0.1. Task 1, step 4.
4. **The SAMD11 probe's firmware too old for openocd's nrf54l target.** Expected: J-Link on the SWD pads is the
   fallback, and the journal records it. Task 2, step 3.
5. **A console port mixed up with the dongle or the J-Link nRF on msi.** Expected: the new by-id entry is found by
   diffing `ls /dev/serial/by-id` before and after plugging in. Task 2, step 1.

---

### Task 1: Zephyr v4.5.0 workspace and SDK 1.0.1

**Files:**
- Create: `~/zephyr-4.5/` (west workspace, outside any repo)
- Create: `~/zephyr-sdk-1.0.1/`

**Interfaces:**
- Produces: `ZEPHYR_BASE=$HOME/zephyr-4.5/zephyr`, with the SDK 1.0.1 toolchain found by cmake and the board
  `xiao_nrf54l15/nrf54l15/cpuapp` resolvable.

- [ ] **Step 1: Initialise the workspace.**
  `west init -m https://github.com/zephyrproject-rtos/zephyr --mr v4.5.0 ~/zephyr-4.5`
- [ ] **Step 2: Fetch only the modules the ladder needs.** Run `west config manifest.project-filter` with
  `-*,+cmsis_6,+hal_nordic,+liblc3,+picolibc,+mbedtls,+segger,+tinycrypt`, then `west update`. A module a later rung
  needs is added to the filter then.
- [ ] **Step 3: Install SDK 1.0.1 beside 0.17.4,** arm toolchain plus host tools. Do not remove 0.17.4, which ztoit
  on 4.2 uses.
- [ ] **Step 4: Verify.**
  `cd ~/zephyr-4.5 && ZEPHYR_BASE=$PWD/zephyr west build -p -b xiao_nrf54l15/nrf54l15/cpuapp -d build-blinky zephyr/samples/basic/blinky`
  - Expected: the build succeeds.
  - Expected: the log shows `Zephyr version: 4.5.0` and SDK `1.0.1`.
  - Expected: the memory report prints FLASH and RAM use. Keep those two lines for the journal.

### Task 2: First light on the board

**Files:**
- Create: `~/zephyr-4.5/build-hello/` (build output only)

**Interfaces:**
- Consumes: Task 1's workspace.
- Produces:
  - the board's console by-id path;
  - a flashing method that works (openocd CMSIS-DAP, or J-Link);
  - both recorded in Task 3's journal entry and in ktau `CLAUDE.md`.

- [ ] **Step 1: Find the board's ports.** Plug in the XIAO. Diff `ls /dev/serial/by-id` from before and after,
  and record the new entry (or entries).
- [ ] **Step 2: Flash blinky.** `west flash -d build-blinky`. Expected: `openocd` reports the image written and
  verified.
- [ ] **Step 3: If step 2 fails with a protection or access-port error,** run
  `west flash -d build-blinky --erase` (openocd `nrf54l_mass_erase`) once and retry. If openocd can't attach at all,
  ask David for the J-Link on the SWD pads and use `west flash -r jlink`. Record which path worked and the exact error.
- [ ] **Step 4: Confirm the LED blinks.** David confirms by eye. That's the demo for rung 1.
- [ ] **Step 5: Flash hello_world.** Build `zephyr/samples/hello_world` into `build-hello`, flash it, and read the
  by-id console with `tools/serial_log.py` (copied from ztoit) at 115200. Expected: `Hello World! xiao_nrf54l15/nrf54l15/cpuapp`.
- [ ] **Step 6: Prove 4.2 is untouched.** Rebuild one ztoit board as ztoit's README shows, with `ZEPHYR_BASE` unset,
  then set to `~/zephyr-esp32/zephyr`. Expected: `Zephyr version: 4.2.0`, and the build succeeds.

### Task 3: Journal entry 1 and the ktau repo basics

**Files:**
- Create: `docs/journal/01-board-on-zephyr-4.5.md`
- Create: `CLAUDE.md` (stable rules, `@FOCUS.md`)
- Create: `FOCUS.md` (under 15 lines: next is rung 2, ztoit on 4.5)

**Interfaces:**
- Consumes: Task 1's build-size lines, and Task 2's port, flashing path and console output.
- Produces: the journal layout every later rung follows.

- [ ] **Step 1: Write the journal entry** with these headings:
  - What we set out to do
  - What it took (wall time, commands, new tools)
  - What broke (exact errors)
  - Evidence (console lines, the blinky confirmation)
  - Sizes (blinky FLASH/RAM, hello_world FLASH/RAM: the C baseline for rung 2's VM)
  - Toit vs C (rung 1 has no Toit yet: this sets the baseline)
- [ ] **Step 2: Write ktau `CLAUDE.md`,** one line each:
  - the `ZEPHYR_BASE` rule;
  - the console's by-id path;
  - the flashing method;
  - the public-text rule;
  - never halt a running nRF.
- [ ] **Step 3: Check before committing.** the public-text check over the new files.
  Expected: no matches.
- [ ] **Step 4: Commit.**
  `git add docs/journal CLAUDE.md FOCUS.md docs/superpowers && git commit -m "Rung 1: XIAO nRF54L15 on Zephyr 4.5, blinky and console; journal 01"`
