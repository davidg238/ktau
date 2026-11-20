// A Toit driver for the LSM6DS3TR-C's single-tap detection, over any serial.Device.
// Register values: ST AN5130 (LSM6DS3TR-C), single-tap example.
import serial

WHO-AM-I ::= 0x0F
WHO-AM-I-VALUE ::= 0x6A
CTRL1-XL ::= 0x10     // Accelerometer rate and scale.
CTRL3-C ::= 0x12      // Bit 0: SW_RESET.
TAP-SRC ::= 0x1C      // Which axis and sign the last tap had.
TAP-CFG ::= 0x58
TAP-THS-6D ::= 0x59
INT-DUR2 ::= 0x5A
WAKE-UP-THS ::= 0x5B
MD1-CFG ::= 0x5E      // What is routed to INT1.

SW-RESET ::= 0x01
ODR-416HZ-2G ::= 0x60
// INT1 pulses for a few ms per tap; LIR (bit 0) did not hold it high, so it is off.
TAP-XYZ ::= 0x8E            // INTERRUPTS_ENABLE, TAP_X/Y/Z_EN.
// TAP_THS 9 (AN5130's value) missed 4 of 9 sharp taps; 2 caught every tap,
// with 3-4 pulses each (ktau journal 03).
TAP-THRESHOLD ::= 0x82      // D4D_EN, TAP_THS = 2.
TAP-TIMING ::= 0x06         // QUIET = 1, SHOCK = 2.
SINGLE-TAP-ONLY ::= 0x00
INT1-SINGLE-TAP ::= 0x40

SINGLE-TAP ::= 0x20         // TAP_SRC bit 5.
SETTLE-MS ::= 50

class Lsm6ds3:
  registers_/serial.Registers

  constructor device/serial.Device:
    registers_ = device.registers
    id := registers_.read-u8 WHO-AM-I
    if id != WHO-AM-I-VALUE: throw "LSM6DS3: WHO_AM_I is 0x$(%02x id)"

  /**
  Resets the chip, then routes single taps on any axis to INT1 as a pulse.
  */
  enable-single-tap -> none:
    // The chip stays powered across a reflash, so clear whatever was set before.
    registers_.write-u8 CTRL3-C SW-RESET
    while (registers_.read-u8 CTRL3-C) & SW-RESET != 0: sleep --ms=1
    registers_.write-u8 CTRL1-XL ODR-416HZ-2G
    registers_.write-u8 TAP-CFG TAP-XYZ
    registers_.write-u8 TAP-THS-6D TAP-THRESHOLD
    registers_.write-u8 INT-DUR2 TAP-TIMING
    registers_.write-u8 WAKE-UP-THS SINGLE-TAP-ONLY
    // The accelerometer's start from 0 to 1 g reads as a tap: let it settle
    // before taps reach INT1.
    sleep --ms=SETTLE-MS
    registers_.write-u8 MD1-CFG INT1-SINGLE-TAP

  /** The tap source register: which axis, which sign; set only briefly after a tap. */
  tap-source -> int:
    return registers_.read-u8 TAP-SRC
