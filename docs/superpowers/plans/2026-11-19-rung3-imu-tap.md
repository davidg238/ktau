# Rung 3: an IMU tap wakes a sleeping Toit task — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Toit configures the XIAO's LSM6DS3TR-C for single-tap detection over I2C, then a Toit task blocks
until a tap raises INT1 and wakes it. Journal entry 3 records it.

**Architecture:**
- **I2C:** one generic primitive, `zephyr.i2c_transfer`, on any Zephyr I2C bus found by node label. The Toit
  side, `zephyr.I2c`, hands out devices that implement `serial.Device`, so register access uses Toit's own
  `serial.Registers`. The IMU driver (register writes, tap setup) is Toit, in ktau.
- **The interrupt:** no new C. ztoit's overlay declares INT1 (P0.02) as a `gpio-keys` child, `imu_int1`, and
  Toit waits on it with the existing event-driven `zephyr.Key`. The tap interrupt is latched (LIR), so the line
  stays high until Toit reads `TAP_SRC`; Zephyr's debounce cannot swallow it.
- **Zephyr's own `st,lsm6dsl` driver is disabled** in the overlay, so Toit alone owns the chip and the pin.
- **The C check first:** Zephyr's `samples/sensor/lsm6dsl` on the stock board proves the bus, the power rail
  (`pdm_imu_pwr`, P0.01) and the chip before any Toit runs.

**Tech Stack:** Zephyr v4.5.0, SDK 1.0.1, the Toit fork (`zephyr-port`, now `3e1418df`), fork SDK from
`tools/fork-sdk.sh`, openocd through the XIAO's CMSIS-DAP.

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 3; Goals: Toit wherever possible, the C sample as first
check; Anti-goals: no hiding in C; Calls: "the IMU interrupt pin is found from the devicetree… if it isn't
wake-capable, that is a journal finding"). Board facts: `~/zephyr-4.5/zephyr/boards/seeed/xiao_nrf54l15/`.

## Global Constraints

- Environment for every 4.5 build: `source ~/workspace/ztoit/env.sh`, then
  `export PATH=~/zephyr-4.5/.venv/bin:$PATH ZEPHYR_BASE=~/zephyr-4.5/zephyr ZEPHYR_SDK_INSTALL_DIR=~/zephyr-sdk-1.0.1`.
  Never `west zephyr-export` 4.5; never register SDK 1.0.1.
- Board `xiao_nrf54l15/nrf54l15/cpuapp`. Console
  `/dev/serial/by-id/usb-Seeed_Studio_Seeed_Studio_XIAO_nrf54_CMSIS-DAP_E96922FA-if02`, 115200, logged by
  `tools/serial_log.py` (logger 2533704 already runs; check its PID before starting another); read with `grep -a`.
