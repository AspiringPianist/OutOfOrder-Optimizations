#include <stdint.h>

/* Branch-heavy: stresses frontend / BTB / mispredict power. */
int main(void) {
    volatile uint64_t s = 0;
    uint64_t x = 0x9e3779b97f4a7c15ULL;
    for (uint64_t i = 0; i < 50000; i++) {
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        if (x & 1ULL) {
            s += x;
        } else if (x & 2ULL) {
            s ^= x;
        } else {
            s -= x;
        }
        if ((x & 0xff) == 0) {
            s += i;
        }
    }
    return (int)(s & 0xff);
}
