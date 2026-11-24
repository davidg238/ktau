# Focus

- **Next session starts with:** branch `main`, focus #6 S2 (I2S out to the MAX98357A). First action: get the
  nRF54L15 MCKFREQ equation (datasheet Figure 66, or Nordic's online I2S page), then sweep MCKFREQ in
  `c/i2sbare` (silent, registers only) until TXPTRUPD reaches ~50/s. Then read the nRF54L15 errata in full.
- **State:** `docs/hookup.md` (pins, status, what is ruled out). The LPC synth is done and host-tested
  (`c/lpcsynth`, `tools/lpc_codec.py`, `tools/test_lpc_codec.py`); phrases in `samples/lpc-phrases-2026-11-23/`.
- **Awaiting David:** keep the amp's Vin unplugged until a run shows buffers advancing (clocks without data = loud
  noise); first audible test ≤ −36 dBFS and ≤ 3 s. A listen to the canned phrases.
- **Bench:** XIAO cd2e runs `build-ktau-i2sbare` (`~/workspace/board-alloc.md`). `build-ktau-thread-rxon` cannot be
  rebuilt (its scratch source was lost in the crash). Pixel bond gone (ztoit #51).
- **Build/flash:** see CLAUDE.md; apps under `c/` build with `west build -b xiao_nrf54l15/nrf54l15/cpuapp -d ~/zephyr-4.5/build-ktau-<name> c/<name>`.
- **Open:** #1, #2, #4, #5 (P3); #6. Unexplained: one CPU fault (stack corrupted, near printk state) during an I2S run.
- **Decided:** the on-board LPC speech sketch (2026-11-23, design doc addendum): 8 kHz order 10 natural pitch;
  server sends phonemes + duration + pitch; canned phrases offline; ztoit #53 no longer blocks the reply.
  Hookup pins: BCLK D0/P1.04, DIN D1/P1.05, LRC D5/P1.11 (may change if these pins cannot clock I2S).
