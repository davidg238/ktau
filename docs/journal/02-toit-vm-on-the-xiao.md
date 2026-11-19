# 02 — The Toit VM on the XIAO nRF54L15

Rung 2, 2026-11-19.

## What we set out to do

Boot ztoit's Toit VM on the XIAO, built against Zephyr 4.5 for the first time. Show Toit `print` on the console
and the LED driven from Toit, and measure how much of the 256 KB of RAM the VM takes.

## What it took

- **Wall time:** about 11 minutes from the first build to the LED blinking, plus the plan written before it.
- **Tokens (Claude Code):** 59 messages, 34 k output, 74 k cache-write, 7.7 M cache-read, from `tools/tokens.py
  2026-11-19T23:10:10Z` (execution only; the planning before it isn't counted).
- **New in ztoit:**
  - A board conf and overlay for `xiao_nrf54l15/nrf54l15/cpuapp`, 3 settings and 1 partition.
  - A crypto shim for Zephyr 4.5's Mbed TLS: 10 forwarding headers and a version-chosen conf.
  - Two small fixes in the Toit fork's VM.
- **The Toit program:** `app/rung2.toit`, built into the image with `-DCONTAINERS=`.

```
west build -p -b xiao_nrf54l15/nrf54l15/cpuapp -d build-rung2 ~/workspace/ztoit/zephyr \
    -- -DCONTAINERS=$HOME/workspaceToit/ktau/app/rung2.toit
west flash -d build-rung2
```

## What broke

Everything that broke came from the move to Zephyr 4.5, not from the board.

1. **Mbed TLS 4.** Zephyr 4.5 ships Mbed TLS 4 on TF-PSA-Crypto. The Kconfig refused ztoit's crypto settings:
   `MBEDTLS … was assigned the value 'y' but got the value 'n' … (PSA_CRYPTO)`, and `MBEDTLS_RSA_C` no longer
   exists. The VM core includes Mbed TLS's older headers (bignum, SHA, AES, GCM, ChaCha-Poly, ECDSA, entropy), but on
   Zephyr it links only bignum, SHA-256/512 and entropy; Toit's `crypto` primitives are compiled out there. In 4.x
   those still exist, but as private headers (`mbedtls/private/*.h`, behind `MBEDTLS_DECLARE_PRIVATE_IDENTIFIERS`).
   - **Fix:** ten headers under the old names forward to the private ones. A conf chosen from `$ZEPHYR_BASE/VERSION`
     turns on the PSA modules the VM needs. The VM sources are unchanged, and 4.2 builds keep their old conf.
   - **Two wrong turns on the way:** asking for bignum through the RSA public key fails, because TF-PSA's own
     `rsa.c` doesn't compile with only that (`unused parameter` under `-Werror`), so it comes through ECC instead.
     The private headers also don't define `MBEDTLS_VERSION_MAJOR`, so the VM's version check silently took the
     2.x branch until the shims also included `build_info.h`.
2. **A name clash.** Toit's `ARGS(word, current)` declares a variable named `_raw_current`, and 4.5 defines a
   kernel macro with that name. The result was `expected ')' before '.' token` deep in `kernel_structs.h`.
   - **Fix:** rename the argument (fork).
3. **stdio.** 4.5 defines `_POSIX_THREAD_SAFE_FUNCTIONS`, so the VM picked its `fwrite_unlocked` path, which
   picolibc doesn't have.
   - **Fix:** Zephyr takes the plain `fwrite` path (fork).
4. **The LED.** The first run threw `FILE_NOT_FOUND` from `zephyr.Led "led0"`. ztoit's LED table is only built
   with `CONFIG_LED`.
   - **Fix:** one line in the board conf.

The ESP32-C6 build on Zephyr 4.2 still succeeds after all four fixes.

## Evidence

First boot, default program:

```
*** Booting Zephyr OS build v4.5.0 ***
ztoit: program 49152 B at 0, installed in the registry in 101 ms
ztoit: program 24576 B at 49152, installed in the registry in 52 ms
hello
idle: process allocated=916 reserved=8192 system free=1073741823 largest=1073741823
tasks started=8
8 tasks: process allocated=6912 reserved=12288 system free=1073741823 largest=1073741823
tick 5: process allocated=6772 reserved=12288 system free=1073741823 largest=1073741823
```

After a reset the programs are found, not reinstalled. The registry works on the nRF54L15's RRAM:

```
ztoit: 2 images, already in the registry
```

The rung-2 program prints `ktau rung 2` and the green LED blinks at about 1 Hz (confirmed by eye). At 50% duty a blink looks the same whichever way round on and off are, so a second program called `led.on` once
and idled: the LED stayed lit (confirmed by eye). Zephyr honours the devicetree's active-low flag, and Toit's `on`
means lit.

## Sizes

| Build | FLASH | RAM (static) |
|---|---|---|
| C blinky (rung 1) | 39236 B | 6584 B |
| ztoit + `hello.toit` | 259840 B | 114120 B |
| ztoit + `rung2.toit` | 260428 B | 114120 B |

- **RAM:** 114120 B is 43.6% of 262048 B. Of that, 80 KB is the Toit heap arena, set by `CONFIG_TOIT_HEAP_SIZE`
  (the nRF52840 dongle's value; not tuned). That leaves about 148 KB for the BLE stack, LC3 and the audio buffers.
- **A Toit process at rest** reserves 8 KB of the arena, and 12 KB with 8 sleeping tasks.
- **Unknown free memory:** `system free` prints `1073741823` (2³⁰−1), a placeholder. ztoit on Zephyr doesn't
  report the C heap's free memory yet, so this rung can't say how much of the remaining RAM is really free.
- **Images** are stored in RRAM, not RAM: the system program takes 48 KB and each app 24 KB.

## Toit vs C

| | C blinky | Toit `rung2.toit` |
|---|---|---|
| Source | 48 lines (28 code) | 18 lines (14 code), including a 4-line memory report |
| Text in flash | 38 KB | 253 KB (VM, system program and app) |
| Finding the LED | `GPIO_DT_SPEC_GET(DT_ALIAS(led0), gpios)` | `zephyr.Led "led0"` |
| Error handling | 3 checks written out | an exception, with a trace |

The Toit side is shorter, and its first failure came back as a decodable exception, not silence. The cost is the
VM: about 220 KB more flash and 107 KB more RAM than blinky, before any feature.

**What went into C this rung, and why:**
- Board files (devicetree and Kconfig), which C needs too.
- The Mbed TLS shim, because the VM core links Mbed TLS.
- Two one-line VM fixes for Zephyr 4.5.

None of it is application logic. Rung 3 (IMU tap over I2C) is the first test of whether the application can stay
in Toit.
