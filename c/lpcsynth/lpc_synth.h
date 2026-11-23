/* LPC speech synth for the board (#6): plays a phrase blob made by tools/lpc_codec.py, 8 kHz 16-bit mono.
 *
 * Integer only. tools/lpc_codec.py `synthesise` is its specification, and tools/test_lpc_codec.py checks the two
 * match sample for sample. Render in any buffer size: the state carries across calls.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "lpc_tables.h"

typedef struct {
  const uint8_t *frames;        /* packed frames, after the 4-byte header */
  uint16_t n_frames, scale;
  uint16_t frame, n;            /* current frame and sample within it */
  uint8_t prev[2 + LPC_ORDER];  /* unpacked indices: gain, pitch, k1..k10 */
  uint8_t cur[2 + LPC_ORDER];
  int32_t b[LPC_ORDER + 1];     /* lattice state, Q20 */
  int32_t y;                    /* de-emphasis state, Q20 */
  uint32_t rng;
  uint16_t pos, period;         /* pitch pulse position and period, samples */
} lpc_synth_t;

/* Returns 0, or -1 if the blob is shorter than its header says. */
int lpc_synth_init(lpc_synth_t *s, const uint8_t *blob, size_t len);

/* Writes up to max samples; returns how many. 0 means the phrase is finished. */
size_t lpc_synth_render(lpc_synth_t *s, int16_t *out, size_t max);
