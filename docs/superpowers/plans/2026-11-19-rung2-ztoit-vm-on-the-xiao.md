# Rung 2: the ztoit VM boots on the XIAO nRF54L15 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ztoit, built against Zephyr v4.5.0, boots the Toit VM on the XIAO nRF54L15 Sense: Toit `print` on the
console, the LED driven from Toit, and RAM measured. Journal entry 2 records it.

**Architecture:**
- ztoit's app (`~/workspace/ztoit/zephyr`) gets a board conf and overlay for `xiao_nrf54l15/nrf54l15/cpuapp`,
  as the dongle and the RP2350B have. The Toit module (`modules/toit`) is in-tree, so nothing new goes into the
  4.5 west workspace.
- Whatever Zephyr 4.2 → 4.5 breaks in ztoit or the Toit fork is fixed so that **both** trees still build. The C6
  build on 4.2 is the check.
- The rung-2 Toit program lives in ktau (`app/rung2.toit`) and is passed with `-DCONTAINERS=`.

**Tech Stack:** Zephyr v4.5.0, SDK 1.0.1, the Toit fork at ztoit's `west.yml` pin (`7fb2838e`), the fork SDK from
`tools/fork-sdk.sh`, openocd through the XIAO's CMSIS-DAP.

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 2, Constraints: RAM, nRF rule; Calls: "a RAM shortfall is
a finding"; "ktau builds through ztoit's tree"). ztoit `docs/design/zephyr-port.md` addendum 2026-11-19.

## Global Constraints

- Environment for every 4.5 build: `source ~/workspace/ztoit/env.sh` (for `TOIT_SRC`, `TOIT_HOST`), then
  `export PATH=~/zephyr-4.5/.venv/bin:$PATH ZEPHYR_BASE=~/zephyr-4.5/zephyr ZEPHYR_SDK_INSTALL_DIR=~/zephyr-sdk-1.0.1`.
  Never `west zephyr-export` 4.5 and never register SDK 1.0.1.
- Board: `xiao_nrf54l15/nrf54l15/cpuapp`. Console:
  `/dev/serial/by-id/usb-Seeed_Studio_Seeed_Studio_XIAO_nrf54_CMSIS-DAP_E96922FA-if02`, 115200, logged with
  `tools/serial_log.py`; read logs with `grep -a`.
