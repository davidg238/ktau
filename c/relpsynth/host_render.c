/* Host driver for the test: relp blob on stdin -> raw s16le samples on stdout, rendered in odd-sized chunks so
 * the state carried across relp_synth_render calls is exercised. The blob is copied to a heap block of exactly
 * its size, so the address sanitiser sees any read past its end.
 * Build: cc -O2 -fsanitize=address -I../lpcsynth -o host_render host_render.c relp_synth.c */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "relp_synth.h"

int main(void) {
  static uint8_t in[1 << 20];
  size_t len = fread(in, 1, sizeof in, stdin);
  uint8_t *blob = malloc(len ? len : 1);
  memcpy(blob, in, len);
  relp_synth_t s;
  if (relp_synth_init(&s, blob, len)) return 1;
  int16_t buf[97];
  size_t n;
  while ((n = relp_synth_render(&s, buf, sizeof buf / sizeof buf[0])) > 0) fwrite(buf, 2, n, stdout);
  free(blob);
  return 0;
}
