# Focus

- **Next session starts with:** branch `main`, focus #6. First action: the Toit side — carry the three I2S fixes
  (`docs/hookup.md`) into ztoit's board files, then a primitive that hands `c/kalsynth` a wire phrase, with the
  table in flash. Then the server makes the wire bytes (phones + ms + f0).
- **State:** the board speaks any phone string: `c/kalcheck` runs the C diphone synth over the kal table
  (`tools/kal_diphones.py build`). Formats, measurements and listening results: the 2026-11-24 addenda in
  `docs/design/2026-11-23-on-board-speech-sketch.md`. Tests: `python3 -m unittest tools/test_*.py`.
- **Awaiting David:** nothing.
- **Bench:** XIAO cd2e runs `build-ktau-pcmplay` with the 3-bit and 2-bit kal clips (`~/workspace/board-alloc.md`).
- **Build/flash:** see CLAUDE.md; apps under `c/` build with `west build -b xiao_nrf54l15/nrf54l15/cpuapp -d ~/zephyr-4.5/build-ktau-<name> c/<name>`.
  `c/*/phrases/` and `c/*/clips/` are git-ignored (derived audio and the kal table); each `CMakeLists.txt` says how to make them.
- **Open:** #1, #2, #4, #5, #7, #8 (P3); #6.
- **Decided (2026-11-24, sketch addenda):** the voice is our kal table, residual-excited LPC at 8 kHz, 3 bits a
  sample until the flash is needed (2 bits is adequate, 577 KB against 780); wire is 4 bytes a phone; a missing
  diphone plays as a short pause, for now; Flite's copyright ships with the table (`licenses/flite-copyright`).
- **Decided (2026-11-24):** unlimited phrases, not canned; LC3 16 kbit/s for any canned speech; no audio from the
  Piper lessac voice in the public repo.
- **Decided (2026-11-23):** server sends phonemes + duration + pitch. Pins: `docs/hookup.md`.
