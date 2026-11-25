/* ktau #6: is there a level of quality above the LPC phrases? One phrase three ways through I2S20 and the
 * MAX98357A, once per boot: the LPC blob (c/lpcsynth, 8 kHz doubled), then LC3 at 16 and at 32 kbit/s (16 kHz,
 * 10 ms frames, encoded on the host from the same TTS source at the same peak level). Prints what each costs. */
#include <lc3.h>
#include <string.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>

#include "lpc_synth.h"

#define RATE 16000
#define BLOCK_FRAMES (RATE / 50) /* 20 ms */
#define BLOCK_BYTES (BLOCK_FRAMES * 2 * sizeof(int16_t))
#define LC3_FRAME_US 10000
#define LC3_FRAME_SAMPLES (RATE / 100)
#define N_BLOCKS 6
#define QUIETER 3 /* right shift, as c/phrasecheck */

K_MEM_SLAB_DEFINE_STATIC(tx_slab, BLOCK_BYTES, N_BLOCKS, 4);

static const uint8_t lpc_blob[] = {
#include <i-cant-reach-the-server.lpc.inc>
};
static const uint8_t lc3_16k[] = {
#include <i-cant-reach-the-server-16k.lc3.inc>
};
static const uint8_t lc3_32k[] = {
#include <i-cant-reach-the-server-32k.lc3.inc>
};

static lpc_synth_t synth;
static lc3_decoder_mem_16k_t lc3_mem;
static lc3_decoder_t lc3_dec;
static const uint8_t *lc3_at, *lc3_end;
static int lc3_len; /* 0: the source is the LPC synth */
static int16_t last;
static uint32_t cycles, max_cycles;

/* One 20 ms block of mono at RATE. Returns the samples produced; 0 means finished. */
static size_t render(int16_t *mono) {
  size_t n = 0;
  uint32_t t0 = k_cycle_get_32();
  if (lc3_len) {
    for (int f = 0; f < 2 && lc3_at + lc3_len <= lc3_end; f++, lc3_at += lc3_len) {
      lc3_decode(lc3_dec, lc3_at, lc3_len, LC3_PCM_FORMAT_S16, mono + n, 1);
      n += LC3_FRAME_SAMPLES;
    }
  } else {
    static int16_t half[BLOCK_FRAMES / 2];
    size_t got = lpc_synth_render(&synth, half, BLOCK_FRAMES / 2);
    for (size_t i = 0; i < got; i++) {
      mono[n++] = (int16_t)((last + half[i]) / 2);
      mono[n++] = last = half[i];
    }
  }
  uint32_t dt = k_cycle_get_32() - t0;
  cycles += dt;
  if (dt > max_cycles) max_cycles = dt;
  return n;
}

static void play(const struct device *i2s, const char *name, const uint8_t *blob, size_t len, int frame_bytes) {
  lc3_len = frame_bytes;
  if (frame_bytes) {
    lc3_dec = lc3_setup_decoder(LC3_FRAME_US, RATE, 0, &lc3_mem);
    lc3_at = blob;
    lc3_end = blob + len;
  } else if (lpc_synth_init(&synth, blob, len)) {
    printk("lc3play: %s: bad blob\n", name);
    return;
  }
  cycles = max_cycles = 0;
  last = 0;
  int blocks = 0, started = 0, err = 0;
  uint32_t samples = 0;
  for (;;) {
    static int16_t mono[BLOCK_FRAMES];
    void *mem;
    if (k_mem_slab_alloc(&tx_slab, &mem, K_MSEC(1000))) {
      printk("lc3play: %s: no free block after %d\n", name, blocks);
      break;
    }
    size_t n = render(mono);
    samples += n;
    int16_t *s = mem;
    for (size_t i = 0; i < BLOCK_FRAMES; i++) s[2 * i] = s[2 * i + 1] = i < n ? mono[i] >> QUIETER : 0;
    if (i2s_write(i2s, mem, BLOCK_BYTES)) {
      k_mem_slab_free(&tx_slab, mem);
      printk("lc3play: %s: write failed after %d\n", name, blocks);
      break;
    }
    if (n == 0 && started) break; /* that was one block of silence after the phrase */
    if (++blocks == 2) {
      err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_START);
      started = 1;
      if (err) break;
    }
  }
  int drain = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
  k_msleep(900); /* the queue drains, then a pause before the next one */
  size_t unused = 0;
  k_thread_stack_space_get(k_current_get(), &unused);
  printk("lc3play: %s: %u bytes, %u ms, err %d, drain %d, cpu %u us a second, worst block %u us, stack %u\n", name,
         (unsigned)len, samples * 1000 / RATE, err, drain,
         samples ? (uint32_t)((uint64_t)k_cyc_to_us_floor32(cycles) * RATE / samples) : 0,
         k_cyc_to_us_floor32(max_cycles), (unsigned)(CONFIG_MAIN_STACK_SIZE - unused));
}

int main(void) {
  const struct device *i2s = DEVICE_DT_GET(DT_NODELABEL(i2s20));
  if (!device_is_ready(i2s)) {
    printk("lc3play: i2s20 not ready\n");
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
  printk("lc3play: configure %d, decoder mem %u\n", err, (unsigned)sizeof lc3_mem);
  if (err) return 0;
  play(i2s, "1 lpc", lpc_blob, sizeof lpc_blob, 0);
  play(i2s, "2 lc3 16 kbit/s", lc3_16k, sizeof lc3_16k, lc3_frame_bytes(LC3_FRAME_US, 16000));
  play(i2s, "3 lc3 32 kbit/s", lc3_32k, sizeof lc3_32k, lc3_frame_bytes(LC3_FRAME_US, 32000));
  printk("lc3play: done\n");
  return 0;
}
