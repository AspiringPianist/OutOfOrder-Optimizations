#include <stdint.h>

/* Load step: idle, then a dense integer kernel. di/dt stress. */
int main(void) {
    volatile uint64_t acc = 1;
    for (uint64_t i = 0; i < 8000; i++) {
        acc += i;
    }
    for (uint64_t i = 0; i < 40000; i++) {
        acc = acc * 1664525u + 1013904223u;
        acc ^= (acc << 13);
        acc ^= (acc >> 7);
        acc ^= (acc << 17);
        acc += i * i;
    }
    /* Keep acc live; tohost 0 is the sim PASS code. */
    if (acc == 0) return 1;
    return 0;
}
