#include <stdio.h>

/*
 * HTIF INT-mix: ALU + MUL + occasional DIV so the 2-wide INT IQ
 * actually sees HIGH and LOW ready together. Compile with htif_nano.specs.
 * Keep the loop short — full VCD is already ~200 MB at hello length.
 */
int main(void) {
    volatile unsigned long a = 3, b = 5;
    unsigned long acc = 1;
    int i;
    for (i = 0; i < 64; i++) {
        acc += a + b;
        acc *= (a + 1);
        if ((i & 7) == 0)
            acc = acc / (b | 1UL);
        a += 1;
        b += 2;
    }
    printf("int_mix acc=%lu\n", acc);
    return 0;
}
