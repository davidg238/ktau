/* See kal_synth.h. Each step mirrors tools/kal_diphones.py `plan` and `render`; keep the two in step. */
#include "kal_synth.h"

#include <string.h>

static uint16_t u16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }

/* Diphone a-b, or -1: the first match, as kal_diphones.lookup. */
static int lookup(const kal_synth_t *s, uint8_t a, uint8_t b) {
  for (int i = 0; i < s->n_diphones; i++)
    if (s->index[i * KAL_INDEX_BYTES] == a && s->index[i * KAL_INDEX_BYTES + 1] == b) return i;
  return -1;
}

static int cursor_next(const kal_synth_t *s, kal_cursor_t *c) {
  int32_t ms;
  if (c->pend) {
    c->pend = 0;
    c->ph = s->pau;                           /* f0 stays that of the phone before */
    ms = KAL_PAUSE_MS;
  } else {
    if (++c->w >= s->n_wire) return c->live = 0;
    const uint8_t *p = s->wire + (size_t)c->w * KAL_WIRE_BYTES;
    c->ph = p[0];
    ms = u16(p + 1);
    c->f0 = p[3];
    c->pend = c->w + 1 < s->n_wire && lookup(s, c->ph, p[KAL_WIRE_BYTES]) < 0;
  }
  int32_t start = c->end;
  c->end += ms * LPC_RATE / 1000;
  c->mid = (start + c->end) / 2;
  return c->live = 1;
}

static void setup_half(kal_synth_t *s) {
  int d = lookup(s, s->a_ph, s->half.ph);
  const uint8_t *e = s->index + (d < 0 ? s->pau_pau : d) * KAL_INDEX_BYTES;
  s->hframes = s->frames + (size_t)u16(e + 2) * RELP_FRAME_BYTES;
  s->hper = s->periods + u16(e + 4);
  if (s->h == 0) {
    s->p0 = 0, s->np = e[6], s->t0 = s->start, s->t1 = s->a_end;
  } else {
    s->p0 = e[6], s->np = e[7], s->t0 = s->a_end, s->t1 = s->half.mid;
  }
  s->base = s->len = 0;
  for (int i = 0; i < s->p0; i++) s->base += s->hper[i];
  for (int i = 0; i < s->np; i++) s->len += s->hper[s->p0 + i];
}

static void advance_half(kal_synth_t *s) {
  if (s->h == 0) {
    s->h = 1;
  } else {
    s->start = s->half.mid;
    s->a_ph = s->half.ph;
    s->a_end = s->half.end;
    if (!cursor_next(s, &s->half)) {
      s->done = 1;
      return;
    }
    s->h = 0;
  }
  setup_half(s);
}

static int32_t f0_at(kal_synth_t *s, int32_t t) {
  if (t <= s->mid_first) return s->f0_first;
  while (s->f0c.live && t >= s->f0c.mid) {
    s->m0 = s->f0c.mid;
    s->fa = s->f0c.f0;
    cursor_next(s, &s->f0c);
  }
  if (!s->f0c.live) return s->fa;
  if (s->f0c.mid <= s->m0) return s->f0c.f0;
  return s->fa + (int32_t)((int64_t)(s->f0c.f0 - s->fa) * (t - s->m0) / (s->f0c.mid - s->m0));
}

static int next_period(kal_synth_t *s) {
  while (!s->done && (s->t >= s->t1 || s->np == 0)) advance_half(s);
  if (s->done) return 0;
  int32_t period = LPC_RATE / f0_at(s, s->t);
  int32_t u = s->base + (s->t > s->t0 ? (int32_t)((int64_t)(s->t - s->t0) * s->len / (s->t1 - s->t0)) : 0);
  int32_t st = s->base, k;
  for (k = 0; k < s->np; k++) {
    int32_t nx = st + s->hper[s->p0 + k];
    int32_t a = u - st, b = u - nx;
    if ((a < 0 ? -a : a) < (b < 0 ? -b : b)) break;
    st = nx;
  }
  if (k == s->np) {
    k = s->np - 1;
    st = s->base + s->len - s->hper[s->p0 + k];
  }
  int32_t slen = s->hper[s->p0 + k];
  s->dframes = s->hframes;
  if (slen < period) {
    s->lead = (uint16_t)((period - slen) / 2), s->src = st, s->n_src = (uint16_t)slen;
  } else {
    s->lead = 0, s->src = st + (slen - period) / 2, s->n_src = (uint16_t)period;
  }
  s->len_t = (uint16_t)period;
  s->j = 0;
  s->t += period;
  return 1;
}

