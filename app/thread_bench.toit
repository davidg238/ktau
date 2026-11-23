// ktau Thread bench: UDP throughput and loss between this node and tools/thread_bench_server.py
// on the border router. The node asks the peer for a plan, runs it (uplink, downlink or both at
// once), reports its counts and asks for the next: the matrix lives in the peer, not in flash.
// The wire is described in tools/thread_bench_server.py.
import net
import net.udp

PEER ::= "fdc5:9109:9afe:97ea:9541:d963:f8d9:8567"  // The border router's mesh-local EID.
PORT ::= 7790
RETRY-MS ::= 500
RETRIES ::= 20

target ::= net.SocketAddress (net.IpAddress.parse PEER) PORT

// What the receive task has seen. Reset by $run.
plan/List? := null
run-id := 0
acked := false
finished := false
report/string? := null
received := 0
late := 0
highest := -1
first-us := 0
last-us := 0
max-gap-us := 0

receive-loop socket/udp.Socket -> none:
  while true:
    data := socket.receive.data
    if data.size < 2: continue
    type := data[0]
    if type == 'P':
      plan = data[1..].to-string.split " "
    else if data[1] != run-id:
      continue
    else if type == 'A':
      acked = true
    else if type == 'F':
      finished = true
    else if type == 'R':
      report = data[2..].to-string
    else if type == 'D' and data.size >= 4:
      now := Time.monotonic-us
      seq := data[2] << 8 | data[3]
      if seq < highest: late++
      else: highest = seq
      if received == 0: first-us = now
      else if now - last-us > max-gap-us: max-gap-us = now - last-us
      last-us = now
      received++

send socket/udp.Socket bytes/ByteArray -> none:
  catch: socket.send (udp.Datagram bytes target)

// Sends $bytes every RETRY-MS until $done is true. False if it never is.
send-until socket/udp.Socket bytes/ByteArray [done] -> bool:
  RETRIES.repeat:
    send socket bytes
    (RETRY-MS / 20).repeat:
      if done.call: return true
      sleep --ms=20
  return false

run socket/udp.Socket id/int size/int up/int up-ms/num down/int down-ms/num -> none:
  run-id = id
  acked = false
  finished = false
  report = null
  received = 0
  late = 0
  highest = -1
  max-gap-us = 0
  if not (send-until socket #['G', id]: acked):
    print "run $id: no ack"
    return
  start := Time.monotonic-us
  send-errors := 0
  packet := ByteArray size
  packet[0] = 'D'
  packet[1] = id
  up.repeat: | seq |
    packet[2] = seq >> 8
    packet[3] = seq & 0xff
    wait-us := start + (seq * up-ms * 1000).to-int - Time.monotonic-us
    if wait-us >= 1000: sleep --ms=wait-us / 1000
    else: yield
    error := catch: socket.send (udp.Datagram packet target)
    if error: send-errors++
  sent-ms := (Time.monotonic-us - start) / 1000
  if down > 0:
    deadline := start + ((down * down-ms).to-int + 5_000) * 1000
    while not finished and Time.monotonic-us < deadline: sleep --ms=50
  span-ms := received > 1 ? (last-us - first-us) / 1000 : 0
  summary := "sent_ms=$sent-ms send_err=$send-errors down_rx=$received late=$late span_ms=$span-ms max_gap_ms=$(max-gap-us / 1000)"
  print "run $id: size $size, up $up @ $up-ms ms, down $down @ $down-ms ms: $summary"
  send-until socket (#['E', id] + summary.to-byte-array): report != null
  print "run $id: peer $report"

main:
  print "ktau thread bench"
  network/net.Client? := null
  while not network:
    error := catch: network = net.open
    if error:
      print "open failed: $error"
      sleep --ms=2_000
  print "address $network.address"
  socket := network.udp-open
  task:: receive-loop socket
  while true:
    plan = null
    run-id = 0
    while not plan:
      send socket #['H']
      sleep --ms=1_000
    fields := plan
    id := int.parse fields[0]
    if id == 0:
      sleep --ms=5_000
      continue
    size := int.parse fields[1]
    up := int.parse fields[2]
    up-ms := float.parse fields[3]
    down := int.parse fields[4]
    down-ms := float.parse fields[5]
    run socket id size up up-ms down down-ms