- Never halt a running nRF (ztoit #23): no GDB attach. Flashing (which resets) is fine.
- A Toit fork commit is followed by `tools/fork-sdk.sh`, and `tools/sdk-id.sh` must agree on node and host (ztoit #24).
- Public text (journal, ztoit commits/issues): the public-text rules apply.
- ztoit commits say `refs #41`, never a closing keyword. No push until `/conclude`.
- Record the rung's start time (UTC) before Task 1, for `tools/tokens.py` in Task 4.

## Review Focus

1. **The registry partition on RRAM.** The nRF54L15 has RRAM, not erase-to-0xff NOR flash; 4.5 partitions are
   `zephyr,mapped-partition`. Expected: `FIXED_PARTITION_*(toit_partition)` still resolves, and a program
   installed at the first boot is found, not reinstalled, after a reset. Task 2, step 4.
2. **Boot fails silently** (a fault before the console is up, or a VM `FATAL`). Expected: the fault is read from
   the console after a reset; no halt. Task 2, step 3.
3. **The 4.2 builds broken by a 4.5 fix.** Expected: the C6 build on 4.2 still succeeds after every ztoit or fork
   change. Task 1, step 5.
4. **RAM overflow at link time.** Expected: a link error is a finding; lower `CONFIG_TOIT_HEAP_SIZE` and record
   both numbers, never move boards. Task 1, step 4.
5. **The LED's label.** `zephyr.Led` finds a node by label; the board's LED is `led0` (active low on the XIAO).
   Expected: `Led "led0"` finds it and on/off match what the eye sees. Task 3, step 3.

---

### Task 1: ztoit builds for the XIAO on Zephyr 4.5

**Files:**
- Create: `~/workspace/ztoit/zephyr/boards/xiao_nrf54l15_nrf54l15_cpuapp.conf`
- Create: `~/workspace/ztoit/zephyr/boards/xiao_nrf54l15_nrf54l15_cpuapp.overlay`
- Modify (only if 4.5 breaks them): `~/workspace/ztoit/zephyr/src/main.cc`, `modules/toit/*`, fork `src/*_zephyr.cc`

**Interfaces:**
- Produces: `west build -b xiao_nrf54l15/nrf54l15/cpuapp -d ~/zephyr-4.5/build-ztoit ~/workspace/ztoit/zephyr`
  succeeding, and the build's FLASH/RAM report.

- [ ] **Step 1: Overlay.** Delete `slot1_partition` and put `toit_partition` (`label = "toit"`) in its place,
  same `reg` as the board's slot1 (read it from 4.5's `nrf54l15_cpuapp_partition.dtsi`, the branch the board
  takes). Leave `storage_partition` alone. Header comment in the dongle overlay's style: what goes where and why.
- [ ] **Step 2: Conf.** `CONFIG_TOIT_HEAP_SIZE=81920` (the dongle's value, a starting point, not a tuning). No
  `CONFIG_UART_LINE_CTRL`: the console is the probe's UART bridge, not USB CDC.
- [ ] **Step 3: Build.** Expected: `Zephyr version: 4.5.0`, SDK 1.0.1, the build succeeds. Each error is fixed at
  its cause, one ztoit (or fork) commit per cause, and its exact text kept for the journal. A 4.2/4.5 difference
  is handled with a version check (`KERNEL_VERSION_NUMBER`) only where one source must serve both.
- [ ] **Step 4: If RAM overflows,** halve `CONFIG_TOIT_HEAP_SIZE` until it links; keep the overflow amount and
  the final value for the journal.
- [ ] **Step 5: 4.2 still builds.** With `env.sh` alone: `west build -p -b esp32c6_devkitc/esp32c6/hpcore -d
  /tmp/…/build-c6-check ~/workspace/ztoit/zephyr` (in the scratchpad). Expected: `Zephyr version: 4.2.0`, success.
  If the fork changed, run `tools/fork-sdk.sh` first and check `tools/sdk-id.sh`.
- [ ] **Step 6: Commit (ztoit).**
  `git add zephyr/boards/xiao_nrf54l15_* && git commit -m "XIAO nRF54L15 on Zephyr 4.5: board conf and overlay (refs #41)"`

### Task 2: The VM boots and prints

**Interfaces:**
- Consumes: Task 1's build (default container, `zephyr/toit/hello.toit`).
- Produces: the boot log, and hello.toit's `report` lines (process allocated/reserved, system free, largest).

- [ ] **Step 1: Start the logger** on the console by-id path into the scratchpad; note its PID.
- [ ] **Step 2: Flash.** `west flash -d ~/zephyr-4.5/build-ztoit`. Expected: exit 0.
- [ ] **Step 3: Read the log** (`grep -a`). Expected: `hello`, `idle: process allocated=…`, `tasks started=8`,
  then `tick 5`. If nothing prints or it faults, reset by reflashing and read the fault text; never attach GDB.
- [ ] **Step 4: Registry survives a reset.** Reflash the same build (or reset via openocd `reset run`). Expected:
  the boot log shows the installed images found, not installed again, and `hello` runs. If it reinstalls every
  boot or faults on install, that is an RRAM finding: record it and fix in the fork's `flash_registry_zephyr.cc`
  (one commit, `refs #41`), then rerun steps 2–4.
- [ ] **Step 5: Keep** the `idle`, `8 tasks` and `tick 5` lines verbatim for the journal.

### Task 3: The LED from Toit (ktau's first Toit code)

**Files:**
- Create: `~/workspaceToit/ktau/app/rung2.toit`

**Interfaces:**
- Consumes: `import zephyr` → `Led "led0"` (fork `lib/zephyr.toit`), `system.process-stats --gc`.
- Produces: the rung-2 demo, and the program later rungs grow from.

- [ ] **Step 1: Write `app/rung2.toit`:** prints `ktau rung 2`, a `report` line in hello.toit's format, then
  toggles `led0` every 500 ms forever (blinky's behaviour, so the two compare one for one).
- [ ] **Step 2: Build** into `~/zephyr-4.5/build-rung2` with `-- -DCONTAINERS=$HOME/workspaceToit/ktau/app/rung2.toit`.
  Keep the FLASH/RAM report.
- [ ] **Step 3: Flash and check.** Expected: `ktau rung 2` and the report on the console; the LED blinks at 1 Hz
  (David confirms by eye). If on/off are inverted, note it (active low) and check `Led` honours the dts flag.
- [ ] **Step 4: Count.** Lines of `app/rung2.toit` against `zephyr/samples/basic/blinky/src/main.c`; image sizes
  against journal 01's table.
- [ ] **Step 5: Commit (ktau).** `git add app && git commit -m "Rung 2: Toit blinks the LED on the XIAO"`

### Task 4: Journal 02 and the records

**Files:**
- Create: `~/workspaceToit/ktau/docs/journal/02-toit-vm-on-the-xiao.md`
- Modify: ztoit `docs/design/zephyr-port.md` (addendum section 2026-11-19, a bullet: the XIAO's partitions,
  heap, and each 4.5 break found)
- Modify: ktau `FOCUS.md`, ztoit `FOCUS.md` (next: rung 3, IMU tap)

- [ ] **Step 1: Write the entry** with journal 01's headings. Sizes table: blinky (C), hello.toit build,
  rung2 build, each FLASH/RAM; plus the VM's runtime numbers from Task 2 step 5 and the heap setting. "What broke":
  every 4.5 break with its fix. "Toit vs C": lines and sizes from Task 3 step 4, and what went into C (the board
  files, any fork change) and why. Tokens: `tools/tokens.py <start> <now>`.
- [ ] **Step 2: Check before committing.** the public-text check over the new text.
  Expected: no matches.
- [ ] **Step 3: Commit both repos;** comment on ztoit #41 (≤5 lines: booted, RAM numbers, journal 02).
