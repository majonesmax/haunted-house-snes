/* The match's light (docs/plan.md, step 2): two windows round the eyes - the lit disc, and the dim ring
   round it - their edges set scanline by scanline by HDMA from a table built each frame; the floor layer
   shows only within them, the walls layer too in games 2-9 (in game 1 the walls show everywhere, dimmed
   outside the light: moonlit); colour math halves what's in the ring. The light reaches as far as the
   remaster's SNES look's does, and never past the room's limits in games 2-9 (the original's rule).
   The same colour math does the rest of the SNES look's view: a lightning flash washes the walls pale,
   dying tints the view red, and the lights-on cheat shows the whole floor. */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "light.h"

#define VIEW_X 8
#define VIEW_Y 32
#define VIEW_LINES 80
#define VIEW_BOTTOM_LINE (VIEW_Y + VIEW_LINES * 2)
#define SCREEN_LINES 224
#define HDMA_CHANNEL 3                /* (engine.h: the others) */
#define HDMA_FOUR_REGISTERS 4        /* the transfer mode: four bytes to four registers in a row */
#define WINDOW_REGISTERS 0x26        /* WH0: the four window edge registers start here */
#define MOST_LINES 127               /* an entry covers at most this many lines */
#define BANK_WORK_RAM 0x7E
#define CLOSED_LEFT 255              /* a window with its left past its right is no window */
#define CLOSED_RIGHT 0
/* The window registers' settings (the SNES's W12SEL, WBGLOG, TMW, WOBJSEL, CGWSEL, CGADSUB). A layer is
   hidden where its window region is; the region wanted is outside both windows, so each is inverted and
   the two combined with AND. The colour window is window 1 alone: colour math applies outside it. */
#define WALLS_WINDOWS_OUTSIDE 0x0F   /* BG1: windows 1 and 2 on, both inverted */
#define FLOOR_WINDOWS_OUTSIDE 0xF0   /* BG2: the same */
#define WINDOWS_AND 0x05             /* BG1 and BG2: the two windows' regions combined with AND */
#define MASK_FLOOR_ONLY 0x02         /* TMW: BG2 hidden where its region is */
#define MASK_WALLS_AND_FLOOR 0x03
#define MASK_NOTHING 0x00            /* (the cheat) */
#define COLOUR_WINDOW_1 0x20         /* WOBJSEL: the colour window is window 1 */
#define MATH_OUTSIDE_WINDOW 0x20     /* CGWSEL: colour math where the colour window isn't */
#define MATH_EVERYWHERE 0x00
#define HALVE_WALLS_AND_FLOOR 0x43   /* CGADSUB: add the fixed colour (black) and halve: BG1 and BG2 */
#define WASH_WALLS 0x01              /* add the fixed colour to BG1, at full: the lightning's pale walls */
#define TINT_VIEW 0x13               /* add it to BG1, BG2 and the sprites: dying's red (not the bands) */
#define NO_MATH 0x00
#define FIXED_RED 0x20               /* COLDATA: which channel of the fixed colour the low 5 bits set */
#define FIXED_GREEN 0x40
#define FIXED_BLUE 0x80
#define WASH_RED 12                  /* the lightning's wash (the SNES look's LIGHTNING_WASH, pale blue) */
#define WASH_GREEN 14
#define WASH_BLUE 20
#define DYING_RED_LOW 8              /* dying's tint pulses between these... */
#define DYING_RED_HIGH 16
#define DYING_PULSE 8                /* ...every 8 frames (a bit of the frame count) */
#define LIGHTNING_FRAMES 0x27        /* the clock's bits that are 0 on a flashing frame: 4 in 64... */
#define DYING_FLASH_FRAMES 0x03      /* ...or 1 in 4 while dying */

u8 light_centre_x;                   /* what light_rows (src/fast.asm) takes... */
u8 light_first_row;
u8 light_row_count;
u8 light_rows_left;                  /* ...and its working bytes */
u8 light_half_width;
u16 light_centre_pair;               /* the centre in both bytes, for the quick loop's 16-bit adds */
void light_rows(void);
static u8 rows_centre_x = 0xFF;      /* the rows now in the table are for this centre... */
static u8 rows_first = 0xFF;         /* ...this first shape row... */
static u8 rows_count;                /* ...and this many: walking up or down, they serve again */

