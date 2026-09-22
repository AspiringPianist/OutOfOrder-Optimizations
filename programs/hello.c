#include <stdio.h>

/* HTIF hello: proves fesvr stdout, not UART. Compile with htif_nano.specs. */
int main(void) {
    printf("hello from boom\n");
    return 0;
}
