cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(lc3play)
target_sources(app PRIVATE src/main.c ../lpcsynth/lpc_synth.c)
target_include_directories(app PRIVATE ../lpcsynth)
# phrases/ is git-ignored (audio derived from a TTS voice). Make it with:
#   tools/lc3_reference.py, then copy the .lc3 files from samples/; the .lpc as for c/phrasecheck
foreach(phrase i-cant-reach-the-server.lpc i-cant-reach-the-server-16k.lc3 i-cant-reach-the-server-32k.lc3)
  generate_inc_file_for_target(app phrases/${phrase} ${ZEPHYR_BINARY_DIR}/include/generated/${phrase}.inc)
endforeach()
