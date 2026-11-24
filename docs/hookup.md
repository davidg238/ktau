# Hookup: MAX98357A I2S amp on the XIAO nRF54L15 Sense (cd2e)

For on-board speech (#6, S2). Module: `max98357a.png`; bench as wired 2026-11-23: `hookup-breadboard.jpg`.

| MAX98357A | XIAO | nRF54L15 | Why |
|---|---|---|---|
| BCLK | D0 | P1.04 | I2S20 is P1-only; SCK must be a dedicated clock pin (datasheet 8.8.5, pin table) |
| DIN | D1 | P1.05 | data next to its clock pin |
| LRC | D5 | P1.11 | the other clock pin on the header; Zephyr's I2S tests use clock pins for LRCK too |
| Vin | 3V3 (as wired) | — | amp takes 2.5–5.5 V; 5V is louder but likely unpowered on battery (unchecked) |
| GND | GND | — | |
| GAIN | open | — | 9 dB |
| SD | open | — | (L+R)/2, suits mono; later to D2 to shut the amp down between phrases |
| speaker | terminal block | — | 4–8 Ω |

Taken on the board: P1.12/P1.13 (PDM mic), P1.08/P1.09 (console UART), P0.03/P0.04 (IMU, `i2c30`). D4/D5 are
Zephyr's default I2C pins but ktau does not use them.

## Status (2026-11-23): I2S does not run yet

- **Keep Vin unplugged while debugging.** With clocks but no valid data the amp plays loud noise; the sample
  amplitude does not control it.
- `c/tonecheck` (Zephyr I2S driver) and `c/i2sbare` (registers only, no driver) both stall after the first
  buffer: one TXPTRUPD, then none. On D0/D5 no frame ever starts; on P1.11/P1.12 exactly one does. No EasyDMA
  bus error. Not changed by: clock source, 8 vs 16 kHz, HFXO + PLL held on, clock-pin input buffers connected.
- Next lead: the MCKFREQ value (`MCKFREQ_512K` in `c/i2sbare/src/main.c`) uses the driver's formula; the
  datasheet gives the equation only as a figure (Figure 66), unverified. Then the nRF54L15 errata in full.
- Logs: `samples/tonecheck-2026-11-23.log`, `samples/i2sbare-2026-11-23.log` (git-ignored).