- Never halt a running nRF (ztoit #23). Flashing is fine.
- Board facts (devicetree, cite don't retype elsewhere): IMU `lsm6ds3tr_c` at `0x6a` on `i2c30` (SDA P0.04,
  SCL P0.03, 400 kHz); INT1 `&gpio0 2 GPIO_ACTIVE_HIGH`; power `pdm_imu_pwr` (`&gpio0 1`, boot-on, 5 ms).
- A fork commit is followed by `tools/fork-sdk.sh`; `tools/sdk-id.sh` must agree on node and host (ztoit #24),
  and ztoit's `west.yml` pin moves to the new fork commit.
- The C6 on 4.2 must still build after the fork change (`build-i38-c6` recipe; build only, do not flash it).
- Public text (journal, ztoit and fork commits): run ktau's `git grep -n -i -f .private/public-text.txt`.
- ztoit commits say `refs #41`. No push until `/conclude`.
- Record the rung's start time (UTC) before Task 1, for `tools/tokens.py` in Task 4.

## Review Focus

1. **The IMU is unpowered or NACKs** (`pdm_imu_pwr` not enabled with the Zephyr driver disabled). Expected:
   `WHO_AM_I` (0x0F) reads `0x6A`; a NACK surfaces as a Toit exception naming the errno, not a hang. Task 3, step 2.
2. **A tap during the 10 ms debounce, or two taps before Toit runs.** Expected: the latch holds INT1 high until
   `TAP_SRC` is read, so no tap is lost; two quick taps may count as one, and the journal says so. Task 3, step 4.
3. **The task polls instead of sleeping.** Expected: between taps nothing runs in Toit; proven by a program that
   prints only on a tap, plus a `presses` count that matches taps. Task 3, step 4.
4. **The fork change breaks the 4.2 builds** (`CONFIG_I2C` off on the C6). Expected: the primitive compiles to
   `UNSUPPORTED` without `CONFIG_I2C`, and the C6 build still links. Task 2, step 5.
5. **The tap register values are wrong for this part** (they come from ST's AN5130 for the LSM6DS3TR-C).
   Expected: the implementer checks each against the datasheet before Task 3, and a wrong one is a journal line.
   Task 3, step 1.

---

### Task 1: The C check — Zephyr's LSM6DSL sample on the XIAO

**Files:** none committed (build in `~/zephyr-4.5/build-lsm6dsl`).

- [ ] **Step 1:** Build `~/zephyr-4.5/zephyr/samples/sensor/lsm6dsl` for the board; record FLASH/RAM.
- [ ] **Step 2:** Flash, read the console. Expected: accelerometer values that change when the board is tilted
  (ask David to tilt it). Any failure here is a board finding, journalled, and stops the rung.
- [ ] **Step 3:** Note the sample's source size (lines, code lines) and whether it uses the trigger (INT1) path,
  for the journal's Toit-vs-C table.

### Task 2: ztoit — I2C primitive and `zephyr.I2c`; INT1 as a key

**Files:**
- Modify (fork): `src/primitive.h` (`MODULE_ZEPHYR`: add `PRIMITIVE(i2c_transfer, 4)`),
  `src/resources/zephyr.cc`, `lib/zephyr.toit`
- Modify (ztoit): `zephyr/boards/xiao_nrf54l15_nrf54l15_cpuapp.conf`, `.overlay`, `west.yml`

**Interfaces:**
- Produces (C): `zephyr.i2c_transfer(device:int, address:int, write:ByteArray|null, read_count:int)`:
  write-then-read with a repeated start (`i2c_write_read`) when both are given, `i2c_write` or `i2c_read` alone
  otherwise. Returns a new ByteArray of `read_count` bytes, or null when `read_count == 0`. Errors:
  `INVALID_ARGUMENT` for a bad device index or address outside 0..0x7f; `os_error(-ret)` from Zephyr;
  `UNSUPPORTED` without `CONFIG_I2C`. The device comes from `device_at(device)`, as `sensor_fetch` does.
- Produces (Toit, `lib/zephyr.toit`):
  - `class I2c` — `constructor label/string` (via `zephyr-device-find_`), `device address/int -> I2cDevice`.
  - `class I2cDevice implements serial.Device` — `registers -> serial.Registers`, `read amount/int -> ByteArray`,
    `write bytes/ByteArray -> none`. Its registers are 8-bit-addressed (write the register byte, then read with a
    repeated start), so `registers.read-u8 0x0F` and `registers.write-u8 0x10 0x60` work.
- Produces (devicetree): node label `imu_int1`, a `gpio-keys` child, `gpios = <&gpio0 2 GPIO_ACTIVE_HIGH>`,
  `zephyr,code = <INPUT_KEY_0>`; `&lsm6ds3tr_c { status = "disabled"; }`.
- Produces (conf): `CONFIG_I2C=y`, `CONFIG_INPUT=y`, `CONFIG_DEVICE_DT_METADATA=y` (needed by `device_find`).

- [ ] **Step 1: Write the failing check.** `app/rung3-probe.toit` in ktau: `zephyr.I2c "i2c30"`, device `0x6a`,
  print `WHO_AM_I=0x$(%02x (registers.read-u8 0x0F))`. Expected once working: `WHO_AM_I=0x6a`.
- [ ] **Step 2:** Build ztoit with the probe as the container on the current fork. Expected: fails to compile
  (`I2c` not in `zephyr`).
- [ ] **Step 3:** Implement the primitive, the Toit classes, the conf and the overlay as above. Commit the fork;
  run `tools/fork-sdk.sh`; check `tools/sdk-id.sh` agrees; move ztoit's `west.yml` pin.
- [ ] **Step 4:** Build, flash, read the console. Expected: `WHO_AM_I=0x6a`. Also expected:
  `zephyr.Key "imu_int1"` constructs without `FILE_NOT_FOUND` (one extra line in the probe).
- [ ] **Step 5:** Break-check: probe address `0x6b`. Expected: an exception carrying an I/O errno (NACK), not a
  hang. Then build the C6 on 4.2 (build only). Expected: links.
- [ ] **Step 6: Commit.** Fork: `Zephyr: I2C transfer primitive and zephyr.I2c (serial.Device)`. ztoit:
  `XIAO nRF54L15: I2C, IMU INT1 as a key, fork pin (refs #41)`.

### Task 3: ktau — the IMU driver and the tap program, in Toit

**Files:**
- Create: `app/lsm6ds3.toit` (the driver), `app/rung3.toit` (the demo); delete `app/rung3-probe.toit`.

**Interfaces:**
- Consumes: `zephyr.I2c`, `I2cDevice.registers`, `zephyr.Key` (Task 2).
- Produces: `class Lsm6ds3` — `constructor device/serial.Device` (checks `WHO_AM_I == 0x6A`, else throws),
  `enable-single-tap -> none`, `tap-source -> int` (reads `TAP_SRC` 0x1C, which clears the latch).

- [ ] **Step 1:** Check these values against the LSM6DS3TR-C datasheet / AN5130 and write them as named constants:
  `CTRL1_XL` 0x10 ← 0x60 (416 Hz, ±2 g); `TAP_CFG` 0x58 ← 0x8F (interrupts on, tap X/Y/Z, LIR latched);
  `TAP_THS_6D` 0x59 ← 0x89; `INT_DUR2` 0x5A ← 0x06; `WAKE_UP_THS` 0x5B ← 0x00 (single tap only);
  `MD1_CFG` 0x5E ← 0x40 (single tap on INT1).
- [ ] **Step 2:** `rung3.toit`: print `ktau rung 3`, construct the driver, `enable-single-tap`, read
  `tap-source` once to clear a stale latch, then loop: `key.wait-for-press`; `src := imu.tap-source`;
  print `tap $n src=0x$(%02x src)`; blink `led0` 100 ms.
- [ ] **Step 3:** Build with `-DCONTAINERS=$HOME/workspaceToit/ktau/app/rung3.toit`, flash.
- [ ] **Step 4:** Ask David to tap the board 5 times, slowly, then twice quickly. Expected: 5 lines `tap 1`…`tap 5`,
  each with bit 5 (`SINGLE_TAP`) set in `src`, an LED blink per tap, nothing printed between taps; the quick
  pair gives one or two lines (record which).
- [ ] **Step 5:** Break-check: with `MD1_CFG` written 0x00, taps print nothing. Restore it.
- [ ] **Step 6: Commit** (ktau): `Rung 3: Toit sets up the IMU over I2C; a tap wakes a Toit task`.

### Task 4: Journal entry 3

**Files:** Create `docs/journal/03-imu-tap.md`, in the layout of entry 02.

- [ ] **Step 1:** Record: wall time; tokens (`tools/tokens.py <start> <end>`); FLASH/RAM vs rung 2; what broke;
  the console evidence from Task 3 step 4; Toit vs the C sample (lines, where INT1 handling lives); **what went
  into C and why** (one generic I2C primitive; the interrupt is devicetree only); whether P0.02 can wake the SoC
  from ordinary sleep (GPIOTE on port 0), as the design asks.
- [ ] **Step 2:** Public-text check, commit (ktau), and a one-line comment on ztoit #41.
