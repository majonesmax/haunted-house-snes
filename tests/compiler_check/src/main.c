/* The compiler's answers to logical conditions, for tests/test_compiler.py: every expression below is
   evaluated for a, b and c in {0, 1, 0xFE} and the results written where the test can read them. The test
   compares them with the truth, so the shapes 816-tcc compiles wrongly are known (CLAUDE.md lists them). */
#include <snes.h>

#define VALUES 3
#define EXPRESSIONS 16
#define DONE 0x42

static const u8 values[VALUES] = {0, 1, 0xFE};
u8 results[VALUES * VALUES * VALUES * EXPRESSIONS];
u8 done_flag;

static void evaluate(u8 a, u8 b, u8 c, u8 *out)
{
    out[0] = (a || b) ? 1 : 0;
    out[1] = (a || b || c) ? 1 : 0;
    out[2] = (a || !b || c) ? 1 : 0;
    out[3] = (!a || b) ? 1 : 0;
    out[4] = (a && b) ? 1 : 0;
    out[5] = (a && !b) ? 1 : 0;
    out[6] = (!a && !b) ? 1 : 0;
    out[7] = ((a && b) || c) ? 1 : 0;
    out[8] = (a || (b && c)) ? 1 : 0;
    out[9] = (!(a || b)) ? 1 : 0;
    out[10] = (a != 0 && b != 0) ? 1 : 0;
    out[11] = (a && !b && c) ? 1 : 0;
    out[12] = (!a || !b || !c) ? 1 : 0;
    out[13] = ((a & 0x40) && !(b & 0x80) && c) ? 1 : 0;
    out[14] = (a == 1 || b == 1 || c == 1) ? 1 : 0;
    out[15] = ((a || b) && !c) ? 1 : 0;
}

int main(void)
{
    u8 i;
    u8 j;
    u8 k;
    consoleInit();
    for (i = 0; i < VALUES; i++) {
        for (j = 0; j < VALUES; j++) {
            for (k = 0; k < VALUES; k++) {
                evaluate(values[i], values[j], values[k], results + ((i * VALUES + j) * VALUES + k) * EXPRESSIONS);
            }
        }
    }
    done_flag = DONE;
    while (1) {
        WaitForVBlank();
    }
    return 0;
}
