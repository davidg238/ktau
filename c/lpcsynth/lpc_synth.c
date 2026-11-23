/* See lpc_synth.h. Each step mirrors tools/lpc_codec.py `synthesise`; keep the two in step. */
#include "lpc_synth.h"

#define SAT ((1 << 30) - 1)

static int32_t sat(int64_t x) { return x > SAT ? SAT : (x < -SAT ? -SAT : (int32_t)x); }

static void unpack(const uint8_t *p, uint8_t *f) {
  uint64_t word = 0;
  for (int i = LPC_FRAME_BYTES - 1; i >= 0; i--) word = (word << 8) | p[i];
  f[0] = word & ((1 << LPC_GAIN_BITS) - 1);
  word >>= LPC_GAIN_BITS;
  f[1] = word & ((1 << LPC_PITCH_BITS) - 1);
  word >>= LPC_PITCH_BITS;
  for (int i = 0; i < LPC_ORDER; i++) {
    f[2 + i] = word & ((1u << lpc_bits[i]) - 1);
    word >>= lpc_bits[i];
  }
}

int lpc_synth_init(lpc_synth_t *s, const uint8_t *blob, size_t len) {
  if (len < 4) return -1;
  *s = (lpc_synth_t){0};
  s->n_frames = blob[0] | blob[1] << 8;
  s->scale = blob[2] | blob[3] << 8;
  if (len < 4 + (size_t)s->n_frames * LPC_FRAME_BYTES) return -1;
  s->frames = blob + 4;
  s->rng = 0x12345678;
  if (s->n_frames) {
    unpack(s->frames, s->cur);
    for (int i = 0; i < 2 + LPC_ORDER; i++) s->prev[i] = s->cur[i];
  }
  return 0;
}

size_t lpc_synth_render(lpc_synth_t *s, int16_t *out, size_t max) {
  size_t done = 0;
  while (done < max && s->frame < s->n_frames) {
    const int n = s->n;
    const uint8_t *pf = s->prev, *cf = s->cur;
    int32_t k[LPC_ORDER];
    for (int i = 0; i < LPC_ORDER; i++) {
      int32_t kp = lpc_k[i][pf[2 + i]], kc = lpc_k[i][cf[2 + i]];
      k[i] = kp + (kc - kp) * n / LPC_HOP;
    }
    int32_t gp = lpc_gain_q20[pf[0]], gc = lpc_gain_q20[cf[0]];
    int32_t g = gp + (gc - gp) * n / LPC_HOP;
    int32_t pp = lpc_period[pf[1]], pc = lpc_period[cf[1]];

    s->rng ^= s->rng << 13;
    s->rng ^= s->rng >> 17;
    s->rng ^= s->rng << 5;
    int32_t r16 = (int16_t)(s->rng >> 16);
    int32_t noise = (int32_t)(((int64_t)r16 * g * 56756) >> 30);   /* unit variance: sqrt(3) * 32768 */
    int32_t e;
    if (pc) {
      if (s->pos >= s->period) {
        s->period = pp ? pp + (pc - pp) * n / LPC_HOP : pc;
        s->pos = 0;
      }
      e = (s->pos == 0 ? (g * lpc_pulse_q8[s->period]) >> 8 : 0) + ((noise * 3277) >> 16);   /* + 0.05 noise */
      s->pos++;
    } else {
      e = noise;
      s->pos = s->period;   /* the next voiced sample starts a pulse */
    }

    int32_t f = e;
    for (int i = LPC_ORDER - 1; i >= 0; i--) {
      f = sat(f - (((int64_t)k[i] * s->b[i]) >> 15));
      s->b[i + 1] = sat(s->b[i] + (((int64_t)k[i] * f) >> 15));
    }
    s->b[0] = f;
    s->y = sat(f + (((int64_t)LPC_DEEMPH_Q15 * s->y) >> 15));
    int64_t v = ((int64_t)s->y * s->scale) >> 16;
    out[done++] = v > 32767 ? 32767 : (v < -32768 ? -32768 : (int16_t)v);

    if (++s->n == LPC_HOP) {
      s->n = 0;
      if (++s->frame < s->n_frames) {
        for (int i = 0; i < 2 + LPC_ORDER; i++) s->prev[i] = s->cur[i];
        unpack(s->frames + s->frame * LPC_FRAME_BYTES, s->cur);
      }
    }
  }
  return done;
}