/* The HDMA table: two entries of (lines, four edges) for the lines above the light - always two, so the
   rows start at a fixed place for light_rows to write them - then (lines | HDMA_REPEAT) and a row's edges for
   each line of the light, two entries for the lines below, and 0 to end. */
#define ENTRY 5                      /* bytes: a count and four edges */
#define ROWS_AT (2 * ENTRY + 1)      /* where the light's rows start (light_rows writes them there) */
u8 light_table[ROWS_AT + LIGHT_ROWS * 4 + 2 * ENTRY + 1];
static u8 shown_mask = 0xFF;         /* the colour rules as the registers have them (written on change) */
static u8 shown_math = 0xFF;
static u8 shown_where = 0xFF;
static u8 shown_red = 0xFF;
static u8 shown_green = 0xFF;
static u8 shown_blue = 0xFF;

void set_up_light(void)
{
    REG_W12SEL = WALLS_WINDOWS_OUTSIDE | FLOOR_WINDOWS_OUTSIDE;
    REG_WBGLOG = WINDOWS_AND;
    REG_WOBJSEL = COLOUR_WINDOW_1;
    shown_mask = 0xFF;               /* (the rules are written as the first frame finds them) */
    shown_math = 0xFF;
    shown_where = 0xFF;
    shown_red = 0xFF;
    shown_green = 0xFF;
    shown_blue = 0xFF;
}

/* --- the colour rules ----------------------------------------------------------------------------- */
/* The lightning (the spec's rule, as the NES game's lightning_now): while dying, every fourth frame; else
   while a monster is in the room, on 4 frames in 64; each time on the toss of the random numbers' low
   bit. */
static u8 lightning_now(void)
{
    u8 clock = RAM(CLOCK);
    if (RAM(DEATH_TIMER)) {
        if (clock & DYING_FLASH_FRAMES) {
            return 0;
        }
    } else {
        if (RAM(MONSTERS_HERE) == 0) {
            return 0;
        }
        if (clock & LIGHTNING_FRAMES) {
            return 0;
        }
    }
    return RAM(RANDOM_LOW) & 1;
}

/* This frame's rules: what's hidden outside the light, what colour math does there and with which fixed
   colour (the SNES's TMW, CGADSUB, CGWSEL and COLDATA); written only when they change. */
static void set_colour_rules(void)
{
    u8 mask = MASK_WALLS_AND_FLOOR;
    u8 math = HALVE_WALLS_AND_FLOOR;
    u8 where = MATH_OUTSIDE_WINDOW;
    u8 red = 0;
    u8 green = 0;
    u8 blue = 0;
    if (lights_on) {
        mask = MASK_NOTHING;
        math = NO_MATH;
    } else if (RAM(GAME_NUMBER) == 0) {
        mask = MASK_FLOOR_ONLY;          /* (the walls moonlit: the lightning isn't seen on them) */
    } else if (lightning_now()) {
        mask = MASK_FLOOR_ONLY;
        math = WASH_WALLS;
        red = WASH_RED;
        green = WASH_GREEN;
        blue = WASH_BLUE;
    }
    if (RAM(DEATH_TIMER)) {
        math = TINT_VIEW;
        where = MATH_EVERYWHERE;
        red = DYING_RED_LOW;
        if (frame_count & DYING_PULSE) {
            red = DYING_RED_HIGH;
        }
        green = 0;
        blue = 0;
    }
    if (mask != shown_mask) {
        REG_TMW = mask;
        shown_mask = mask;
    }
    if (math != shown_math) {
        REG_CGADSUB = math;
        shown_math = math;
    }
    if (where != shown_where) {
        REG_CGWSEL = where;
        shown_where = where;
    }
    if (red != shown_red) {
        REG_COLDATA = FIXED_RED | red;
        shown_red = red;
    }
    if (green != shown_green) {
        REG_COLDATA = FIXED_GREEN | green;
        shown_green = green;
    }
    if (blue != shown_blue) {
        REG_COLDATA = FIXED_BLUE | blue;
        shown_blue = blue;
    }
}

