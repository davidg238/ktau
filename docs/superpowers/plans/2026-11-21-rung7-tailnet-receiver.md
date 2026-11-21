# Rung 7: the receiver on the tailnet — push to talk → LC3 over the relay → Whisper → LLM → action — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hold the XIAO's button and speak; the board streams LC3 through the Pixel relay to a receiver on msi, which
transcribes it with Whisper, asks the z170's LLM for one action from a short allowlist, carries it out, and replies;
the board's LED confirms. Journal entry 7 records it.

**Architecture:**
- **Device** (`app/rung7.toit`): rung 5's push to talk with rung 6's socket. Each 100 ms block is encoded and sent
  as one datagram as soon as it is read (400 B, the rate rung 6 carried 50/50). On release, an END datagram, sent
  3 times 50 ms apart. Then it waits up to 30 s for the reply and blinks `led0`. No fork or ztoit change.
- **The wire** (decided here; the design left it to the builder). Big-endian:
  - audio: `clip:u16 | seq:u16 | 10 × 40 B LC3` (one 100 ms block, `seq` from 0);
  - end: `clip:u16 | 0xFFFF | blocks:u16`;
  - reply (receiver → the datagram's source): `clip:u16 | status:u8`, status `0` ACTED, `1` NO-SPEECH, `2` FAILED.
  The LC3 format is fixed on both sides: 16 kHz, 10 ms frames, 40 B (rung 5's `Lc3Encoder`).
- **Receiver** (`server/`, Python, on msi, port `7700` on `::`): reassemble → decode with host liblc3 (a missing
  block is 100 ms of silence) → peak-normalise (the design: levels are evened out here, not by device gain) →
  faster-whisper `medium.en`, CPU int8, loaded once → drop no-speech → LLM → action → reply. One clip at a time;
  per-stage times printed.
- **LLM:** the llama.cpp server already running on the z170 (Qwen3.6-35B-A3B, OpenAI-compatible, `127.0.0.1:8080` there),
  published to the whole tailnet by `tailscale serve --tcp 8080` (2026-11-21): `http://z170:8080`, tailnet only.
  The z170's server itself is not touched. Thinking off (`chat_template_kwargs: {"enable_thinking": false}`), `response_format` JSON.
- **Actions** (allowlist; anything else is FAILED): `say` (`spd-say <text>` on msi), `note` (append a timestamped
  line to `~/.local/state/ktau/notes.txt`), `none` (just answer). The LLM returns `{"action", "text"}`.
- **LED** (the board has one user LED, `led0`; the red charge LED is the charger's, not a GPIO): lit while
  recording (rung 5); ACTED → 2 short blinks; NO-SPEECH or FAILED → 1 long (600 ms); no reply in 30 s → 5 fast.

**Tech Stack:** Toit on ztoit (`~/zephyr-4.5`, the rung 6 build recipe with `prj_ble.conf`), Python 3 stdlib,
faster-whisper + numpy via `uv run`, host liblc3 (`~/.local/lib/ktau/liblc3.so`, `tools/lc3dec.py`'s loader),
ffmpeg, llama.cpp `llama-server` on the z170, `spd-say`.

**Spec:** `docs/design/2026-11-19-ktau-design.md` (rung 7; "The device and the path" step 4; Decided: gain fixed
and levels evened at the receiver; no-speech clips dropped; push to talk; rung 7 starts as a small script).

## Global Constraints

- The board, console, logger and flashing rules of the rung 6 plan apply unchanged
  (`docs/superpowers/plans/2026-11-20-rung6-udp-over-ble.md`). Never halt a running nRF (ztoit #23).
- Whisper runs as `uv run -q --with faster-whisper --with numpy python -I …`; audio goes in as a float32 numpy array
  (PyAV's file decode is broken on msi), never a path.
- No new tunables beyond the ones named here: no-speech threshold `0.6` (journal 05: silence scored ≈ 0.9),
  normalise to peak `0.9` of full scale, END ×3 at 50 ms, idle finish 1.5 s, device reply wait 30 s.
- The z170's `llama-server` is shared: no restart or reconfiguration. Undo the tailnet serve with `tailscale serve --tcp=8080 off`.
- Public text: ktau's `git grep -n -i -f .private/public-text.txt`. msi's tailnet address appears in `rung7.toit`
  as the receiver; David to confirm that is fine, as the echo host's was.
- Commits in ktau; one ≤ 5-line comment on ztoit #41 at the end (`refs`, never a closing keyword).
- **The bench needs David** (bench call sound): Pixel relay and Tailscale up, board at the mouth.

## Review Focus

1. **The END datagram is lost** (all 3). Expected: the clip still finishes 1.5 s after its last block. Task 1 tests it.
2. **A block is lost mid-clip.** Expected: 100 ms of silence in its place, not a shortened or failed clip. Task 1.
3. **The LLM answers with prose, broken JSON, or an action not on the list.** Expected: FAILED reply, nothing
   run, the raw answer printed. Task 2 tests it.
4. **A press with no speech** (or a tap of the button). Expected: NO-SPEECH reply, no LLM call. Task 3 checks it
   with a silent clip; Task 4 on the bench.
5. **The z170 or its LLM is down.** Expected: FAILED within 10 s (HTTP timeout), the receiver keeps running.
   Task 3 checks it with `--llm` pointed at a closed port.

---

### Task 1: Clip reassembly — `server/clips.py`, host-tested

**Files:**
- Create: `server/clips.py`, `server/test_clips.py`.

**Interfaces:**
- Produces: `Assembler(idle_s=1.5)` with `feed(src, data: bytes, now: float) -> list[Clip]` and
  `expire(now: float) -> list[Clip]`; `Clip(src, clip_id: int, frames: list[bytes | None])` — one entry per
  100 ms block, `None` where lost. `encode_audio(clip_id, seq, lc3: bytes) -> bytes`,
  `encode_end(clip_id, blocks) -> bytes`, `encode_reply(clip_id, status) -> bytes`; `ACTED, NO_SPEECH, FAILED = 0, 1, 2`.

- [ ] **Step 1: Write the failing tests** (`python3 -m unittest server/test_clips.py`):
  - `end_finishes`: blocks 0–2 then END(3) → one `Clip` with 3 frames, none `None`.
  - `duplicate_end_ignored`: END sent 3 times → exactly one `Clip`.
  - `lost_block_is_none`: blocks 0, 2 then END(3) → frames `[b, None, b]` (Review Focus 2).
  - `lost_end_expires`: blocks 0–1, no END; `expire(now + 1.4)` → `[]`; `expire(now + 1.6)` → one clip (Review Focus 1).
  - `new_clip_finishes_old`: blocks of clip 5, then a block of clip 6 from the same `src` → clip 5 returned.
  - `two_sources_apart`: clip 1 from two `src` interleaved → two separate clips.
  - `short_or_bad_ignored`: 3-byte datagram, audio payload not 400 B → ignored, no exception.
  - `cap`: `seq ≥ 100` ignored (50 blocks is the device's 5 s cap; 100 is the guard).
- [ ] **Step 2:** Run → FAIL (no module).
- [ ] **Step 3:** Implement `server/clips.py`, stdlib only.
- [ ] **Step 4:** Run → PASS. Break `lost_end_expires` (set `idle_s=10`), see it fail, restore.
- [ ] **Step 5:** Commit: `Rung 7: clip reassembly for the receiver, host-tested`.

### Task 2: LLM and actions — `server/act.py`, host-tested

**Files:**
- Create: `server/act.py`, `server/test_act.py`.

**Interfaces:**
- Produces: `ask(text: str, url: str, timeout_s=10) -> str` (the raw model answer; raises on HTTP error/timeout);
  `parse(answer: str) -> tuple[str, str]` (`(action, text)`; raises `ValueError` if not JSON, a missing key, or an
  action not in `ACTIONS = ("say", "note", "none")`); `run(action, text, notes_path, say=…) -> None`.
  `SYSTEM_PROMPT`: one paragraph naming the three actions and the JSON shape; `say` text is what to speak back,
  `note` text is what to keep, `none` text is a one-sentence answer.

- [ ] **Step 1: Write the failing tests:**
  - `parse_ok`: `'{"action":"note","text":"buy milk"}'` → `("note", "buy milk")`.
  - `parse_rejects`: prose, `'{"action":"shell","text":"rm"}'`, `'{"text":"x"}'`, `''` → `ValueError` (Review Focus 3).
  - `note_appends`: two `run("note", …)` into a temp file → two lines, each `<ISO time> <text>`.
  - `say_calls_runner`: `run("say", "hi", …, say=fake)` → `fake` got `["spd-say", "hi"]`; `none` runs nothing.
  - `ask_body`: against a stub `http.server` on localhost: the request has the system prompt, the text,
    `enable_thinking: false`, `response_format` JSON; returns the stub's `choices[0].message.content`.
  - `ask_timeout`: stub that never answers, `timeout_s=1` → raises within 2 s.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement with `urllib.request` (no SDK). `POST {url}/v1/chat/completions`, `temperature 0`.
- [ ] **Step 4:** Run → PASS. Then once against the real model: `python3 -c` `ask("remind me to buy milk")`
  → `parse` gives `note`; record the answer time.
- [ ] **Step 5:** Commit: `Rung 7: LLM call and the action allowlist, host-tested`.

### Task 3: The receiver and a host sender — `server/receiver.py`, `tools/sendclip.py`

**Files:**
- Create: `server/receiver.py`, `tools/sendclip.py`.

**Interfaces:**
- Consumes: Task 1's `Assembler`, `encode_*`; Task 2's `ask`, `parse`, `run`; `tools/lc3dec.py`'s `lc3()` and `LIBPATH`.
- Produces: `receiver.py [--port 7700] [--llm http://z170:8080] [--model medium.en]`; one line per clip:
  `clip <id> from <src>: <blocks> blocks (<lost> lost) | stt <s> s "<text>" nsp=<p> | llm <s> s <action> "<text>" | <STATUS>`.
  `sendclip.py <audio-file> <host> [--port 7700] [--drop SEQ,…] [--no-end] [--write F.lc3 | --read F.lc3]`: ffmpeg → 16 kHz mono → LC3 with the host
  encoder (or `--read` a dump `--write` made, for hosts without liblc3) → datagrams at 100 ms, exactly as the device sends them; prints the reply status or `no reply`.

- [ ] **Step 1:** `receiver.py`: a `socket(AF_INET6)` bound to `::` with `IPV6_V6ONLY` off; loop with a 0.25 s
  timeout calling `feed`/`expire`; per finished clip: decode (`None` → 320 zero samples per frame), normalise to
  peak 0.9, transcribe (`vad_filter` off; text = joined segments; nsp = max `no_speech_prob`); nsp ≥ 0.6 or empty
  text → NO-SPEECH; else `ask`/`parse`/`run`, any exception → FAILED with the reason printed; reply to `src`.
- [ ] **Step 2:** Local run, receiver and sender on msi (`::1`): `sendclip.py samples/sample-qb.m4a ::1` → the
  transcript matches journal 05's, status ACTED or FAILED with a printed reason; `samples/kitchen-lights-parrot.m4a`
  → `none` with an answer that it cannot control lights.
- [ ] **Step 3:** The Review Focus cases through the sender: `--drop 3` → `(1 lost)`, still transcribed;
  `--no-end` → finishes after 1.5 s; a 2 s silent file (`ffmpeg -f lavfi -i anullsrc`) → NO-SPEECH, no `llm` stage;
  `--llm` at a closed port → FAILED within 10 s, and the receiver takes the next clip.
- [ ] **Step 4:** From the tailnet: `sendclip.py … fd7a:115c:a1e0::8733:894a` run on gw85224-01 (copy the script and
  a WAV; no liblc3 there → send the dump from `sendclip.py --write` on msi, sent with `--read`). Expected: a reply
  arrives, so msi's firewall passes UDP 7700 on the tailnet. If not, record and fix before Task 4.
- [ ] **Step 5:** Commit: `Rung 7: the receiver, and a host sender that speaks the device's wire`.

### Task 4: The device, the bench, journal 07

**Files:**
- Create: `app/rung7.toit`, `docs/journal/07-tailnet-receiver.md`.

**Interfaces:**
- Consumes: the wire above; rung 5's `Key`, `Led`, `Microphone`, `Lc3Encoder`; rung 6's `net.open` loop.

- [ ] **Step 1:** `rung7.toit`: `RECEIVER ::= "fd7a:115c:a1e0::8733:894a"`, `PORT ::= 7700`. Open `net` as rung 6
  does, one socket for the program. Per press: clip id +1 (wraps at 0xFFFF); start, discard the first block
  (journal 04), LED on, each block → `encode_audio` shape → send; on release or 50 blocks: stop, LED off, END ×3.
  Wait up to 30 s for a reply with this clip id (others are dropped); blink per Architecture; print
  `clip <id>: <blocks> sent, reply <status>|none in <ms> ms`.
- [ ] **Step 2:** Build with the rung 6 recipe and `rung7.toit` as the container; flash (the bond survives).
  Receiver running on msi; logger on the console.
- [ ] **Step 3:** Bench (David): 5 phrases — 2 notes, 2 say, 1 question. Expected: ≥ 4/5 acted as meant, 2 short
  blinks each; record the time from release to blink. Then one press with no speech → 1 long blink (Review Focus 4).
  Then receiver stopped → 5 fast blinks after 30 s, and the board keeps working when it is back.
- [ ] **Step 4:** Journal 07 in journal 06's layout: what it took (time, lines of Toit and Python, tokens from
  `tools/tokens.py`), what broke, the evidence (transcripts, per-stage times, release-to-blink, the Review Focus
  results). Public-text grep.
- [ ] **Step 5:** Commit: `Rung 7: tap, speak, act through the receiver; journal 07`. Comment on ztoit #41 (≤ 5
  lines: the numbers, the ktau commit). Update ktau `FOCUS.md` for rung 8.
