# 01 — The XIAO nRF54L15 on Zephyr 4.5

Rung 1, 2026-11-19.

## What we set out to do

Get the Seeed XIAO nRF54L15 Sense running Zephyr's own C samples, blinky and hello_world, from a fresh Zephyr
v4.5.0 workspace, and flash it through the board's on-board probe. No Toit yet. This rung sets the C baseline that
the Toit VM is measured against in rung 2.

## What it took

- **Wall time:** about two hours from start to this entry. Most of it was waiting for the board to be plugged in.
  The work itself was under half an hour.
- **Tokens (Claude Code):** 64 messages, 31 k output, 75 k cache-write, 8.1 M cache-read, from `tools/tokens.py
  2026-11-19T20:55:04Z`.
- **New tools:** Zephyr SDK 1.0.1 (beside 0.17.4, which the existing 4.2 tree still uses), and a second west
  workspace with its own Python venv.

```
west init -m https://github.com/zephyrproject-rtos/zephyr --mr v4.5.0 ~/zephyr-4.5
west config manifest.project-filter -- '-.*,+cmsis_6,+hal_nordic,+liblc3,+picolibc,+mbedtls,+segger'
west update
export ZEPHYR_BASE=~/zephyr-4.5/zephyr ZEPHYR_SDK_INSTALL_DIR=~/zephyr-sdk-1.0.1
west build -p -b xiao_nrf54l15/nrf54l15/cpuapp -d build-blinky zephyr/samples/basic/blinky
west flash -d build-blinky
west build -p -b xiao_nrf54l15/nrf54l15/cpuapp -d build-hello zephyr/samples/hello_world
west flash -d build-hello
```

The board's default runner is openocd, from the SDK, talking to the XIAO's on-board CMSIS-DAP probe (firmware
2.0.0). It worked first time. The flash wasn't protected, so no mass erase was needed, and the J-Link fallback
wasn't used. The console is the probe's USB serial interface (`…XIAO_nrf54_CMSIS-DAP_<serial>-if02`) at 115200.

## What broke

- `tinycrypt` is no longer in v4.5.0's `west.yml`, so it was dropped from the project filter.
- The 4.2 tree's venv lacks `jsonschema`, which 4.5 needs. 4.5 got its own venv from its own
  `scripts/requirements.txt` rather than sharing one.
- Keeping two trees apart needs care. SDK 1.0.1 was installed without registering it with CMake, and the 4.5 tree
  was not `zephyr-export`ed. Each 4.5 build names both with environment variables. A check found that with
  `ZEPHYR_BASE` unset, CMake resolves to a third Zephyr, an nRF Connect SDK install registered earlier. That
  predates this rung and isn't 4.5 leaking in, but it means `ZEPHYR_BASE` must always be set.
- The flash runner prints no "wrote/verified" line; a zero exit code and the LED are the evidence.

## Evidence

- Blinky: the green LED marked **L** blinks about once a second (confirmed by eye).
- hello_world console:

```
Hello World! xiao_nrf54l15/nrf54l15/cpuapp
```

- The build log says `Zephyr version: 4.5.0` and finds SDK 1.0.1. A rebuild of the existing 4.2 project with
  `ZEPHYR_BASE` pointing at 4.2 still says `4.2.0` with SDK 0.17.4 and succeeds.

## Sizes

| Sample | FLASH | RAM |
|---|---|---|
| blinky | 39236 B | 6584 B |
| hello_world | 39168 B | 6584 B |

Of 1524 KB flash and 256 KB RAM.

## Toit vs C

No Toit yet. These numbers are the C floor: rung 2 puts the Toit VM on this board, and its sizes are read against
this table.
