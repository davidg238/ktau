// ktau rung 7: push to talk to the receiver on the tailnet. Hold the user button and speak:
// the LED is lit while recording, and each 100 ms block is LC3-encoded and sent as one
// datagram through the Pixel's BLE relay. On release, an END (3 times). The receiver
// (server/receiver.py) transcribes it, asks the LLM for an action, runs it and replies;
// the LED answers: 2 short blinks acted, 1 long not understood, 5 fast no reply.
//
// The wire (server/clips.py), big-endian:
//   audio: clip:u16 | seq:u16 | 400 B LC3    end: clip:u16 | 0xFFFF | blocks:u16
//   reply: clip:u16 | status:u8 (0 acted, 1 no speech, 2 failed)
import net
import net.udp
import zephyr

RECEIVER ::= "fd7a:115c:a1e0::8733:894a"  // msi on the tailnet.
PORT ::= 7700
MAX-BLOCKS ::= 50     // 5 s (rung 5).
GAIN-DB ::= 10        // Levels are evened out at the receiver (design, Decided).
END-SEQ ::= 0xffff
REPLY-MS ::= 30_000
ACTED ::= 0

target ::= net.SocketAddress (net.IpAddress.parse RECEIVER) PORT

header clip/int seq/int -> ByteArray:
  return #[clip >> 8, clip & 0xff, seq >> 8, seq & 0xff]

blink led/zephyr.Led times/int on-ms/int off-ms/int -> none:
  times.repeat:
    led.on
    sleep --ms=on-ms
    led.off
    sleep --ms=off-ms

// Waits for the reply to $clip; replies to earlier clips are dropped. Null on timeout.
reply socket/udp.Socket clip/int -> int?:
  catch: with-timeout --ms=REPLY-MS:
    while true:
      data := socket.receive.data
      if data.size == 3 and (data[0] << 8 | data[1]) == clip: return data[2]
  return null

main:
  print "ktau rung 7"
  button := zephyr.Key "usr_btn"
  led := zephyr.Led "led0"
  mic := zephyr.Microphone "pdm20" --gain-db=GAIN-DB
  network/net.Client? := null
  while not network:
    error := catch: network = net.open
    if error: print "open failed: $error"
  socket := network.udp-open
  // A random start, so a reboot doesn't reuse an id the receiver has just finished.
  clip := random 0x10000
  while true:
    button.wait-for-press
    clip = (clip + 1) & 0xffff
    encoder := zephyr.Lc3Encoder  // A fresh encoder state for each clip.
    mic.start
    mic.read  // The first block after a start is the PDM filter settling (journal 04).
    led.on
    blocks := 0
    while button.pressed and blocks < MAX-BLOCKS:
      lc3 := encoder.encode mic.read
      socket.send (udp.Datagram (header clip blocks) + lc3 target)
      blocks++
    mic.stop
    led.off
    released := Time.monotonic-us
    end := (header clip END-SEQ) + #[blocks >> 8, blocks & 0xff]
    3.repeat:
      socket.send (udp.Datagram end target)
      sleep --ms=50
    status := reply socket clip
    ms := (Time.monotonic-us - released) / 1_000
    print "clip $clip: $blocks sent, reply $(status == null ? "none" : status) in $ms ms"
    if status == null: blink led 5 80 80
    else if status == ACTED: blink led 2 150 150
    else: blink led 1 600 0
    button.wait-for-release
