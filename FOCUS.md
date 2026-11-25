# Focus

- **Next session starts with:** branch `main`, focus #7 (the nRF 802.15.4 driver panic). First action: count the
  restarts in `samples/rung8-2026-11-25.log` since 16:34, then look for the assertion upstream (ztoit #26 is kin).
- **State:** rung 8 is demonstrated over Thread and over the BLE relay: the board speaks the LLM's answer
  (`docs/journal/08-spoken-answer.md`). Tests: `python3 -m unittest tools/test_*.py server/test_*.py`.
- **Awaiting David:** read and deploy the post (`docs/posts/01-push-to-talk.md`; the site copy is committed in
  `~/ekorau-website`, not deployed).
- **Bench:** XIAO cd2e runs `build-ktau-rung8-thread`; the BLE build is `build-ktau-rung8-ble`, bonded to the Pixel
  (`~/workspace/board-alloc.md`). The receiver runs on the z170, started by hand (#9).
- **Build/flash:** see CLAUDE.md. Rung 8 firmware is ztoit's app plus `c/speech`; the command is in
  `c/speech/CMakeLists.txt`. `c/*/phrases/` and `c/*/clips/` are git-ignored (derived audio and the kal table).
- **Open:** #1, #2, #4, #5, #7, #8, #9 (P3).
- **Decided (2026-11-25, design addendum):** two links, one per firmware; server on the z170, Whisper `small.en`
  on the 3050 with a CPU fallback; spoken answers are one sentence of at most 15 words, `none` spoken too; clips up
  to 30 s; a fatal error restarts the board; the LAN hop stays plain UDP.
- **Decided (2026-11-25, sketch addendum):** the voice is 2 bits a sample.
- **Decided (2026-11-24):** no audio from the Piper lessac voice in the public repo; Flite's copyright ships with
  the table (`licenses/flite-copyright`).
