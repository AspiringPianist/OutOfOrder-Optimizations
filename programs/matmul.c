#include <stdint.h>

#define N 24
static int A[N][N];
static int B[N][N];
static int C[N][N];

/* Sustained high issue/LSU/RF activity. */
int main(void) {
    for (int i = 0; i < N; i++) {
        for (int j = 0; j < N; j++) {
            A[i][j] = i + j;
            B[i][j] = i * j + 1;
            C[i][j] = 0;
        }
    }
    for (int i = 0; i < N; i++) {
        for (int k = 0; k < N; k++) {
            int aik = A[i][k];
            for (int j = 0; j < N; j++) {
                C[i][j] += aik * B[k][j];
            }
        }
    }
    volatile int s = 0;
    for (int i = 0; i < N; i++) s += C[i][i];
    return s & 0xff;
}
