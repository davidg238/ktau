// ktau rung 6: UDP through the Pixel's BLE relay to udp-echo6 on a tailnet host.
// 20 pings of 16 B, one a second; then a stream of 400 B datagrams, one per 100 ms:
// one 100 ms block of LC3 at 32 kbit/s (rung 5), each echoed back. Prints round
// trips and losses.
import net
import net.udp

ECHO-HOST ::= "fd7a:115c:a1e0::bf01:d921"  // gw85224-01 on the tailnet.
ECHO-PORT ::= 7777
PINGS ::= 20
STREAM ::= 50
BLOCK-BYTES ::= 400   // 10 LC3 frames of 40 B (rung 5).
BLOCK-MS ::= 100
TIMEOUT-MS ::= 1_000

target ::= net.SocketAddress (net.IpAddress.parse ECHO-HOST) ECHO-PORT

median list/List -> int:
  if list.is-empty: return -1
  sorted := list.sort
  return sorted[sorted.size / 2]

pings network/net.Client -> none:
  socket := network.udp-open
  rtts := []
  try:
    PINGS.repeat: | i |
      message := ByteArray 16: i
      start := Time.monotonic-us
      socket.send (udp.Datagram message target)
      timed-out := catch: with-timeout --ms=TIMEOUT-MS:
        while (socket.receive).data != message: null  // A late reply to an earlier ping.
      if timed-out:
        print "lost $i"
      else:
        rtt := (Time.monotonic-us - start) / 1_000
        rtts.add rtt
        print "echo $i rtt=$rtt"
      sleep --ms=(max 0 (1_000 - (Time.monotonic-us - start) / 1_000))
  finally:
    socket.close
  if rtts.is-empty: print "pings: 0/$PINGS echoed"
  else: print "pings: $rtts.size/$PINGS echoed, rtt min $(rtts.reduce: | a b | min a b) median $(median rtts) max $(rtts.reduce: | a b | max a b) ms"

stream network/net.Client -> none:
  socket := network.udp-open
  sent := {:}  // Sequence number -> send time (us).
  rtts := []
  try:
    reader := task::
      while true:
        reply := socket.receive
        seq := reply.data[0] << 8 | reply.data[1]
        if sent.contains seq:
          rtts.add (Time.monotonic-us - (sent.get seq)) / 1_000
          sent.remove seq
    start := Time.monotonic-us
    STREAM.repeat: | i |
      block := ByteArray BLOCK-BYTES
      block[0] = i >> 8
      block[1] = i & 0xff
      sent[i] = Time.monotonic-us
      socket.send (udp.Datagram block target)
      next := start + (i + 1) * BLOCK-MS * 1_000
      sleep --ms=(max 0 (next - Time.monotonic-us) / 1_000)
    sleep --ms=3_000
    reader.cancel
  finally:
    socket.close
  print "stream: sent $STREAM echoed $rtts.size, rtt median $(median rtts) ms, lost $sent.keys"

main:
  network/net.Client? := null
  while not network:
    error := catch: network = net.open
    if error: print "open failed: $error"
  try:
    pings network
    stream network
  finally:
    network.close
