# ktau — tap, speak, act: a Toit-on-Zephyr bring-up on the XIAO nRF54L15 Sense

Design: `docs/design/2026-11-19-ktau-design.md`. One journal entry per rung in `docs/journal/`, the raw material
for a public blog post.

@FOCUS.md

- Build with `~/zephyr-4.5`, after `source ~/workspace/ztoit/env.sh` (else CMake: `TOIT_SRC is not set`): `PATH=~/zephyr-4.5/.venv/bin:$PATH ZEPHYR_BASE=~/zephyr-4.5/zephyr ZEPHYR_SDK_INSTALL_DIR=~/zephyr-sdk-1.0.1`, board `xiao_nrf54l15/nrf54l15/cpuapp`. Never `west zephyr-export` it, and never register SDK 1.0.1 (ztoit's 4.2 builds would pick them up).
- Console: `/dev/serial/by-id/usb-Seeed_Studio_Seeed_Studio_XIAO_nrf54_CMSIS-DAP_E96922FA-if02`, 115200, logged with `tools/serial_log.py <log> <port>`.
- Flash: `west flash -d <build> --cmd-pre-init "adapter serial E96922FA"` (openocd through the on-board CMSIS-DAP; the serial keeps it off the bench's other XIAO). J-Link on the SWD pads is the fallback.
- Board files, primitives and the BLE seam are ztoit commits (ztoit #41). ktau holds the Toit app, the receiver and the journal.
- Repo, journal and blog are public: before committing, run `git grep -n -i -f .private/public-text.txt -- <files>` (patterns git-ignored); matches need a look (some are harmless, e.g. Zephyr's own upstream).
- Never halt a running nRF (ztoit #23).
- Each rung records its token cost: `tools/tokens.py <start> <end>`.
- Reflashing a build is the reset: openocd erases only the image's sectors, so Toit apps in `toit_partition` survive (a different container is installed fresh).
