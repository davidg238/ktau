# Focus

- **Done as a demonstration (2026-11-21):** ktau ends at rung 7. Battery (rung 8) is out of scope (design doc,
  Decided). Two post drafts in `docs/posts/` await David's review; nothing is pushed until he has read them.
- **Next session starts with:** David's edits to `docs/posts/01-push-to-talk.md` and `02-imu-tap-driver.md`, then
  the public-text check and push.
- **Bench state:** the XIAO runs `~/zephyr-4.5/build-rung7` (build needs `source ~/workspace/ztoit/env.sh`), bonded
  to the Pixel. Receiver: `uv run -q --with faster-whisper --with numpy python -I server/receiver.py` on msi (port
  7700); the LLM is `http://z170:8080`.
- **Repo:** public at github.com/davidg238/ktau (MIT); `private-history` is local only, never pushed. `samples/` is
  git-ignored; host liblc3 is `~/.local/lib/ktau/liblc3.so`.
- **Open:** #1, #2, #4, #5 (P3 minors on the demo code).
- **Decided (design doc, Decided):** Approach A; Zephyr 4.5; Toit owns the IMU; push to talk; gain +10 dB, levels
  evened at the receiver; no-speech clips dropped; Android + rete's relay; receiver on msi, LLM on the z170 via
  `tailscale serve`; actions note/say/none, a refusal gets the long blink; ends at rung 7.
