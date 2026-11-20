# 03 — A tap wakes a Toit task

Rung 3, 2026-11-19.

## What we set out to do

Set up the XIAO's IMU (an LSM6DS3TR-C) for tap detection from Toit, over I2C, and have a tap wake a Toit task
that is asleep waiting for it. Toit should do the work wherever it can. Zephyr's C sample for the IMU is the first
check.

## What it took

- **Wall time:** about 31 minutes from the C sample to the last test, plus the plan written before it. Five of
  those runs needed someone at the bench to tap the board.
- **Tokens (Claude Code):** 67 messages, 41 k output, 63 k cache-write, 9.1 M cache-read, from `tools/tokens.py
  2026-11-20T00:03:05Z` (execution only).
- **New in ztoit:**
  - One generic I2C primitive (35 lines of C): write, read, or write then read with a repeated start, on any
    Zephyr I2C bus found by its devicetree label.
  - `zephyr.I2c` in Toit (57 lines). Its devices implement Toit's `serial.Device`, so register access is Toit's
    own `serial.Registers`.
  - Board conf: 3 settings. Overlay: the IMU's INT1 pin declared as a `gpio-keys` child, and Zephyr's IMU
    driver turned off.
- **The Toit program:** `app/lsm6ds3.toit` (the driver, 42 code lines) and `app/rung3.toit` (the demo, 19).

## Why not Zephyr's IMU driver

Zephyr has a driver for this chip (`st,lsm6dsl`), but its only trigger is data-ready: it has no tap detection.
Using it would mean adding tap support to Zephyr's C driver (the hard part, hidden in C) or sharing the chip
between two owners. Waking at 416 Hz to detect taps in software would keep the CPU from sleeping. Instead, Toit owns
the chip: six register writes set up the tap engine, over one generic I2C primitive.

## What broke

1. **No tap reached Toit.** The IMU saw the taps (its `TAP_SRC` register read `0x6c`: tap, single tap, X axis),
   but the Toit task never woke. The tap interrupt pulses INT1 for a few milliseconds, and `gpio-keys` waits out a
   30 ms debounce by default before reading the pin, so every pulse was gone by then. The latch bit (`LIR`) did
   not hold the pin high.
   - **Fix:** a 1 ms debounce on the IMU's key node (ztoit overlay). This was found by elimination, one run each:
     the USR button worked through the same `zephyr.Key` path; a 1 ms debounce then counted presses on INT1.
2. **Too many taps, then too few.** ST's application note threshold (`TAP_THS` 9) missed 4 of 9 sharp taps.
   Threshold 2 caught every tap, but one sharp tap on the edge of this small board gives several tap events over
   about a second (it rings). 7 taps logged as 18.
   - **Fix:** one rule in Toit: a wake counts as one tap, and anything in the next 1000 ms is the same tap.
     Two taps less than a second apart count once, which suits tap-to-talk.
3. **A tap at boot.** The accelerometer starting up (0 to 1 g) reads as a tap. The driver now waits 50 ms before
   routing taps to INT1.
4. **The IMU stays powered across a reflash** (its power switch, `pdm_imu_pwr`, is on from boot), so the C
   sample's settings survived into the Toit run. The driver starts with a software reset.
5. **A container's file name must be a C identifier:** `rung3-probe.toit` broke the build, because ztoit uses
   the name in generated C. Renamed to `rung3_probe.toit`. Filed for ztoit.

## Evidence

The C sample (`samples/sensor/lsm6dsl`) on the stock board: gravity reads 9.9 m/s², and its data-ready trigger
counts about 105 a second on INT1 (P0.02). The bus, the power switch, the chip and the pin all work:

```
accel x:6.828517 ms/2 y:3.056830 ms/2 z:6.503093 ms/2
loop:2 trig_cnt:211
```

The Toit probe: `WHO_AM_I=0x6a`. With a wrong address (`0x6b`), Toit gets an exception, `I/O error`, not a
hang.

The demo, with the board lying on the bench: 5 sharp taps with slow spacing, then two quick pairs. The LED blinked
once for each slow tap and once for each pair:

```
tap 11 src=0x6c
tap 12 src=0x6c
tap 13 src=0x61
tap 14 src=0x6c
tap 15 src=0x6c
tap 16 src=0x62
tap 17 src=0x6c
```

Every `src` has bit 5 (single tap) set. Nothing prints between taps: the task is blocked in `wait-for-press`,
woken by Zephyr's input event, not polling. When every Toit task is waiting, Zephyr's idle thread runs. INT1 is
on port 0 with an interrupt, so it wakes the CPU from ordinary sleep. Rung 8 measures the current.

## Sizes

| Build | FLASH | RAM (static) |
|---|---|---|
| C sample `lsm6dsl` | 49632 B | 6952 B |
| ztoit + `rung2.toit` (rung 2) | 260428 B | 114120 B |
| ztoit + `rung3.toit` | 273612 B | 115632 B |

I2C, the input subsystem and device metadata add 1.5 KB of RAM over rung 2.

## Toit vs C

| | C sample `lsm6dsl` | Toit `rung3.toit` + driver |
|---|---|---|
| Source | 178 lines (133 code) | 82 lines (61 code) |
| Taps | not supported by the Zephyr driver | set up from Toit, 6 register writes |
| The interrupt | a trigger callback in C | `zephyr.Key "imu_int1"` and `wait-for-press` |
| A bad address | an error code to check | an exception |

**What went into C this rung, and why:**
- One I2C primitive, generic over any bus and target: Toit can't reach the bus without it.
- Devicetree only for the interrupt: no new C, because `gpio-keys` already carries a pin's edges to Toit.

None of it is specific to this IMU. The tap logic, the timings, and the fixes for ringing and start-up are all in
Toit.
