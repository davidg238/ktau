// ktau rung 8 through a phone: the firmware is built with ztoit's BLE relay link (prj_ble.conf) in place of Thread,
// and the receiver is reached at its tailnet address. The rest is app/rung8.toit.
import .rung8

RECEIVER ::= "fd7a:115c:a1e0::bc33:3332"  // The server on the tailnet.

main:
  run RECEIVER
