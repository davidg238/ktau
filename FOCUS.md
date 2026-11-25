# Focus

- **Next session starts with:** branch `main`, focus #6. First action: a frame format and an integer C synth for
  residual-excited LPC at 8 kHz (clip 2 of `tools/relp_reference.py`), bit-exact against a Python model the way
  `c/lpcsynth` is against `tools/lpc_codec.py`. Then the CMU kal diphone table on top.
- **State:** the MAX98357A works; three fixes, all in `c/phrasecheck` (`docs/hookup.md`). The Toit firmware needs
  the same three (ztoit board files). Speech decisions and listening results: the 2026-11-24 addenda in
  `docs/design/2026-11-23-on-board-speech-sketch.md`.
- **Awaiting David:** nothing.
- **Bench:** XIAO cd2e runs `build-ktau-pcmplay` and speaks at every boot (`~/workspace/board-alloc.md`).
- **Build/flash:** see CLAUDE.md; apps under `c/` build with `west build -b xiao_nrf54l15/nrf54l15/cpuapp -d ~/zephyr-4.5/build-ktau-<name> c/<name>`.
  `c/*/phrases/` and `c/*/clips/` are git-ignored (TTS-derived audio); each `CMakeLists.txt` says how to make them.
- **Open:** #1, #2, #4, #5, #7 (P3); #6.
- **Decided (2026-11-24, sketch addenda):** unlimited phrases, not canned; the phoneme path uses residual-excited
  LPC at 8 kHz order 10, not plain LPC; diphones from CMU kal (keep CMU's notice); LC3 16 kbit/s is the measured
  option for any canned speech; no audio from the Piper lessac voice in the public repo.
- **Decided (2026-11-23):** server sends phonemes + duration + pitch. Pins: `docs/hookup.md`.
