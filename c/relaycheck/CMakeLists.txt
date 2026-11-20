cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(relaycheck)
# rete's BLE datagram seam, built in place (never copied): rete commit 2b8e9291.
set(RETE $ENV{HOME}/workspace/rete CACHE PATH "rete checkout")
set(OEVM ${RETE}/nodus/oevm/src)
target_include_directories(app PRIVATE ${OEVM} ${OEVM}/backend/zephyr)
target_sources(app PRIVATE src/main.c ${OEVM}/backend/zephyr/udp_ble.c)
