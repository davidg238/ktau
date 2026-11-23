# Focus

- **Next session starts with:** branch `main`, focus #6 (speech reply, now the on-board LPC synth). First action:
  S2 — once the MAX98357A is wired, play `samples/lpc-phrases-2026-11-23/i-cant-reach-the-server.lpc` through
  `c/lpcsynth` on the XIAO (I2S), and measure cycles per sample.
- **Awaiting David:** MAX98357A + speaker wired to the XIAO (I2S pins still unchecked); a listen to the canned
  phrases in `samples/lpc-phrases-2026-11-23/` (Whisper is a poor judge of short 8 kHz clips).
- **Bench state:** boards are in `~/workspace/board-alloc.md` (ktau owns XIAO cd2e, running `build-ktau-thread-rxon`).
  The Pixel bond is gone (ztoit #51): rung 7 needs a reflash of `build-rung7` and re-pairing "ztoit".
- **Receiver:** `uv run -q --with faster-whisper --with numpy python -I server/receiver.py` on msi (port 7700); the
  LLM is `http://z170:8080`.
- **Repo:** public (MIT); `private-history` local only. `samples/` is git-ignored. Posts on ekorau.com (`docs/posts/`).
- **Open:** #1, #2, #4, #5 (P3 minors); #6. Piper is not deterministic: phrase blobs differ per run.
- **Decided:** see the design doc's Decided and addenda; 2026-11-23: the on-board LPC speech sketch is adopted (8 kHz,
  order 10, natural pitch; server sends phonemes + duration + pitch; canned phrases offline); ztoit #53 no longer
  blocks the reply.
