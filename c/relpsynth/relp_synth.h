/* Residual-excited LPC synth for the board (#6): plays a blob made by tools/relp_codec.py, 8 kHz 16-bit mono.
 *
 * Integer only. tools/relp_codec.py `synthesise` is its specification, and tools/test_relp_codec.py checks the
 * two match sample for sample. Render in any buffer size: the state carries across calls.
 */
#pragma once
#include <stddef.h>
#include <stdint.h>

#include "lpc_tables.h"
#include "relp_tables.h"

typedef struct {
  const uint8_t *frames;            /* packed frames, after the 4-byte header */
  uint16_t n_frames, scale;
  uint16_t frame, n;                /* current frame and sample within it */
  int16_t k[LPC_ORDER];             /* this frame's reflection coefficients, Q15 */
  int32_t level[RELP_N_LEVEL];      /* this frame's residual magnitudes, Q20 */
  int32_t b[LPC_ORDER + 1];         /* lattice state, Q20 */
} relp_synth_t;

/* Returns 0, or -1 if the blob is shorter than its header says. */
int relp_synth_init(relp_synth_t *s, const uint8_t *blob, size_t len);

/* Writes up to max samples; returns how many. 0 means the blob is finished. */
size_t relp_synth_render(relp_synth_t *s, int16_t *out, size_t max);

/* The steps of relp_synth_render, for synths that play frames out of order (c/kalsynth). */
/* A frame's reflection coefficients and residual magnitudes. */
void relp_frame_load(const uint8_t *frame, int16_t k[LPC_ORDER], int32_t level[RELP_N_LEVEL]);
/* Residual sample n (< RELP_HOP) of a frame, Q20. */
int32_t relp_residual(const uint8_t *frame, const int32_t level[RELP_N_LEVEL], unsigned n);
/* One sample through the lattice: excitation in, output out, state b updated. */
int32_t relp_lattice(int32_t f, const int16_t k[LPC_ORDER], int32_t b[LPC_ORDER + 1]);
/* Q20 signal to a 16-bit sample with the blob's output scale. */
int16_t relp_out(int32_t f, uint16_t scale);
