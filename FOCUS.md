# Focus

- **Next session starts with (Opus):** rung 6, ztoit `net.udp` over rete's BLE relay; an echo from a tailnet host
  (ztoit #41). First: write its plan with superpowers:writing-plans from the design doc's rung 6. Rung 5 is done
  (`docs/journal/05-lc3-encode.md`): push to talk, LC3 at 32 kbit/s, 5/5 phrases through Whisper.
- **Repo:** public at github.com/davidg238/ktau (MIT); the pre-publication history is the local branch `private-history`, never pushed.
  `samples/` (David's recordings) is git-ignored; host liblc3 for `tools/lc3dec.py` is `~/.local/lib/ktau/liblc3.so`.
- **Open:** #1 (P3) lsm6ds3 driver cleanup; #2 clip2wav; #3 (P3) two-mic boom/glasses idea; #4 (P3) rung 5 review minors.
- **Decided (design doc):**
  - Approach A, the ladder. Zephyr 4.5 upgrade. Toit owns the IMU.
  - On nRF: sleep, not deep sleep.
  - Push to talk on the user button; the board held at the mouth for the demo (2026-11-20).
  - Audio streams only after LC3; gain +10 dB; rung 7 drops clips Whisper marks as no speech.
  - Android and rete's relay. Rung 7 is a small script. The blog is public. Token count per rung.
  - 2×AAA and David's enclosure for the first prototype.
