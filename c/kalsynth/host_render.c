/* Host driver for the test: argv[1] a diphone table, argv[2] wire bytes -> raw s16le samples on stdout, rendered
 * in odd-sized chunks so the state carried across kal_synth_render calls is exercised. Each file is copied to a
 * heap block of exactly its size, so the address sanitiser sees any read past either end. Exit 1 if init rejects
 * them; prints the substituted-pair count on stderr.
 * Build: cc -O2 -fsanitize=address -I../relpsynth -I../lpcsynth -o host_render host_render.c kal_synth.c \
 *        ../relpsynth/relp_synth.c */
#include <stdio.h>
#include <stdlib.h>

#include "kal_synth.h"

static uint8_t *slurp(const char *path, size_t *len) {
  FILE *f = fopen(path, "rb");
  if (!f) exit(2);
  fseek(f, 0, SEEK_END);
  *len = (size_t)ftell(f);
  fseek(f, 0, SEEK_SET);
  uint8_t *p = malloc(*len ? *len : 1);
  if (fread(p, 1, *len, f) != *len) exit(2);
  fclose(f);
  return p;
}

int main(int argc, char **argv) {
  if (argc != 3) return 2;
  size_t tlen, wlen;
  uint8_t *table = slurp(argv[1], &tlen), *wire = slurp(argv[2], &wlen);
  static kal_synth_t s;
  if (kal_synth_init(&s, table, tlen, wire, wlen)) return 1;
  fprintf(stderr, "missing %u\n", s.missing);
  int16_t buf[97];
  size_t n;
  while ((n = kal_synth_render(&s, buf, sizeof buf / sizeof buf[0])) > 0) fwrite(buf, 2, n, stdout);
  free(table);
  free(wire);
  return 0;
}