/* An entry of lines with no window at all (1 to 127 of them). */
static u8 *closed_entry(u8 *table, u8 lines)
{
    *table++ = lines;
    *table++ = CLOSED_LEFT;
    *table++ = CLOSED_RIGHT;
    *table++ = CLOSED_LEFT;
    *table++ = CLOSED_RIGHT;
    return table;
}

/* Two entries of lines with no window, lines split between them (each then under 128, and never 0,
   which would end the table: there are always 32 lines or more). */
static u8 *closed_lines(u8 *table, u8 lines)
{
    u8 half = lines >> 1;
    table = closed_entry(table, half);
    return closed_entry(table, lines - half);
}

/* Point the HDMA channel at the table: each frame it sends the edges line by line. */
static void send_table(void)
{
    REG_DMAP3 = HDMA_FOUR_REGISTERS;
    REG_BBAD3 = WINDOW_REGISTERS;
    REG_A1T3LH = (u16)light_table;
    REG_A1B3 = BANK_WORK_RAM;
    REG_HDMAEN = HDMA_CHANNELS;
}

/* The light's rows on the screen this frame: the eyes' middle is 1.5 pixels a unit across (VIEW_X on),
   and the view's lines go down from its top at 2 pixels a line; the disc's middle row is at the eyes'
   middle, a line above their bottom. In games 2-9 nothing is lit above the room's top or below its
   bottom. */
static void build_table(void)
{
    u8 view_bottom = (u8)(RAM(POS_Y) - RAM(EYES_LINE));
    s16 eyes_line = (s16)RAM(POS_Y) - view_bottom;              /* the eyes' bottom line in the view */
    s16 centre_y = VIEW_Y + ((VIEW_LINES - eyes_line) << 1) - 2;
    s16 top = centre_y - LIGHT_MIDDLE_ROW;
    s16 first = 0;
    s16 count = LIGHT_ROWS;
    s16 highest = VIEW_Y;                                        /* no light above here... */
    s16 lowest = VIEW_BOTTOM_LINE;                               /* ...or from here down */
    u8 *table = light_table;
    s16 units = (s16)RAM(POS_X) + 4;
    light_centre_x = (u8)(VIEW_X + (((units << 1) + units) >> 1));
    if (RAM(GAME_NUMBER) != 0) {                                 /* games 2-9: the room's limits */
        if (RAM(ROOM_TOP)) {
            s16 limit = VIEW_Y + ((VIEW_LINES - ((s16)RAM(ROOM_TOP) - view_bottom)) << 1);
            if (limit > highest) {
                highest = limit;
            }
        }
        if (RAM(ROOM_BOTTOM)) {
            s16 limit = VIEW_Y + ((VIEW_LINES - ((s16)RAM(ROOM_BOTTOM) - view_bottom)) << 1);
            if (limit < lowest) {
                lowest = limit;
            }
        }
    }
    if (top < highest) {
        first = highest - top;
        count -= first;
        top = highest;
    }
    if (top + count > lowest) {
        count = lowest - top;
    }
    if (count <= 0) {
        table = closed_lines(table, SCREEN_LINES);
        *table = 0;
        return;
    }
    table = closed_lines(table, (u8)top);
    *table++ = HDMA_REPEAT | (u8)count;
    if (light_centre_x != rows_centre_x || (u8)first != rows_first || (u8)count != rows_count) {
        light_first_row = (u8)first;
        light_row_count = (u8)count;
        light_rows();                                /* (writes the rows at light_table + ROWS_AT) */
        rows_centre_x = light_centre_x;
        rows_first = (u8)first;
        rows_count = (u8)count;
    }
    table += (u16)count << 2;
    table = closed_lines(table, (u8)(SCREEN_LINES - top - count));
    *table = 0;
}

/* Each frame, in the vertical blank. */
void draw_light(void)
{
    set_colour_rules();
    if (RAM(FLAGS) & MATCH_LIT) {
        build_table();
    } else {
        u8 *table = closed_lines(light_table, SCREEN_LINES);
        *table = 0;
    }
    send_table();
}
