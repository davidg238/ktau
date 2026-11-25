/* ktau #6: play host-made clips from flash through I2S20 and the MAX98357A, once per boot, a second apart.
 * The clips are raw 16 kHz 16-bit mono (tools/relp_reference.py writes them); nothing is decoded here, so what
 * is heard is the host experiment on the real speaker. */
#include <string.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>

#define RATE 16000
#define BLOCK_FRAMES (RATE / 50) /* 20 ms */
#define BLOCK_BYTES (BLOCK_FRAMES * 2 * sizeof(int16_t))
#define N_BLOCKS 6
#define QUIETER 3 /* right shift, as c/phrasecheck */

K_MEM_SLAB_DEFINE_STATIC(tx_slab, BLOCK_BYTES, N_BLOCKS, 4);

struct clip {
  const char *name;
  const uint8_t *pcm;
  size_t len;
};
#include <clips.h> /* generated from clips/ by CMakeLists.txt */

static void play(const struct device *i2s, const char *name, const int16_t *pcm, size_t samples) {
  int blocks = 0, err = 0;
  size_t at = 0;
  for (;;) {
    void *mem;
    if (k_mem_slab_alloc(&tx_slab, &mem, K_MSEC(1000))) {
      printk("pcmplay: %s: no free block after %d\n", name, blocks);
      break;
    }
    int16_t *s = mem;
    size_t n = MIN(BLOCK_FRAMES, samples - at);
    for (size_t i = 0; i < BLOCK_FRAMES; i++) s[2 * i] = s[2 * i + 1] = i < n ? pcm[at + i] >> QUIETER : 0;
    at += n;
    if (i2s_write(i2s, mem, BLOCK_BYTES)) {
      k_mem_slab_free(&tx_slab, mem);
      printk("pcmplay: %s: write failed after %d\n", name, blocks);
      break;
    }
    if (n == 0) break; /* that was one block of silence after the clip */
    if (++blocks == 2) {
      err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_START);
      if (err) break;
    }
  }
  int drain = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
  k_msleep(1000); /* the queue drains, then a pause before the next clip */
  printk("pcmplay: %s: %u ms, %d blocks, err %d, drain %d\n", name, (unsigned)(samples * 1000 / RATE), blocks, err,
         drain);
}

int main(void) {
  const struct device *i2s = DEVICE_DT_GET(DT_NODELABEL(i2s20));
  if (!device_is_ready(i2s)) {
    printk("pcmplay: i2s20 not ready\n");
    return 0;
  }
  struct i2s_config cfg = {
      .word_size = 16,
      .channels = 2,
      .format = I2S_FMT_DATA_FORMAT_I2S,
      .options = I2S_OPT_BIT_CLK_CONTROLLER | I2S_OPT_FRAME_CLK_CONTROLLER,
      .frame_clk_freq = RATE,
      .mem_slab = &tx_slab,
      .block_size = BLOCK_BYTES,
      .timeout = 1000,
  };
  int err = i2s_configure(i2s, I2S_DIR_TX, &cfg);
  printk("pcmplay: configure %d\n", err);
  if (err) return 0;
  for (size_t i = 0; i < ARRAY_SIZE(clips); i++) {
    play(i2s, clips[i].name, (const int16_t *)clips[i].pcm, clips[i].len / 2);
  }
  printk("pcmplay: done\n");
  return 0;
}
