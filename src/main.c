/* Haunted House: By Matchlight, for the Super Nintendo - the program's start (docs/plan.md, step 0: a ROM
   that boots). Each frame the counter below goes up, and the checks read it to know the ROM is alive. */
#include <snes.h>

#define NIGHT_BLUE RGB5(2, 2, 10)   /* the backdrop while there is nothing to draw (red, green, blue, 0-31) */
#define READY 0x42                   /* ready_flag's value once the program has set the console up */

u16 frame_count;     /* frames since the program started (the checks read it: tests/test_boot.py) */
u8 ready_flag;       /* READY once the console is set up */

int main(void)
{
    consoleInit();
    setMode(BG_MODE1, 0);
    setPaletteColor(0, NIGHT_BLUE);
    setScreenOn();
    ready_flag = READY;
    while (1) {
        WaitForVBlank();
        frame_count++;
    }
    return 0;
}
