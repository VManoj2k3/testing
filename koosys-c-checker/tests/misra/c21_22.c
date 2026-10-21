/* Chapters 21-22: standard library, resources. */
#include <stdint.h>
#include <stdlib.h>
#include <setjmp.h>                            // EXPECT 21.4
#include <signal.h>                            // EXPECT 21.5
#include <stdio.h>
#include <time.h>                              // EXPECT 21.10
#include <tgmath.h>                            // EXPECT 21.11
#include <fenv.h>                              // EXPECT 21.12
#include <ctype.h>
#include <string.h>
#include <locale.h>
#include <errno.h>
#include <threads.h>
#include <stdatomic.h>

void ch21(const char *s, char *d, int32_t c)
{
    int32_t *m = malloc(4U);                   // EXPECT 21.3
    free(m);
    (void)printf("x");                         // EXPECT 21.6
    int32_t n = atoi(s);                       // EXPECT 21.7
    qsort(NULL, 0U, 0U, NULL);                 // EXPECT 21.9
    time_t t = time(NULL);
    int32_t up = toupper(-5);                  // EXPECT 21.13
    if (memcmp(s, d, 3U) == 0) { }             // EXPECT 21.14
    int16_t i16[2]; int32_t i32[2];
    memcpy(i16, i32, 4U);                      // EXPECT 21.15
    float fa[2], fb[2];
    if (memcmp(fa, fb, sizeof(fa)) == 0) { }   // EXPECT 21.16
    char small[4];
    strcpy(small, "too long text");            // EXPECT 21.17
    (void)memset(small, 0, 10U);               // EXPECT 21.18
    char *lc = setlocale(LC_ALL, NULL);
    lc[0] = 'x';                               // EXPECT 21.19
    char *e1 = getenv("A");
    char *e2 = getenv("B");
    (void)e1[0];                               // EXPECT 21.20
    (void)system("ls");                        // EXPECT 21.21
    double dd = sqrt(c);                       // EXPECT 21.22
    double pw = pow(1.0f, 2.0);                // EXPECT 21.23
    int32_t rn = rand();                       // EXPECT 21.24
    atomic_int ai;
    atomic_store_explicit(&ai, 1, memory_order_relaxed); // EXPECT 21.25
    mtx_t mx;
    (void)mtx_init(&mx, mtx_plain);
    (void)mtx_timedlock(&mx, NULL);            // EXPECT 21.26
    (void)n; (void)t; (void)up; (void)e2; (void)dd; (void)pw; (void)rn;
}

void ch21_abort(void)
{
    abort();                                   // EXPECT 21.8
}

void ch22(void)
{
    int32_t *leak = malloc(8U);                // EXPECT 22.1
    int32_t local = 0;
    free(&local);                              // EXPECT 22.2
    FILE *r = fopen("a.txt", "r");
    FILE *w = fopen("a.txt", "w");             // EXPECT 22.3
    (void)fputs("x", r);                       // EXPECT 22.4
    FILE copy = *r;                            // EXPECT 22.5
    (void)fclose(w);
    (void)fputs("x", w);                       // EXPECT 22.6
    char ch = (char)getchar();
    if (ch == EOF) { }                         // EXPECT 22.7
    long v = strtol("1", NULL, 10);            // EXPECT 22.8
    errno = 0;
    long v2 = strtol("1", NULL, 10);
    v2 = strtol("2", NULL, 10);                // EXPECT 22.9
    errno = 0;
    (void)printf("x");
    if (errno != 0) { }                        // EXPECT 22.10
    (void)leak; (void)copy; (void)v; (void)v2; (void)fclose(r);
}

static int run(void *a) { (void)a; return 0; }
void ch22_threads(void)
{
    thrd_t th;
    (void)thrd_create(&th, run, NULL);
    (void)thrd_join(th, NULL);
    (void)thrd_join(th, NULL);                 // EXPECT 22.11
    mtx_t m1;
    mtx_t copy = m1;                           // EXPECT 22.12
    mtx_t local_m;                             // EXPECT 22.13
    (void)mtx_lock(&local_m);                  // EXPECT 22.14
    mtx_destroy(&local_m);                     // EXPECT 22.15
    (void)mtx_lock(&m1);                       // EXPECT 22.16
    (void)mtx_unlock(&copy);                   // EXPECT 22.17
    (void)mtx_lock(&m1);                       // EXPECT 22.18
    cnd_t cv;
    (void)cnd_wait(&cv, &m1);
    (void)cnd_wait(&cv, &local_m);             // EXPECT 22.19
    tss_t key;
    (void)tss_get(key);                        // EXPECT 22.20
}
