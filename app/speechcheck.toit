// ktau #6: the Toit firmware speaks. Says one phrase twice through zephyr.Speech (c/speech in the firmware:
// the kal diphone synth, I2S20, the MAX98357A), the second asked for while the first is still playing, then
// offers a phrase the synth must refuse.
import zephyr

// c/kalcheck's "kitchen lights" phrase as wire phones (4 bytes each: phone, ms as u16, f0), made by
//   tools/kal_diphones.py flite "<text>" <dir> c/kalcheck/clips/kal-relp.bin
PHRASE ::= #[
  28, 220, 0, 82, 6, 168, 0, 109, 32, 135, 0, 98, 12, 106, 0, 111,
  23, 52, 0, 98, 9, 35, 0, 92, 0, 106, 0, 94, 23, 61, 0, 84,
  10, 21, 0, 83, 5, 50, 0, 90, 20, 141, 0, 90, 17, 58, 0, 102,
  8, 147, 0, 91, 5, 36, 0, 97, 23, 53, 0, 87, 21, 55, 0, 83,
  6, 129, 0, 89, 32, 50, 0, 88, 30, 71, 0, 87, 28, 220, 0, 82,
  1, 77, 0, 88, 23, 41, 0, 83, 9, 30, 0, 80, 30, 135, 0, 85,
  13, 188, 0, 99, 36, 35, 0, 91, 9, 53, 0, 88, 38, 60, 0, 92,
  3, 73, 0, 105, 29, 66, 0, 94, 23, 57, 0, 92, 25, 138, 0, 105,
  32, 56, 0, 90, 5, 66, 0, 92, 7, 85, 0, 82, 4, 112, 0, 89,
  32, 55, 0, 80, 10, 26, 0, 78, 5, 60, 0, 83, 31, 156, 0, 80,
  0, 128, 0, 87, 27, 154, 0, 79, 17, 69, 0, 81, 24, 83, 0, 79,
  28, 220, 0, 79]

main:
  print "speechcheck: $PHRASE.size bytes, twice"
  start := Time.monotonic-us
  zephyr.Speech.say PHRASE
  zephyr.Speech.say PHRASE
  print "speechcheck: second phrase started after $((Time.monotonic-us - start) / 1000) ms"
  zephyr.Speech.wait
  print "speechcheck: quiet after $((Time.monotonic-us - start) / 1000) ms"
  refused := catch: zephyr.Speech.say #[0xff, 0, 100, 100]
  print "speechcheck: unknown phone -> $refused"
