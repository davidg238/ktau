// ktau rung 5: push to talk. Hold the user button and speak: the LED is lit while the
// recording runs, each 100 ms block is LC3-encoded as it is read, and on release (or
// after 5 s) the clip is printed for tools/lc3dec.py to decode on the host.
import encoding.base64
import zephyr

// 100 ms each: 5 s. At 32 kbit/s that is 20 KB of LC3, against the 48 KB of PCM
// that capped rung 4 at 1.5 s.
MAX-BLOCKS ::= 50
// +10 dB from rung 4 (journal 04); held at the mouth this may clip (journal 05).
GAIN-DB ::= 10

main:
  print "ktau rung 5"
  button := zephyr.Key "usr_btn"
  led := zephyr.Led "led0"
  mic := zephyr.Microphone "pdm20" --gain-db=GAIN-DB
  encoder := zephyr.Lc3Encoder
  n := 0
  while true:
    button.wait-for-press
    n++
    encoder = zephyr.Lc3Encoder  // A fresh encoder state for each clip.
    mic.start
    mic.read  // The first block after a start is the PDM filter settling (journal 04).
    led.on  // On for exactly the recording window.
    frames := []
    times := []
    while button.pressed and frames.size < MAX-BLOCKS:
      pcm := mic.read
      t0 := Time.monotonic-us
      frames.add (encoder.encode pcm)
      times.add Time.monotonic-us - t0
    mic.stop
    led.off
    total := frames.reduce --initial=0: | a b | a + b.size
    sum := times.reduce --initial=0: | a b | a + b
    print "clip $n: blocks=$frames.size bytes=$total encode-us min=$(times.reduce --initial=0: | a b | a == 0 ? b : min a b) avg=$(frames.size == 0 ? 0 : sum / frames.size) max=$(times.reduce --initial=0: | a b | max a b)"
    print "LC3 BEGIN rate=$zephyr.Lc3Encoder.RATE frame-us=$zephyr.Lc3Encoder.FRAME-US frame-bytes=$encoder.frame-bytes frames=$(total / encoder.frame-bytes)"
    frames.do: print (base64.encode it)
    print "LC3 END"
    button.wait-for-release
