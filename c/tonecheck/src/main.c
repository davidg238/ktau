/* ktau #6, S2 bring-up: a quiet 440 Hz tone for at most 3 s through I2S20, printing the I2S events as it goes.
 * 2026-11-23: the stream stalled after its first buffer yet the amp sounded; this run reports what the
 * peripheral is doing rather than guessing. */
#include <math.h>
#include <hal/nrf_gpio.h>
#include <hal/nrf_i2s.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>

#define RATE 16000
#define BLOCK_FRAMES 320 /* 20 ms */
#define BLOCK_BYTES (BLOCK_FRAMES * 2 * sizeof(int16_t))
#define N_BLOCKS 4
#define AMPLITUDE 500   /* about -36 dBFS (David: half again) */
#define MAX_BLOCKS 150  /* 3 s, then stop whatever happens */

K_MEM_SLAB_DEFINE_STATIC(tx_slab, BLOCK_BYTES, N_BLOCKS, 4);

static void report(const char *what) {
  NRF_I2S_Type *r = NRF_I2S20;
  printk("tonecheck: %s: FRAMESTART %u TXPTRUPD %u STOPPED %u TXD.PTR %08x ENABLE %u\n", what,
         r->EVENTS_FRAMESTART, r->EVENTS_TXPTRUPD, r->EVENTS_STOPPED, r->TXD.PTR, r->ENABLE);
}

static void fill(int16_t *s, uint32_t *phase) {
  const uint32_t step = (uint32_t)((440.0 * 65536) / RATE);
  for (int i = 0; i < BLOCK_FRAMES; i++) {
    int16_t v = (int16_t)(AMPLITUDE * sinf(2.0f * 3.14159265f * (*phase & 0xFFFF) / 65536.0f));
    *phase += step;
    s[2 * i] = v;
    s[2 * i + 1] = v;
  }
}

static void silence(const struct device *i2s) {
  int err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_DROP);
  k_msleep(50);
  nrf_i2s_task_trigger(NRF_I2S20, NRF_I2S_TASK_STOP); /* belt and braces: the amp must go quiet */
  k_msleep(10);
  report("after stop");
  printk("tonecheck: drop %d, done\n", err);
}

int main(void) {
  const struct device *i2s = DEVICE_DT_GET(DT_NODELABEL(i2s20));
  if (!device_is_ready(i2s)) {
    printk("tonecheck: i2s20 not ready\n");
    return 0;
  }
  struct i2s_config cfg = {
      .word_size = 16,
      .channels = 2,
      .format = I2S_FMT_DATA_FORMAT_I2S,
      .options = I2S_OPT_BIT_CLK_MASTER | I2S_OPT_FRAME_CLK_MASTER,
      .frame_clk_freq = RATE,
      .mem_slab = &tx_slab,
      .block_size = BLOCK_BYTES,
      .timeout = 1000,
  };
  int err = i2s_configure(i2s, I2S_DIR_TX, &cfg);
  printk("tonecheck: configure %d\n", err);
  if (err) return 0;

#ifdef CONNECT_CLOCK_INPUTS
  /* Experiment: keep the clock pins' input buffers connected, as Zephyr does for SPIM SCK on the nRF54L. */
  NRF_P1->PIN_CNF[SCK_PIN] &= ~GPIO_PIN_CNF_INPUT_Msk; /* INPUT = Connect (0) */
  NRF_P1->PIN_CNF[LRCK_PIN] &= ~GPIO_PIN_CNF_INPUT_Msk;
  printk("tonecheck: clock inputs connected (P1.%d, P1.%d)\n", SCK_PIN, LRCK_PIN);
#endif
  uint32_t phase = 0;
  for (int b = 0; b < 2; b++) {
    void *mem;
    k_mem_slab_alloc(&tx_slab, &mem, K_NO_WAIT);
    fill(mem, &phase);
    i2s_write(i2s, mem, BLOCK_BYTES);
  }
  report("before start");
  err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_START);
  printk("tonecheck: start %d\n", err);
  for (int t = 0; t < 5; t++) {
    k_msleep(5);
    report("5 ms");
  }

  int64_t end = k_uptime_get() + 3000;
  uint32_t written = 2;
  while (k_uptime_get() < end && written < MAX_BLOCKS) {
    void *mem;
    if (k_mem_slab_alloc(&tx_slab, &mem, K_MSEC(100))) {
      report("no free block");
      continue;
    }
    fill(mem, &phase);
    if (i2s_write(i2s, mem, BLOCK_BYTES)) {
      k_mem_slab_free(&tx_slab, mem);
      report("write failed");
      break;
    }
    written++;
    if (written % 50 == 0) report("progress");
  }
  printk("tonecheck: wrote %u blocks (%u expected in 3 s)\n", written, 3000 / 20);
  silence(i2s);
  return 0;
}
