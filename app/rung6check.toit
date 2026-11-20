// ktau rung 6, the checks on the board: UDP over BLE through the Pixel relay to
// udp-echo6 on a tailnet host. Prints PASS/FAIL per check.
import net
import net.udp

ECHO-HOST ::= "fd7a:115c:a1e0::bf01:d921"  // gw85224-01 on the tailnet.
ECHO-PORT ::= 7777
TIMEOUT-MS ::= 3_000
MAX-DATAGRAM ::= 1280  // udp_ble.cc, as udp_zephyr.cc.

target ::= net.SocketAddress (net.IpAddress.parse ECHO-HOST) ECHO-PORT

check name/string [block] -> none:
  why := catch: block.call
  if why: print "FAIL $name: $why"
  else: print "PASS $name"

echo socket/udp.Socket message/ByteArray -> none:
  socket.send (udp.Datagram message target)
  reply := with-timeout --ms=TIMEOUT-MS: socket.receive
  if reply.data != message: throw "got $reply.data.size B, not the $message.size B sent"

main:
  network/net.Client? := null
  while not network:
    error := catch: network = net.open
    if error: print "open failed: $error"
  try:
    check "echo-one":
      socket := network.udp-open
      try: echo socket "x".to-byte-array
      finally: socket.close

    check "two-sockets":
      a := network.udp-open
      b := network.udp-open
      try:
        a.send (udp.Datagram "from a".to-byte-array target)
        b.send (udp.Datagram "from b".to-byte-array target)
        ra := with-timeout --ms=TIMEOUT-MS: a.receive
        rb := with-timeout --ms=TIMEOUT-MS: b.receive
        if ra.data.to-string != "from a": throw "a got $ra.data.to-string"
        if rb.data.to-string != "from b": throw "b got $rb.data.to-string"
      finally:
        a.close
        b.close

    check "too-big":
      socket := network.udp-open
      try:
        error := catch: socket.send (udp.Datagram (ByteArray MAX-DATAGRAM + 1) target)
        if not error: throw "a $(MAX-DATAGRAM + 1) B datagram was accepted"
        print "  $(MAX-DATAGRAM + 1) B: $error"
        echo socket (ByteArray MAX-DATAGRAM: it & 0xff)
      finally:
        socket.close
  finally:
    network.close
