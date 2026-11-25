# 08 — The board speaks the answer

Rung 8, 2026-11-25 (#6).

## What we set out to do

Hold the button, ask, and hear the answer from the board. The server sends what to say as phonemes (4 bytes each:
phone, duration, pitch); the board's C synth renders them from a diphone table in flash and plays them through the
MAX98357A. Then the same over both links: Thread at home, a phone's BLE relay and the tailnet away from it.

## What it took

- **Wall time:** one day's session, about 7 h 40 min, much of it at the bench.
- **Tokens (Claude Code):** 180 k output, 483 k cache-write, 34.6 M cache-read, from `tools/tokens.py
  2026-11-25T15:57:06Z 2026-11-25T23:36:00Z`.
- **In the Toit fork:** `zephyr.Speech` (`say`, `speaking`, `wait`) over two primitives that call weak C hooks, the
  pattern of `ztoit_link_up`; 57 lines in four files.
- **In ktau, C:** `c/speech`, a Zephyr module that overrides the hooks: a player thread renders with `c/kalsynth`
  and plays at twice the synth's rate (`docs/hookup.md`). Its overlay carries the I2S fixes and moves
  `toit_partition` up to make room for the table (`CONFIG_FLASH_LOAD_SIZE` in `c/speech/prj_speech.conf`).
- **In ktau, Toit:** `app/rung8.toit` (70 code lines), rung 7 plus speaking the reply; `app/rung8ble.toit` gives it
  the tailnet address for the BLE firmware.
- **The server:** `server/speak.py` turns the LLM's text into phones with Flite's front end and cuts at the last
  pause that fits one datagram (`MAX_WIRE` in `server/clips.py`). `say` and `none` are both spoken; the prompt asks
  for one sentence of at most 15 words. The `spd-say` action is gone.

## What broke

- **780 KB of voice beside Thread** left under 20 KB of flash free, so the table went to 2 bits a residual sample
  (`BITS` in `tools/relp_reference.py`): 577 KB, and David's ears accepted it.
- **Silence after a reset.** The firmware on the board had changed from one that speaks at boot to one that waits
  for the button. Say what is on the board.
- **The server moved to the z170** (Whisper beside the LLM) and the first reply never arrived: the z170 ignored the
  border router's advertised route to the mesh (`accept_ra_rt_info_max_plen` was 0). My test had come from the LAN,
  not the mesh.
- **Whisper out of GPU memory.** The LLM fills both cards; `small.en` fits in what is left of the 3050 but spikes
  past it now and then. The receiver now retries that clip on the CPU (`Whisper.__call__`).
- **The radio driver panics** (#7): an assertion in the nRF 802.15.4 driver, four times in a day, idle or
  mid-clip. A timer-driven soak (`app/soak.toit`, 153 clips) and a press test did not reproduce it; it is rare and
  not tied to the button. Not fixed: the firmware now restarts on a fatal error (`CONFIG_RESET_ON_FATAL_ERROR`).
- **BLE pairing timed out** eight times, 30 s each, until David approved the request on the phone.

## What ran

| Link | Server | Clips | Blocks lost | Reply after release |
|---|---|---|---|---|
| Thread | msi, Whisper `medium.en` on the CPU | 6 | 0 of 117 | 3.0–4.1 s |
| Thread | z170, Whisper `small.en` on the 3050 | 5 | 0 of 273 | 0.7–1.0 s |
| BLE relay + tailnet | z170 | 5 | 0 of 118 | 0.3–1.4 s |

- The longest question was 11.5 s; the clip limit is now 30 s (`MAX-BLOCKS`).
- Firmware: Thread 1191160 B of flash and 215820 B of RAM; BLE 1128960 B and 187376 B. The table is 591033 B.
- Logs (git-ignored): `samples/rung8-2026-11-25.log`, `samples/speechcheck-2026-11-25.log`; the receiver's is on
  the z170.

## Open

- #7: the driver panic, and silent boots after flashing.
- The receiver on the z170 is started by hand (`server/receiver-gpu.sh`); see the issue filed for a service.
