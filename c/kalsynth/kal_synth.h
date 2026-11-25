/* Diphone synth for the board (#6): plays phones (the wire format) from a diphone table made by
 * tools/kal_diphones.py, 8 kHz 16-bit mono, through the residual-excited LPC steps of c/relpsynth.
 *
 * Integer only. tools/kal_diphones.py `plan` + `render` are its specification, and tools/test_kal_diphones.py
 * checks the two match sample for sample. The table and the wire bytes are read in place (the table can live in
 * flash); nothing is copied. Render in any buffer size: the state carries across calls.
 *
 * Where the model keeps lists (the phones with pauses filled in, their ends and midpoints, the half-units), this
 * keeps cursors: utterance time only moves forward, so each list is read once, in order.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "relp_synth.h"

#define KAL_WIRE_BYTES 4   /* u8 phone, u16 ms, u8 f0 Hz: kal_diphones.WIRE_BYTES */
#define KAL_INDEX_BYTES 8  /* kal_diphones.INDEX_BYTES */
#define KAL_PAUSE_MS 20    /* kal_diphones.PAUSE_MS */

/* A cursor over the phones as played: the wire, with a pause after each phone whose pair is missing. */
typedef struct {
  int32_t w;               /* wire phone last read */
  int32_t end, mid;        /* the current phone's end and midpoint, in samples */
  uint8_t ph, f0, pend, live;
} kal_cursor_t;

typedef struct {
  const uint8_t *index, *periods, *frames, *wire;
  uint16_t n_diphones, scale, n_wire, pau_pau, missing;
  uint8_t n_phones, pau;

  /* half-units: the pair (a, next phone of `half`) */
  kal_cursor_t half;
  uint8_t a_ph, h, done;
  int32_t a_end, start;
  uint16_t p0, np;         /* first period and period count of the current half, in its diphone */
  const uint8_t *hper, *hframes;  /* the half's diphone: its periods and first frame */
  int32_t t0, t1, base, len;  /* its target span; its source start and length, in samples */

  /* f0: the phone before `f0c` (mid m0, f0 fa) and the first phone's midpoint and f0 */
  kal_cursor_t f0c;
  int32_t m0, mid_first;
  uint8_t fa, f0_first;

  /* the current target period */
  int32_t t;               /* its start */
  const uint8_t *dframes;  /* its diphone's first frame */
  int32_t src;             /* first source sample played */
  uint16_t lead, n_src, len_t, j;

  const uint8_t *cur;      /* frame whose k and level are loaded */
  int16_t k[LPC_ORDER];
  int32_t level[RELP_N_LEVEL];
  int32_t b[LPC_ORDER + 1];
} kal_synth_t;

/* Returns 0, or -1 if the table is short or malformed (no pau-pau), or the wire is not whole phones, names a
 * phone the table lacks, or has an f0 of 0. s->missing is then the number of pairs played with a pause. */
int kal_synth_init(kal_synth_t *s, const uint8_t *table, size_t table_len, const uint8_t *wire, size_t wire_len);

/* Writes up to max samples; returns how many. 0 means the phrase is finished. */
size_t kal_synth_render(kal_synth_t *s, int16_t *out, size_t max);
