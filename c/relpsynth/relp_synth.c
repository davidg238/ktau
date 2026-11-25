/* See relp_synth.h. Each step mirrors tools/relp_codec.py `synthesise`; keep the two in step. */
#include "relp_synth.h"

#define SAT ((1 << 30) - 1)

static int32_t sat(int64_t x) { return x > SAT ? SAT : (x < -SAT ? -SAT : (int32_t)x); }

void relp_frame_load(const uint8_t *p, int16_t k[LPC_ORDER], int32_t level[RELP_N_LEVEL]) {
  uint64_t word = 0;
  for (int i = RELP_HEAD_BYTES - 1; i >= 0; i--) word = (word << 8) | p[i];
  int32_t gain = relp_gain_q20[word & ((1 << RELP_GAIN_BITS) - 1)];
  word >>= RELP_GAIN_BITS;
  for (int i = 0; i < LPC_ORDER; i++) {
    k[i] = lpc_k[i][word & ((1u << lpc_bits[i]) - 1)];
    word >>= lpc_bits[i];
  }
  for (int m = 0; m < RELP_N_LEVEL; m++) level[m] = (int32_t)(((int64_t)relp_level_q12[m] * gain) >> 12);
}

int32_t relp_residual(const uint8_t *frame, const int32_t level[RELP_N_LEVEL], unsigned n) {
  const uint8_t *codes = frame + RELP_HEAD_BYTES;
  unsigned bit = n * RELP_RES_BITS;
  unsigned c = codes[bit >> 3] >> (bit & 7);
  if ((bit & 7) + RELP_RES_BITS > 8) c |= codes[(bit >> 3) + 1] << (8 - (bit & 7));   /* never past the frame */
  c &= (1 << RELP_RES_BITS) - 1;
  int32_t f = level[c & (RELP_N_LEVEL - 1)];
  return c & RELP_N_LEVEL ? -f : f;
}

int32_t relp_lattice(int32_t f, const int16_t k[LPC_ORDER], int32_t b[LPC_ORDER + 1]) {
  for (int i = LPC_ORDER - 1; i >= 0; i--) {
    f = sat(f - (((int64_t)k[i] * b[i]) >> 15));
    b[i + 1] = sat(b[i] + (((int64_t)k[i] * f) >> 15));
  }
  b[0] = f;
  return f;
}

int16_t relp_out(int32_t f, uint16_t scale) {
  int64_t v = ((int64_t)f * scale) >> 16;
  return v > 32767 ? 32767 : (v < -32768 ? -32768 : (int16_t)v);
}

static void load_frame(relp_synth_t *s) {
  relp_frame_load(s->frames + (size_t)s->frame * RELP_FRAME_BYTES, s->k, s->level);
}

int relp_synth_init(relp_synth_t *s, const uint8_t *blob, size_t len) {
  if (len < 4) return -1;
  *s = (relp_synth_t){0};
  s->n_frames = blob[0] | blob[1] << 8;
  s->scale = blob[2] | blob[3] << 8;
  if (len < 4 + (size_t)s->n_frames * RELP_FRAME_BYTES) return -1;
  s->frames = blob + 4;
  if (s->n_frames) load_frame(s);
  return 0;
}

size_t relp_synth_render(relp_synth_t *s, int16_t *out, size_t max) {
  size_t done = 0;
  while (done < max && s->frame < s->n_frames) {
    int32_t f = relp_residual(s->frames + (size_t)s->frame * RELP_FRAME_BYTES, s->level, s->n);
    out[done++] = relp_out(relp_lattice(f, s->k, s->b), s->scale);
    if (++s->n == RELP_HOP) {
      s->n = 0;
      if (++s->frame < s->n_frames) load_frame(s);
    }
  }
  return done;
}
