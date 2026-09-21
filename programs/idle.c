#include <stdint.h>

/* Idle: long low-activity stretch, then a short burst. PDN baseline. */
int main(void) {
    volatile uint64_t x = 1;
    for (uint64_t i = 0; i < 20000; i++) {
        x ^= i;
    }
    return (int)(x & 0xff);
}
