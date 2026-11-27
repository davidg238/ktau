# Focus

- **Next session starts with:** branch `main`. If ztoit's rename has reached the fork's `zephyr-port` (fork
  `70f833fe` is the local commit; ztoit `a2ef051`), first move to it: `import zephyr` → `import ztoit` in the 8
  apps under `app/`, rerun ztoit's `tools/fork-sdk.sh`, rebuild both rung 8 images. Else focus #7 (the nRF
  802.15.4 driver panic): count restarts in `samples/rung8-2026-11-25.log` since 16:34; ztoit #26 is kin.
- **State:** rung 8 demonstrated over Thread and over the BLE relay (`docs/journal/08-spoken-answer.md`). Tests:
  `python3 -m unittest tools/test_*.py server/test_*.py`.
- **Awaiting David:** read and deploy the post (`docs/posts/01-push-to-talk.md`; site copy committed in
  `~/ekorau-website`, not deployed). The phone relay's battery cost: rete #534 (P1).
- **Bench:** XIAO cd2e runs `build-ktau-rung8-thread`; `build-ktau-rung8-ble` is bonded to the Pixel
  (`~/workspace/board-alloc.md`). Receiver on the z170, started by hand (#9).
- **Build/flash:** see CLAUDE.md; rung 8's command is in `c/speech/CMakeLists.txt`.
- **Open:** #1, #2, #4, #5, #7, #8, #9.
- **Decided (2026-11-27, design addendum):** ktau stays the simple demo; streamed replies and the better voice go
  to the private follow-on repo.
- **Decided (2026-11-25, design addendum):** two links, one per firmware; server on the z170; spoken answers one
  sentence of at most 15 words; clips up to 30 s; a fatal error restarts the board; the LAN hop stays plain UDP.
- **Decided (2026-11-25, sketch addendum):** the voice is 2 bits a sample.
- **Decided (2026-11-24):** no Piper lessac audio in the public repo; Flite's copyright ships with the table.
