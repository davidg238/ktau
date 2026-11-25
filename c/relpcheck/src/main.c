/* ktau #6: play residual-excited LPC clips from flash through I2S20 and the MAX98357A, once per boot, and
 * measure what the synth costs. The blobs are made by tools/relp_codec.py; the synth is c/relpsynth.
 *
 * I2S runs at twice the synth's rate, each sample interpolated once, as in c/relpcheck (docs/hookup.md). */
#include <string.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>

#include "relp_synth.h"

#define OUT_RATE (2 * LPC_RATE)
#define SYNTH_FRAMES (LPC_RATE / 50) /* 20 ms */
#define BLOCK_BYTES (2 * SYNTH_FRAMES * 2 * sizeof(int16_t))
#define N_BLOCKS 6
#define QUIETER 3 /* right shift: the clips peak near full scale, David's bench level is far below */

K_MEM_SLAB_DEFINE_STATIC(tx_slab, BLOCK_BYTES, N_BLOCKS, 4);

struct clip {
  const char *name;
  const uint8_t *blob;
  size_t len;
};
#include <clips.h>

static relp_synth_t synth;
static uint32_t render_cycles, rendered;
static int16_t last;

/* Fills one stereo block from the synth, zero-padded at the end of the clip. Returns the samples rendered. */
static size_t fill(int16_t *s) {
  static int16_t mono[SYNTH_FRAMES];
  uint32_t t0 = k_cycle_get_32();
  size_t n = relp_synth_render(&synth, mono, SYNTH_FRAMES);
  render_cycles += k_cycle_get_32() - t0;
  rendered += n;
  for (size_t i = 0; i < SYNTH_FRAMES; i++) {
    int16_t v = i < n ? mono[i] >> QUIETER : 0;
    int16_t mid = (int16_t)((last + v) / 2);
    last = v;
    s[4 * i] = s[4 * i + 1] = mid;
    s[4 * i + 2] = s[4 * i + 3] = v;
  }
  return n;
}

static void play(const struct device *i2s, const char *name, const uint8_t *blob, size_t len) {
  int err = relp_synth_init(&synth, blob, len);
  if (err) {
    printk("relpcheck: %s: bad blob\n", name);
    return;
  }
  render_cycles = rendered = 0;
  last = 0;
  int blocks = 0, started = 0;
  for (;;) {
    void *mem;
    if (k_mem_slab_alloc(&tx_slab, &mem, K_MSEC(1000))) {
      printk("relpcheck: %s: no free block after %d\n", name, blocks);
      break;
    }
    size_t n = fill(mem);
    if (n == 0 && started) { /* one block of silence after the clip, then stop */
      err = i2s_write(i2s, mem, BLOCK_BYTES);
      break;
    }
    if (i2s_write(i2s, mem, BLOCK_BYTES)) {
      k_mem_slab_free(&tx_slab, mem);
      printk("relpcheck: %s: write failed after %d\n", name, blocks);
      break;
    }
    if (++blocks == 2) {
      err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_START);
      started = 1;
      if (err) break;
    }
  }
  int drain = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
  k_msleep(700); /* the queue drains, then a pause before the next clip */
  uint32_t us = k_cyc_to_us_floor32(render_cycles);
  printk("relpcheck: %s: %u bytes, %d blocks, %u ms of speech, err %d, drain %d, synth %u us a second\n", name,
         (unsigned)len, blocks, rendered * 1000 / LPC_RATE, err, drain,
         rendered ? (uint32_t)((uint64_t)us * LPC_RATE / rendered) : 0);
}

int main(void) {
  const struct device *i2s = DEVICE_DT_GET(DT_NODELABEL(i2s20));
  if (!device_is_ready(i2s)) {
    printk("relpcheck: i2s20 not ready\n");
    return 0;
  }
  struct i2s_config cfg = {
      .word_size = 16,
      .channels = 2,
      .format = I2S_FMT_DATA_FORMAT_I2S,
      .options = I2S_OPT_BIT_CLK_CONTROLLER | I2S_OPT_FRAME_CLK_CONTROLLER,
      .frame_clk_freq = OUT_RATE,
      .mem_slab = &tx_slab,
      .block_size = BLOCK_BYTES,
      .timeout = 1000,
  };
  int err = i2s_configure(i2s, I2S_DIR_TX, &cfg);
  printk("relpcheck: configure %d at %d Hz\n", err, OUT_RATE);
  if (err) return 0;
  for (size_t i = 0; i < ARRAY_SIZE(clips); i++) play(i2s, clips[i].name, clips[i].blob, clips[i].len);
  printk("relpcheck: done\n");
  return 0;
}
