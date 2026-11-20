// ktau rung 3: Toit sets up the IMU's tap detection over I2C, then a task
// sleeps until a tap raises INT1 (devicetree imu_int1) and wakes it.
import zephyr
import .lsm6ds3

// One physical tap gives several tap events (landing, lift, ringing) over up to
// about a second; everything in this window after a wake is the same tap.
ONE-TAP-MS ::= 1000

main:
  print "ktau rung 3"
  imu := Lsm6ds3 ((zephyr.I2c "i2c30").device 0x6a)
  imu.enable-single-tap
  int1 := zephyr.Key "imu_int1"
  led := zephyr.Led "led0"
  n := 0
  while true:
    int1.wait-for-press
    src := imu.tap-source
    n++
    print "tap $n src=0x$(%02x src)"
    led.on
    sleep --ms=100
    led.off
    sleep --ms=ONE-TAP-MS - 100
