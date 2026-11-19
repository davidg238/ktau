// ktau rung 2: the Toit VM on the XIAO nRF54L15. Zephyr's C blinky, in Toit:
// the board's LED (devicetree label led0) toggles every 500 ms.
import system
import zephyr

report label/string:
  s := system.process-stats --gc
  print "$label: process allocated=$s[system.STATS-INDEX-ALLOCATED-MEMORY] reserved=$s[system.STATS-INDEX-RESERVED-MEMORY]"

main:
  print "ktau rung 2"
  report "start"
  led := zephyr.Led "led0"
  on := false
  while true:
    on = not on
    led.set on
    sleep --ms=500
