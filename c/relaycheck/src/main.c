/* ktau rung 6, the C check: rete's datagram seam over Bluetooth LE (udp_ble.c, built in
   place from the rete tree) pings udp-echo6 on gw85224-01 over the tailnet, through the
   Pixel relay. Proves radio, bonding, relay and route before any Toit code. */
#include <stdio.h>
#include <string.h>
#include <zephyr/kernel.h>
#include "udp_backend.h"
#include "pulse_backend.h"

#define ECHO_HOST "fd7a:115c:a1e0::bf01:d921"
#define ECHO_PORT 7777
#define PINGS 20

/* udp_ble.c rings rete's pulse mailbox on arrival; this check polls instead. */
void pulse_post_isr_value(int chan_id, oop immediate) { (void)chan_id; (void)immediate; }

int main(void) {
    udp_open();
    int sock = udp_socket_bind(0);
    printk("relaycheck: socket %d\n", sock);
    while (!net_link_up()) {
        printk("relay: waiting\n");
        k_sleep(K_SECONDS(5));
    }
    int echoed = 0;
    for (int n = 1; n <= PINGS; n++) {
        char out[32], in[64], host[64];
        int len = snprintf(out, sizeof out, "ping %d", n);
        int64_t t0 = k_uptime_get();
        if (udp_send(sock, ECHO_HOST, ECHO_PORT, (const uint8_t *)out, len) < 0)
            printk("send %d failed (errno %d)\n", n, errno);
        int got = -1, port = 0;
        while (k_uptime_get() - t0 < 1000) {
            got = udp_receive(sock, (uint8_t *)in, sizeof in - 1, host, sizeof host, &port);
            if (got >= 0) break;
            k_sleep(K_MSEC(2));
        }
        int64_t rtt = k_uptime_get() - t0;
        if (got == len && memcmp(in, out, len) == 0) {
            echoed++;
            printk("echo %d rtt=%lld from %s:%d\n", n, rtt, host, port);
        } else {
            printk("lost %d\n", n);
        }
        if (rtt < 1000) k_sleep(K_MSEC(1000 - rtt));
    }
    printk("relaycheck: %d/%d echoed\n", echoed, PINGS);
    return 0;
}
