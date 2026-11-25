# ktau #6: the board's voice as a Zephyr module of the ztoit firmware. Build ztoit's zephyr/ app with
#   -DZEPHYR_EXTRA_MODULES=<ktau>/c/speech -DEXTRA_DTC_OVERLAY_FILE=<ktau>/c/speech/speech.overlay
#   -DEXTRA_CONF_FILE="prj_thread.conf;prj_thread.local.conf;<ktau>/c/speech/prj_speech.conf"
#   -DCONTAINERS=<ktau>/app/rung8.toit   (for the BLE relay: prj_ble.conf in place of the two Thread files, and app/rung8ble.toit)
# The table is c/kalcheck's (git-ignored; c/kalcheck/CMakeLists.txt says how to make it), or -DKAL_TABLE=<file>.
if(CONFIG_KTAU_SPEECH)
  set(KAL_TABLE ${CMAKE_CURRENT_LIST_DIR}/../kalcheck/clips/kal-relp.bin CACHE FILEPATH "kal diphone table")
  if(NOT EXISTS ${KAL_TABLE})
    message(FATAL_ERROR "no ${KAL_TABLE}: see c/kalcheck/CMakeLists.txt")
  endif()
  zephyr_library()
  zephyr_library_sources(speech.c ../kalsynth/kal_synth.c ../relpsynth/relp_synth.c)
  zephyr_library_include_directories(../kalsynth ../relpsynth ../lpcsynth)
  generate_inc_file_for_target(${ZEPHYR_CURRENT_LIBRARY} ${KAL_TABLE} ${ZEPHYR_BINARY_DIR}/include/generated/kal_table.inc)
endif()
