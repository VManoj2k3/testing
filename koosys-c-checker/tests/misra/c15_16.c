/* Chapters 15-16: control flow, switch statements. */
#include <stdint.h>

int32_t ch15(int32_t a)
{
    if (a > 0) {
        goto later;                            // EXPECT 15.1
    }
later:
    if (a > 1) {
        goto earlier_block;                    // EXPECT 15.3
    }
back:
    a++;
    if (a < 5) { goto back; }                  // EXPECT 15.2
    {
earlier_block:
        a++;
    }
    for (int32_t i = 0; i < 10; i++) {
        if (i == a) { break; }
        if (i == 3) { break; }                 // EXPECT 15.4
    }
    if (a == 7) {
        return 1;                              // EXPECT 15.5
    }
    while (a < 9) a++;                         // EXPECT 15.6
    if (a == 1) {
        a = 2;
    } else if (a == 3) {                       // EXPECT 15.7
        a = 4;
    }
    return a;
}

void ch16(int32_t x, _Bool flag)
{
    switch (x) {
        case 1:
            x = 2;
            break;
        default:
            break;
        case 3:                                // EXPECT 16.5
            break;
    }
    switch (x) {                               // EXPECT 16.4
        case 1:
            if (flag) {
        case 2:                                // EXPECT 16.2
                x = 3;
            }
            break;
        case 4:
            x = 5;                             // EXPECT 16.3
        case 5:
            break;
    }
    switch (x) {                               // EXPECT 16.6
        default:
            break;
    }
    switch (flag) {                            // EXPECT 16.7
        case 0: break;
        default: break;
    }
    switch (x) {                               // EXPECT 16.1
        x = 9;
        case 1: break;
        default: break;
    }
}
