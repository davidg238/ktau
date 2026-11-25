/* ktau #6: does I2S20 on the XIAO nRF54L15 advance buffers when driven by its registers alone?
 * Zephyr's driver stalled after the first buffer (2026-11-23): i2c22 owned P1.11, see boards/ and
 * docs/hookup.md. This polls the events directly, no interrupts, no I2S driver. Silent: the buffers are zeros. Each pin set runs for 1 s. */
#include <string.h>
#include <zephyr/kernel.h>
#include <nrfx.h>

#define FRAMES 320                         /* 20 ms at 16 kHz, 16-bit stereo: one 32-bit word a frame */
static uint32_t buf[2][FRAMES];
static uint32_t sink[FRAMES];             /* RXD.PTR target: RX is off, but see whether anything lands here */
#define MCKFREQ_512K 0x04105000u           /* 512 kHz: floor(f*2^20 / (32 MHz + f/2)) << 12 */
#define PSEL(pin) ((1u << 5) | (pin))      /* port 1, CONNECT = 0 */
#define PSEL_OFF 0xFFFFFFFFu

static void pin_out(int pin) {
  NRF_P1->PIN_CNF[pin] = (GPIO_PIN_CNF_DIR_Output << GPIO_PIN_CNF_DIR_Pos) |
                         (GPIO_PIN_CNF_INPUT_Connect << GPIO_PIN_CNF_INPUT_Pos);
  NRF_P1->OUTCLR = 1u << pin;
}

static void run(const char *name, int sck, int lrck, int sdout) {
  NRF_I2S_Type *r = NRF_I2S20;
  memset(buf, 0, sizeof buf);
  memset(sink, 0xA5, sizeof sink);
  pin_out(sck); pin_out(lrck); pin_out(sdout);

  r->ENABLE = 0;
  r->CONFIG.MODE = I2S_CONFIG_MODE_MODE_Master;
  r->CONFIG.RXEN = 0;
  r->CONFIG.TXEN = 1;
  r->CONFIG.MCKEN = 1;
  r->CONFIG.MCKFREQ = MCKFREQ_512K;
  r->CONFIG.RATIO = I2S_CONFIG_RATIO_RATIO_32X;
  r->CONFIG.SWIDTH = I2S_CONFIG_SWIDTH_SWIDTH_16Bit;
  r->CONFIG.ALIGN = I2S_CONFIG_ALIGN_ALIGN_Left;
  r->CONFIG.FORMAT = I2S_CONFIG_FORMAT_FORMAT_I2S;
  r->CONFIG.CHANNELS = I2S_CONFIG_CHANNELS_CHANNELS_Stereo;
  r->PSEL.MCK = PSEL_OFF;
  r->PSEL.SDIN = PSEL_OFF;
  r->PSEL.SCK = PSEL(sck);
  r->PSEL.LRCK = PSEL(lrck);
  r->PSEL.SDOUT = PSEL(sdout);
  r->RXD.PTR = (uint32_t)sink;           /* reset value pointed at 0x20000000, over printk's state */
  r->TXD.PTR = (uint32_t)buf[0];
  r->RXTXD.MAXCNT = sizeof buf[0];        /* bytes on the nRF54L (nrf_i2s_transfer_set) */
  r->EVENTS_TXPTRUPD = 0;
  r->EVENTS_FRAMESTART = 0;
  r->EVENTS_STOPPED = 0;
  r->ENABLE = 1;
  r->TASKS_START = 1;

  int updates = 0, frames = 0, next = 1;
  int64_t end = k_uptime_get() + 1000;
  while (k_uptime_get() < end) {
    if (r->EVENTS_TXPTRUPD) {
      r->EVENTS_TXPTRUPD = 0;
      r->TXD.PTR = (uint32_t)buf[next];
      next ^= 1;
      updates++;
    }
    if (r->EVENTS_FRAMESTART) {
      r->EVENTS_FRAMESTART = 0;
      frames++;
    }
  }
  r->TASKS_STOP = 1;
  k_msleep(5);
  printk("i2sbare: %s (SCK P1.%02d LRCK P1.%02d SDOUT P1.%02d): TXPTRUPD %d in 1 s (expect ~50), "
         "FRAMESTART %d (one per buffer), STOPPED %u\n",
         name, sck, lrck, sdout, updates, frames, r->EVENTS_STOPPED);
  printk("i2sbare: %s: BUSERRORADDRESS ch0 %08x ch1 %08x, TXD.PTR %08x, buf %p/%p\n", name,
         r->CHANNEL[0].BUSERRORADDRESS, r->CHANNEL[1].BUSERRORADDRESS, r->TXD.PTR, buf[0], buf[1]);
  r->ENABLE = 0;
  int touched = 0;
  for (int i = 0; i < FRAMES; i++) touched += sink[i] != 0xA5A5A5A5u;
  printk("i2sbare: %s: RX sink words written %d of %d\n", name, touched, FRAMES);
}

/* Drive each pin high then low and read the pad back: a pin something external holds will not follow. */
static void probe(int pin) {
  pin_out(pin);
  NRF_P1->OUTSET = 1u << pin;
  k_busy_wait(1000);
  int hi = (NRF_P1->IN >> pin) & 1;
  NRF_P1->OUTCLR = 1u << pin;
  k_busy_wait(1000);
  int lo = (NRF_P1->IN >> pin) & 1;
  printk("i2sbare: probe P1.%02d: driven high reads %d, driven low reads %d\n", pin, hi, lo);
}

int main(void) {
  k_msleep(500);
  static const int pins[] = {4, 5, 6, 7, 10, 11, 12};
  for (int i = 0; i < 7; i++) probe(pins[i]);
#ifdef CLOCKS_ON
  NRF_CLOCK->EVENTS_XOSTARTED = 0;
  NRF_CLOCK->TASKS_XOSTART = 1;
  while (!NRF_CLOCK->EVENTS_XOSTARTED) {}
  NRF_CLOCK->EVENTS_PLLSTARTED = 0;
  NRF_CLOCK->TASKS_PLLSTART = 1;
  while (!NRF_CLOCK->EVENTS_PLLSTARTED) {}
  printk("i2sbare: HFXO and PLL started and held\n");
#endif
  run("ours", 4, 11, 6);      /* D0, D5; data to D2, unwired */
  run("upstream", 11, 12, 6); /* Zephyr's i2s tests' clock pins */
  run("free", 6, 7, 10);      /* D2, D3, D4: nothing wired to any of them */
  run("free-sck", 6, 11, 10); /* only SCK moved off the amp */
  run("free-lrck", 4, 7, 10); /* only LRCK moved off the amp */
  printk("i2sbare: done\n");
  return 0;
}
