/* Haunted House: By Matchlight, for the Super Nintendo - the program's start. Each frame: read the pad as
   the 2600's controls, run one frame of the game (player.c), and wait for the next picture. The checks
   read frame_count and late_frames (tests/test_boot.py, tests/verify_engine.py). */
#include <snes.h>
#include "state.h"
#include "engine.h"

#define READY 0x42                   /* ready_flag's value once the program has set the console up */
#define RANDOM_SEED_LOW 0x31         /* the random numbers must start somewhere other than 0 */
#define RANDOM_SEED_HIGH 0x8F

u8 game_ram[128];    /* the game's state, at the 2600's offsets (state.h) */
u16 frame_count;     /* frames since the program started */
u16 frames_done;     /* game frames worked out to the end (the checks wait for this to move on) */
u8 ready_flag;       /* READY once the console is set up */
u8 lights_on;        /* the player's cheat (the remaster's O key): the whole floor lit, everything shown */
u16 late_frames;     /* frames that took longer than a frame to work out (the checks allow a few) */
u16 end_line;        /* the scanline the last frame's work ended on (of 262): how near the limit it came */
u16 busiest_line;    /* the lowest such line ever... */
u16 busiest_frame;   /* ...and which frame that was */

#define LATCH_COUNTERS (*(volatile u8 *)0x2137)    /* SLHV: reading it latches the PPU's H and V counters */
#define VERTICAL_COUNTER (*(volatile u8 *)0x213D)  /* OPVCT: the latched V counter, low byte then high */

static volatile u8 latch_sink;   /* the latch is read for its side effect; this keeps the read */

/* The scanline the picture is on now (0-261): the PPU's vertical counter, latched then read in two. */
u16 scanline_now(void)
{
    u8 low;
    u8 high;
    latch_sink = LATCH_COUNTERS;
    low = VERTICAL_COUNTER;
    high = VERTICAL_COUNTER & 1;
    return ((u16)high << 8) | low;
}

/* Note how far into the frame the work got, for the busiest frame so far. */
static void note_busiest(void)
{
    end_line = scanline_now();
    if (end_line > busiest_line) {
        busiest_line = end_line;
        busiest_frame = frame_count;
    }
}

/* The pad as the 2600's joystick, button and console switches. */
static void read_controls(Controls *controls)
{
    u16 pad = padsCurrent(0);
    controls->stick = 0;
    if (pad & KEY_RIGHT) {
        controls->stick |= STICK_RIGHT;
    }
    if (pad & KEY_LEFT) {
        controls->stick |= STICK_LEFT;
    }
    if (pad & KEY_DOWN) {
        controls->stick |= STICK_DOWN;
    }
    if (pad & KEY_UP) {
        controls->stick |= STICK_UP;
    }
    controls->button = (pad & (KEY_B | KEY_A)) != 0;
    controls->reset = (pad & KEY_START) != 0;
    controls->select = (pad & KEY_SELECT) != 0;
    if (controls->button) {   /* the button held: Select is the cheat's (as the NES game), not the game's */
        controls->select = 0;
        if (padsDown(0) & KEY_SELECT) {
            lights_on ^= 1;
        }
    }
}

/* Power-on: the game sets itself up as if RESET had been pressed, then goes to select mode with game 1.
   (Work RAM holds whatever it held: nothing is zero until it's made so.) */
static void power_on(void)
{
    u8 address;
    for (address = 0; address < sizeof game_ram; address++) {
        game_ram[address] = 0;
    }
    frame_count = 0;
    frames_done = 0;
    late_frames = 0;
    end_line = 0;
    busiest_line = 0;
    busiest_frame = 0;
    lights_on = 0;
    RAM(RANDOM_LOW) = RANDOM_SEED_LOW;
    RAM(RANDOM_HIGH) = RANDOM_SEED_HIGH;
    set_up_columns();
    new_game();
    select_mode();
}

int main(void)
{
    Controls controls;
    u16 last_vblank;
    consoleInit();
    set_up_picture();
    setScreenOn();
    power_on();
    ready_flag = READY;
    last_vblank = snes_vblank_count;
    while (1) {
        draw_frame();         /* first thing in the vertical blank: the picture of the frame just worked out */
        read_controls(&controls);
        game_frame(&controls);
        compose_status();     /* the status band, if what it shows has changed */
        frames_done++;
        note_busiest();
        WaitForVBlank();
        if ((u16)(snes_vblank_count - last_vblank) > 1) {
            late_frames++;
        }
        last_vblank = snes_vblank_count;
        frame_count++;
    }
    return 0;
}
