# Focus

- **Next session starts with (Opus):** rung 8, battery: sleep current and current per instruction, a lifetime
  estimate, the 2.0 V check (design doc, Constraints: Power). First: write its plan with superpowers:writing-plans.
  Rung 7 is done (`docs/journal/07-tailnet-receiver.md`): 4/4 phrases acted, release to blink 2.9–3.3 s.
- **Bench state:** the XIAO runs `~/zephyr-4.5/build-rung7` (build needs `source ~/workspace/ztoit/env.sh`), bonded
  to the Pixel. The receiver is `uv run -q --with faster-whisper --with numpy python -I server/receiver.py` on msi
  (port 7700); the LLM is `http://z170:8080`.
- **Repo:** public at github.com/davidg238/ktau (MIT); `private-history` is local only, never pushed. `samples/` is
  git-ignored; host liblc3 is `~/.local/lib/ktau/liblc3.so`.
- **Open:** #1, #3, #4, #5 (P3 review minors and ideas); #2 clip2wav.
- **Decided (design doc, Decided):** Approach A; Zephyr 4.5; Toit owns the IMU; ordinary sleep on nRF; push to talk;
  gain +10 dB, levels evened at the receiver; no-speech clips dropped; Android + rete's relay; receiver on msi, LLM on
  the z170 via `tailscale serve`; actions note/say/none, a refusal gets the long blink; 2×AAA first prototype.
