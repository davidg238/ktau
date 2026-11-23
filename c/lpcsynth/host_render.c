/* Host driver for the test: lpc blob on stdin -> raw s16le samples on stdout, rendered in odd-sized chunks so
 * the state carried across lpc_synth_render calls is exercised. Build: cc -O2 -o host_render host_render.c lpc_synth.c */
#include <stdio.h>

#include "lpc_synth.h"

int main(void) {
  static uint8_t blob[1 << 20];
  size_t len = fread(blob, 1, sizeof blob, stdin);
  lpc_synth_t s;
  if (lpc_synth_init(&s, blob, len)) return 1;
  int16_t buf[97];
  size_t n;
  while ((n = lpc_synth_render(&s, buf, sizeof buf / sizeof buf[0])) > 0) fwrite(buf, 2, n, stdout);
  return 0;
}
