# Focus

- **Next session starts with:** branch `main`, focus #6 (speech reply over Thread). First action: start
  `tools/thread_bench_server.py 7790 audio` on the border router and carry the XIAO to other rooms (range and a
  second hop), before any audio hardware work.
- **Awaiting David:** ztoit #53 (an app-held rx-on for an exchange) blocks the reply path; a MAX98357A wired to the
  XIAO for I2S.
- **Bench state:** boards are in `~/workspace/board-alloc.md` (ktau owns XIAO cd2e). It runs
  `~/zephyr-4.5/build-ktau-thread-rxon`: Thread, no agent, the bench app, built from a scratch copy of the Toit
  fork with the experimental rx-on patch (ztoit #53; the copy is gone after a reboot). The Pixel bond is gone
  (ztoit #51): rung 7 needs a reflash of `build-rung7` (`source ~/workspace/ztoit/env.sh` first) and re-pairing "ztoit".
- **Receiver:** `uv run -q --with faster-whisper --with numpy python -I server/receiver.py` on msi (port 7700); the
  LLM is `http://z170:8080`.
- **Repo:** public at github.com/davidg238/ktau (MIT); `private-history` is local only, never pushed. `samples/` is
  git-ignored (raw Thread runs: `samples/thread-bench-2026-11-22/`); host liblc3 is `~/.local/lib/ktau/liblc3.so`.
  Posts are published on ekorau.com (`docs/posts/` is their source; edit there and in the site together).
- **Open:** #1, #2, #4, #5 (P3 minors on the demo code); #6.
- **Decided (design doc, Decided and the 2026-11-22 addendum):** Approach A; Zephyr 4.5; Toit owns the IMU; push to
  talk; gain +10 dB, levels evened at the receiver; no-speech clips dropped; receiver on msi, LLM on the z170;
  actions note/say/none; the demo ended at rung 7; the reply goes over Thread, talk then reply, 100 ms datagrams.
