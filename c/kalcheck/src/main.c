/* ktau #6: speak phrases from the CMU kal diphone table in flash through I2S20 and the MAX98357A, once per boot,
 * and measure what the synth costs. Table and phrases are made by tools/kal_diphones.py; the synth is c/kalsynth.
 *
 * I2S runs at twice the synth's rate, each sample interpolated once, as in c/relpcheck (docs/hookup.md). */
#include <string.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>

#include "kal_synth.h"

#define OUT_RATE (2 * LPC_RATE)
#define SYNTH_FRAMES (LPC_RATE / 50) /* 20 ms */
#define BLOCK_BYTES (2 * SYNTH_FRAMES * 2 * sizeof(int16_t))
#define N_BLOCKS 6
#define QUIETER 3 /* right shift: the table peaks near full scale, David's bench level is far below */

K_MEM_SLAB_DEFINE_STATIC(tx_slab, BLOCK_BYTES, N_BLOCKS, 4);

struct phrase {
  const char *name;
  const uint8_t *wire;
  size_t len;
};
#include <phrases.h>

static kal_synth_t synth;
static uint32_t render_cycles, rendered;
static int16_t last;

/* Fills one stereo block from the synth, zero-padded at the end of the phrase. Returns the samples rendered. */
static size_t fill(int16_t *s) {
  static int16_t mono[SYNTH_FRAMES];
  uint32_t t0 = k_cycle_get_32();
  size_t n = kal_synth_render(&synth, mono, SYNTH_FRAMES);
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

static void play(const struct device *i2s, const struct phrase *ph) {
  int err = kal_synth_init(&synth, kal_table, sizeof kal_table, ph->wire, ph->len);
  if (err) {
    printk("kalcheck: %s: bad table or phrase\n", ph->name);
    return;
  }
  render_cycles = rendered = 0;
  last = 0;
  int blocks = 0, started = 0;
  for (;;) {
    void *mem;
    if (k_mem_slab_alloc(&tx_slab, &mem, K_MSEC(1000))) {
      printk("kalcheck: %s: no free block after %d\n", ph->name, blocks);
      break;
    }
    size_t n = fill(mem);
    if (n == 0 && started) { /* one block of silence after the phrase, then stop */
      err = i2s_write(i2s, mem, BLOCK_BYTES);
      break;
    }
    if (i2s_write(i2s, mem, BLOCK_BYTES)) {
      k_mem_slab_free(&tx_slab, mem);
      printk("kalcheck: %s: write failed after %d\n", ph->name, blocks);
      break;
    }
    if (++blocks == 2) {
      err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_START);
      started = 1;
      if (err) break;
    }
  }
  int drain = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
  k_msleep(700); /* the queue drains, then a pause before the next phrase */
  uint32_t us = k_cyc_to_us_floor32(render_cycles);
  printk("kalcheck: %s: %u bytes, %d blocks, %u ms of speech, %u substituted, err %d, drain %d, synth %u us a "
         "second\n",
         ph->name, (unsigned)ph->len, blocks, rendered * 1000 / LPC_RATE, synth.missing, err, drain,
         rendered ? (uint32_t)((uint64_t)us * LPC_RATE / rendered) : 0);
}

int main(void) {
  const struct device *i2s = DEVICE_DT_GET(DT_NODELABEL(i2s20));
  if (!device_is_ready(i2s)) {
    printk("kalcheck: i2s20 not ready\n");
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
  printk("kalcheck: configure %d at %d Hz, table %u bytes\n", err, OUT_RATE, (unsigned)sizeof kal_table);
  if (err) return 0;
  for (size_t i = 0; i < ARRAY_SIZE(phrases); i++) play(i2s, &phrases[i]);
  printk("kalcheck: done\n");
  return 0;
}
