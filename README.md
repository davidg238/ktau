# ktau — push to talk, from Toit on Zephyr

A bring-up of [Toit on Zephyr](https://github.com/davidg238/ztoit) on a board it had never seen, the Seeed XIAO
nRF54L15 Sense: hold the button, speak a short instruction, and the audio streams as LC3 over Bluetooth LE and
Tailscale to an LLM on the tailnet, which acts on it; the LED says how it went. Built as a ladder of seven rungs,
each with a demo and a journal entry.

- Posts: `docs/posts/` (the push-to-talk chain; a tap driver in Toit)
- Journal, one entry per rung: `docs/journal/`
- Design: `docs/design/2026-11-19-ktau-design.md`
- The Toit app: `app/`; the receiver: `server/`

MIT licensed.
