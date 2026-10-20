/* The match's light (docs/plan.md, step 2): two windows round the eyes - the lit disc, and the dim ring
   round it - their edges set scanline by scanline by HDMA from a table built each frame; the floor layer
   shows only within them, the walls layer too in games 2-9 (in game 1 the walls show everywhere, dimmed
   outside the light: moonlit); colour math halves what's in the ring. The light reaches as far as the
   remaster's SNES look's does, and never past the room's limits in games 2-9 (the original's rule). */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "light.h"

#define VIEW_X 8
#define VIEW_Y 32
#define VIEW_LINES 80
#define VIEW_BOTTOM_LINE (VIEW_Y + VIEW_LINES * 2)
#define SCREEN_LINES 224
#define HDMA_CHANNEL 3                /* (channel 7 the library uses itself) */
#define HDMA_ENABLE (1 << HDMA_CHANNEL)
#define HDMA_FOUR_REGISTERS 4        /* the transfer mode: four bytes to four registers in a row */
#define WINDOW_REGISTERS 0x26        /* WH0: the four window edge registers start here */
#define REPEAT 0x80                  /* a table entry's count with this bit: a line's own bytes each line */
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
#define COLOUR_WINDOW_1 0x20         /* WOBJSEL: the colour window is window 1 */
#define MATH_OUTSIDE_WINDOW 0x20     /* CGWSEL: colour math where the colour window isn't */
#define HALVE_WALLS_AND_FLOOR 0x43   /* CGADSUB: add the fixed colour (black) and halve: BG1 and BG2 */

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
   rows start at a fixed place for light_rows to write them - then (lines | REPEAT) and a row's edges for
   each line of the light, two entries for the lines below, and 0 to end. */
#define ENTRY 5                      /* bytes: a count and four edges */
#define ROWS_AT (2 * ENTRY + 1)      /* where the light's rows start (light_rows writes them there) */
u8 light_table[ROWS_AT + LIGHT_ROWS * 4 + 2 * ENTRY + 1];
static u8 shown_dark;                /* whether the layers are set for games 2-9 (walls hidden too) */

void set_up_light(void)
{
    REG_W12SEL = WALLS_WINDOWS_OUTSIDE | FLOOR_WINDOWS_OUTSIDE;
    REG_WBGLOG = WINDOWS_AND;
    REG_WOBJSEL = COLOUR_WINDOW_1;
    REG_CGWSEL = MATH_OUTSIDE_WINDOW;
    REG_CGADSUB = HALVE_WALLS_AND_FLOOR;
    REG_COLDATA = 0xE0;              /* the fixed colour: black (all three channels, 0) */
    REG_TMW = MASK_FLOOR_ONLY;
    shown_dark = 0;
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
    REG_HDMAEN = HDMA_ENABLE;   /* (written whole: the register can't be read; this is the only channel) */
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
    *table++ = REPEAT | (u8)count;
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
    u8 dark = RAM(GAME_NUMBER) != 0;
    if (dark != shown_dark) {
        REG_TMW = dark ? MASK_WALLS_AND_FLOOR : MASK_FLOOR_ONLY;
        shown_dark = dark;
    }
    if (RAM(FLAGS) & MATCH_LIT) {
        build_table();
    } else {
        u8 *table = closed_lines(light_table, SCREEN_LINES);
        *table = 0;
    }
    send_table();
}
