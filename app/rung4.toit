// ktau rung 4: a tap records 1.5 seconds from the PDM microphone, then prints it
// on the console for tools/clip2wav.py to turn into a WAV on the host.
import encoding.base64
import zephyr
import .lsm6ds3

// 100 ms each: 1.5 s. Two seconds (64000 B) ran out of the 80 KB Toit heap (journal 04).
BLOCKS ::= 15
// +10 dB: speech at 10 cm peaks near 8000, so about 12 dB of headroom; more gain
// raises the noise as much as the speech (journal 04).
GAIN-DB ::= 10

main:
  print "ktau rung 4"
  imu := Lsm6ds3 ((zephyr.I2c "i2c30").device 0x6a)
  imu.enable-single-tap
  int1 := zephyr.Key "imu_int1"
  led := zephyr.Led "led0"
  mic := zephyr.Microphone "pdm20" --gain-db=GAIN-DB
  n := 0
  while true:
    int1.wait-for-press
    imu.tap-source  // Clears the latch.
    n++
    mic.start
    mic.read  // The first block after a start is the PDM filter settling (journal 04).
    led.on  // On for exactly the recording: speak while it is lit.
    // The console is slower than the audio, so the clip is kept, then printed.
    clip := List BLOCKS: mic.read
    mic.stop
    led.off
    print "CLIP BEGIN n=$n rate=$zephyr.Microphone.RATE"
    clip.do: print (base64.encode it)
    print "CLIP END"
    imu.tap-source  // Taps while recording or printing don't start another clip.