int kal_synth_init(kal_synth_t *s, const uint8_t *table, size_t table_len, const uint8_t *wire, size_t wire_len) {
  memset(s, 0, sizeof *s);
  if (table_len < 5) return -1;
  s->n_diphones = u16(table);
  s->scale = u16(table + 2);
  s->n_phones = table[4];
  size_t p = 5;
  int pau = -1;
  for (int i = 0; i < s->n_phones; i++) {
    const uint8_t *z = memchr(table + p, 0, table_len - p);
    if (!z) return -1;
    if ((size_t)(z - table) == p + 3 && !memcmp(table + p, "pau", 3)) pau = i;
    p = (size_t)(z - table) + 1;
  }
  if (pau < 0 || table_len - p < (size_t)s->n_diphones * KAL_INDEX_BYTES) return -1;
  s->pau = (uint8_t)pau;
  s->index = table + p;
  p += (size_t)s->n_diphones * KAL_INDEX_BYTES;
  size_t n_periods = 0;
  for (int i = 0; i < s->n_diphones; i++) n_periods += s->index[i * KAL_INDEX_BYTES + 6] + s->index[i * KAL_INDEX_BYTES + 7];
  if (table_len - p < n_periods) return -1;
  s->periods = table + p;
  s->frames = table + p + n_periods;
  size_t frames_len = table_len - p - n_periods;
  for (int i = 0; i < s->n_diphones; i++) {
    const uint8_t *e = s->index + i * KAL_INDEX_BYTES;
    size_t q0 = u16(e + 4), n = e[6] + e[7], samples = 0;
    if (e[0] >= s->n_phones || e[1] >= s->n_phones || q0 + n > n_periods) return -1;
    for (size_t j = 0; j < n; j++) samples += s->periods[q0 + j];
    size_t nf = (samples + RELP_HOP - 1) / RELP_HOP;
    if ((u16(e + 2) + nf) * RELP_FRAME_BYTES > frames_len) return -1;
  }
  int pp = lookup(s, s->pau, s->pau);
  if (pp < 0) return -1;
  s->pau_pau = (uint16_t)pp;

  if (wire_len % KAL_WIRE_BYTES || wire_len / KAL_WIRE_BYTES > UINT16_MAX) return -1;
  s->wire = wire;
  s->n_wire = (uint16_t)(wire_len / KAL_WIRE_BYTES);
  for (int w = 0; w < s->n_wire; w++) {
    const uint8_t *q = wire + w * KAL_WIRE_BYTES;
    if (q[0] >= s->n_phones || q[3] == 0) return -1;
    if (w + 1 < s->n_wire && lookup(s, q[0], q[KAL_WIRE_BYTES]) < 0) s->missing++;
  }

  s->half.w = s->f0c.w = -1;
  if (!cursor_next(s, &s->f0c)) {
    s->done = 1;
    return 0;
  }
  s->mid_first = s->m0 = s->f0c.mid;
  s->f0_first = s->fa = s->f0c.f0;
  cursor_next(s, &s->f0c);
  cursor_next(s, &s->half);
  s->a_ph = s->half.ph;
  s->a_end = s->half.end;
  if (!cursor_next(s, &s->half)) {
    s->done = 1;
    return 0;
  }
  setup_half(s);
  return 0;
}

size_t kal_synth_render(kal_synth_t *s, int16_t *out, size_t max) {
  size_t done = 0;
  while (done < max) {
    if (s->j == s->len_t && !next_period(s)) break;
    int32_t f = 0;
    if (s->j >= s->lead && s->j < s->lead + s->n_src) {
      int32_t p = s->src + s->j - s->lead;
      const uint8_t *fr = s->dframes + (size_t)(p / RELP_HOP) * RELP_FRAME_BYTES;
      if (fr != s->cur) {
        s->cur = fr;
        relp_frame_load(fr, s->k, s->level);
      }
      f = relp_residual(fr, s->level, (unsigned)(p % RELP_HOP));
    }
    out[done++] = relp_out(relp_lattice(f, s->k, s->b), s->scale);
    s->j++;
  }
  return done;
}
