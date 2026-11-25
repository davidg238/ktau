// Soak for the radio-driver panic seen under rung 8 (ktau #7): rung 8's clip, sent on a timer
// instead of a button press, so the crash rate can be measured with nobody at the bench.
// Each clip is CLIP-BLOCKS of whatever the microphone hears; the wire is rung 8's (app/rung8.toit).
import net
import net.udp
import zephyr

RECEIVER ::= "fd3f:2e87:5f7:5554:428d:5cff:fe50:2680"
PORT ::= 7700
CLIP-BLOCKS ::= 23
GAP-MS ::= 3_000
GAIN-DB ::= 10
END-SEQ ::= 0xffff
REPLY-MS ::= 10_000

target ::= net.SocketAddress (net.IpAddress.parse RECEIVER) PORT

header clip/int seq/int -> ByteArray:
  return #[clip >> 8, clip & 0xff, seq >> 8, seq & 0xff]

reply socket/udp.Socket clip/int -> ByteArray?:
  catch: with-timeout --ms=REPLY-MS:
    while true:
      data := socket.receive.data
      if data.size >= 3 and (data[0] << 8 | data[1]) == clip: return data[2..]
  return null

main:
  print "ktau soak to $RECEIVER"
  led := zephyr.Led "led0"
  mic := zephyr.Microphone "pdm20" --gain-db=GAIN-DB
  network/net.Client? := null
  while not network:
    error := catch: network = net.open
    if error: print "open failed: $error"
  socket := network.udp-open
  clip := random 0x10000
  count := 0
  while true:
    clip = (clip + 1) & 0xffff
    count++
    encoder := zephyr.Lc3Encoder
    mic.start
    mic.read
    led.on
    CLIP-BLOCKS.repeat:
      lc3 := encoder.encode mic.read
      socket.send (udp.Datagram (header clip it) + lc3 target)
    mic.stop
    led.off
    released := Time.monotonic-us
    end := (header clip END-SEQ) + #[CLIP-BLOCKS >> 8, CLIP-BLOCKS & 0xff]
    3.repeat:
      socket.send (udp.Datagram end target)
      sleep --ms=50
    answer := reply socket clip
    ms := (Time.monotonic-us - released) / 1_000
    status := answer ? answer[0] : null
    phones := answer ? answer[1..] : #[]
    print "soak $count: clip $clip, reply $(status == null ? "none" : status) in $ms ms, $phones.size B to speak"
    if phones.size > 0: catch: zephyr.Speech.say phones
    zephyr.Speech.wait
    sleep --ms=GAP-MS
