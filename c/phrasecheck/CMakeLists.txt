cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(phrasecheck)
target_sources(app PRIVATE src/main.c ../lpcsynth/lpc_synth.c)
target_include_directories(app PRIVATE ../lpcsynth)
# phrases/ is git-ignored (audio derived from a TTS voice). Make it with:
#   tools/lpc_codec.py phrase "<text>" c/phrasecheck/phrases/<name>.lpc
foreach(phrase i-cant-reach-the-server note-saved battery-low-please-charge-me-soon)
  generate_inc_file_for_target(app phrases/${phrase}.lpc ${ZEPHYR_BINARY_DIR}/include/generated/${phrase}.inc)
endforeach()
