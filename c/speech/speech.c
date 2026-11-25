/* ktau #6: the board's voice inside the Toit firmware. The Toit fork's speech primitives (zephyr.Speech) call
 * ztoit_speech_say with a wire phrase (tools/kal_diphones.py's format); a thread renders it with c/kalsynth from
 * the diphone table in flash and plays it through I2S20 and the MAX98357A. The playing is c/kalcheck's, which is
 * the reference: I2S at twice the synth's rate, each sample interpolated once (docs/hookup.md). */
#include <errno.h>
#include <string.h>
#include <zephyr/drivers/i2s.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/atomic.h>

#include "kal_synth.h"

#define OUT_RATE (2 * LPC_RATE)
#define BLOCK_MS 20
#define SYNTH_FRAMES (LPC_RATE * BLOCK_MS / 1000)
#define BLOCK_BYTES (2 * SYNTH_FRAMES * 2 * sizeof(int16_t))
#define N_BLOCKS 6
#define QUIETER 3       /* right shift: the table peaks near full scale, David's bench level is far below */
#define MAX_PHONES 256  /* the phrase is copied, since Toit's bytes may move: 20 s of speech and more */
/* Above the Toit VM's threads (K_LOWEST_APPLICATION_THREAD_PRIO), so a busy program cannot starve the amp. */
#define PRIORITY 5

K_MEM_SLAB_DEFINE_STATIC(tx_slab, BLOCK_BYTES, N_BLOCKS, 4);
static K_SEM_DEFINE(go, 0, 1);

static const uint8_t kal_table[] = {
#include <kal_table.inc>
};

static const struct device *const i2s = DEVICE_DT_GET(DT_NODELABEL(i2s20));
static atomic_t busy;
static bool configured;
static uint8_t phrase[MAX_PHONES * KAL_WIRE_BYTES];
static size_t phrase_len;
static kal_synth_t synth;
static int16_t last;

/* Fills one stereo block from the synth, zero-padded at the end of the phrase. Returns the samples rendered. */
static size_t fill(int16_t *s) {
  static int16_t mono[SYNTH_FRAMES];
  size_t n = kal_synth_render(&synth, mono, SYNTH_FRAMES);
  for (size_t i = 0; i < SYNTH_FRAMES; i++) {
    int16_t v = i < n ? mono[i] >> QUIETER : 0;
    int16_t mid = (int16_t)((last + v) / 2);
    last = v;
    s[4 * i] = s[4 * i + 1] = mid;
    s[4 * i + 2] = s[4 * i + 3] = v;
  }
  return n;
}

static void play(void) {
  size_t rendered = 0;
  int blocks = 0, err;
  last = 0;
  for (;;) {
    void *mem;
    err = k_mem_slab_alloc(&tx_slab, &mem, K_MSEC(1000));
    if (err) break;
    size_t n = fill(mem);
    rendered += n;
    err = i2s_write(i2s, mem, BLOCK_BYTES);
    if (err) {
      k_mem_slab_free(&tx_slab, mem);
      break;
    }
    if (++blocks == 2) { /* two blocks queued before the clock starts, as the driver wants */
      err = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_START);
      if (err) break;
    }
    if (n == 0 && blocks >= 2) break; /* a block of silence ends the phrase */
  }
  int drain = i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_DRAIN);
  k_msleep((N_BLOCKS + 2) * BLOCK_MS); /* what is queued plays out, and the driver is ready again */
  if (err || drain) i2s_trigger(i2s, I2S_DIR_TX, I2S_TRIGGER_PREPARE); /* out of the driver's error state */
  printk("speech: %u bytes, %d blocks, %u ms, %u substituted, err %d, drain %d\n", (unsigned)phrase_len, blocks,
         (unsigned)(rendered * 1000 / LPC_RATE), synth.missing, err, drain);
}

static void speech_thread(void *a, void *b, void *c) {
  for (;;) {
    k_sem_take(&go, K_FOREVER);
    play();
    atomic_clear(&busy);
  }
}
K_THREAD_DEFINE(speech_tid, 2048, speech_thread, NULL, NULL, NULL, PRIORITY, 0, 0);

static int configure(void) {
  if (!device_is_ready(i2s)) return -ENODEV;
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
  return i2s_configure(i2s, I2S_DIR_TX, &cfg);
}

int ztoit_speech_busy(void) { return atomic_get(&busy) != 0; }

int ztoit_speech_say(const uint8_t *wire, size_t len) {
  if (len == 0 || len > sizeof phrase) return -EINVAL;
  if (!atomic_cas(&busy, 0, 1)) return -EBUSY;
  int err = configured ? 0 : configure();
  if (!err) {
    configured = true;
    memcpy(phrase, wire, len);
    phrase_len = len;
    if (kal_synth_init(&synth, kal_table, sizeof kal_table, phrase, len)) err = -EINVAL;
  }
  if (err) {
    atomic_clear(&busy);
    return err;
  }
  k_sem_give(&go);
  return 0;
}
