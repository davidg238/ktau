/* ktau rung 5, the C check: encode 1 s of a 440 Hz sine with liblc3 (16 kHz, 10 ms frames, 32 kbit/s),
 * print sizes, encode time per frame, stack use, and the frames in the format tools/lc3dec.py reads. */
#include <math.h>
#include <stdio.h>
#include <zephyr/kernel.h>
#include <zephyr/sys/base64.h>
#include <lc3.h>

#define RATE 16000
#define FRAME_US 10000
#define FRAME_SAMPLES 160
#define FRAMES 100
#define BITRATE 32000

static int16_t pcm[FRAME_SAMPLES * FRAMES];
static uint8_t out[FRAMES * 40];
static lc3_encoder_mem_16k_t mem;

int main(void)
{
	int frame_bytes = lc3_frame_bytes(FRAME_US, BITRATE);
	for (int i = 0; i < FRAME_SAMPLES * FRAMES; i++) {
		pcm[i] = (int16_t)(16383.0f * sinf(2.0f * 3.14159265f * 440.0f * i / RATE));
	}
	lc3_encoder_t enc = lc3_setup_encoder(FRAME_US, RATE, 0, &mem);
	uint32_t min = UINT32_MAX, max = 0, sum = 0;
	for (int f = 0; f < FRAMES; f++) {
		uint32_t t0 = k_cycle_get_32();
		int ret = lc3_encode(enc, LC3_PCM_FORMAT_S16, pcm + f * FRAME_SAMPLES, 1, frame_bytes,
				     out + f * frame_bytes);
		uint32_t us = k_cyc_to_us_floor32(k_cycle_get_32() - t0);
		if (ret) {
			printf("lc3_encode frame %d: %d\n", f, ret);
			return 0;
		}
		min = MIN(min, us); max = MAX(max, us); sum += us;
	}
	size_t unused = 0;
	k_thread_stack_space_get(k_current_get(), &unused);
	printf("lc3check: encoder-mem=%u frame-bytes=%d enc-us min=%u avg=%u max=%u stack-used=%u of %u\n",
	       (unsigned)sizeof(mem), frame_bytes, min, sum / FRAMES, max,
	       (unsigned)(CONFIG_MAIN_STACK_SIZE - unused), CONFIG_MAIN_STACK_SIZE);
	printf("LC3 BEGIN rate=%d frame-us=%d frame-bytes=%d frames=%d\n", RATE, FRAME_US, frame_bytes, FRAMES);
	for (int f = 0; f < FRAMES; f += 10) {
		char line[600];
		size_t olen;
		base64_encode(line, sizeof(line), &olen, out + f * frame_bytes, 10 * frame_bytes);
		printf("%s\n", line);
	}
	printf("LC3 END\n");
	return 0;
}
