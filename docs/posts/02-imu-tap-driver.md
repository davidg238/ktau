# A tap driver in Toit, when Zephyr's driver can't

Draft, 2026-11-21. Raw material: `docs/journal/03-imu-tap.md`.

The push-to-talk demo used Zephyr's microphone driver as it is. The board's IMU went the other way.

The XIAO nRF54L15 Sense has an LSM6DS3TR-C accelerometer and gyro. The chip has a tap engine: set it up, and it
pulses a pin when it feels a tap, with the CPU asleep. Zephyr has a driver for the chip family (`st,lsm6dsl`), but
its only trigger is data-ready. It has no tap detection. That left three choices:

1. add tap support to Zephyr's C driver;
2. read samples at 416 Hz and detect taps in software, which keeps the CPU awake;
3. turn Zephyr's driver off and let Toit own the chip.

ztoit took the third. All it needed from C was one generic I2C primitive (35 lines): write, read, or write then read,
on any Zephyr I2C bus. On top of that, `zephyr.I2c` (57 lines) implements Toit's `serial.Device`, so register access
is Toit's own `serial.Registers`. The tap driver is 42 lines of Toit; six register writes set up the tap engine.

The interrupt needed no new C at all. The IMU's INT1 pin is declared in the devicetree overlay as a `gpio-keys`
button, so Toit waits on it the same way as on the board's real button: `zephyr.Key "imu_int1"` and `wait-for-press`.
The task blocks, Zephyr's idle thread runs, and the pin's interrupt wakes the CPU.

## What broke

- **No tap reached Toit.** The chip saw every tap, but its pulse lasts a few milliseconds, and `gpio-keys` waits out
  a 30 ms debounce before reading the pin. A 1 ms debounce on that one node fixed it.
- **The board rings.** At a threshold low enough to catch every tap, one sharp tap gave several events over about a
  second. One rule in Toit: anything within 1000 ms of a tap is the same tap.
- **Starting up reads as a tap** (0 to 1 g), so the driver waits 50 ms before routing taps to the pin.
- **The IMU stays powered across a reflash**, so the driver starts with a software reset.

## Zephyr's driver against Toit's

| | Zephyr C sample + driver | Toit demo + driver |
|---|---|---|
| Source | 133 code lines (the sample) | 61 code lines (demo and driver) |
| Taps | not supported | 6 register writes |
| The interrupt | a trigger callback in C | `wait-for-press` on a key |
| A wrong address | an error code to check | an exception |
| Flash | — | +13 KB over the bare VM |

The C that went in is generic: an I2C primitive and a pin. What is specific to this chip, the register settings, the
timings and the fixes for ringing and start-up, is all in Toit.

## When to write the driver in Toit

Use Zephyr's driver when it does what you need: the microphone's `dmic` driver did, and Toit wraps it in three
primitives. Write the driver in Toit when Zephyr's driver lacks the feature, as here. Then C only has to provide the
bus, and the chip-specific logic stays in a language where an error is an exception.
