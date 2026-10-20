/* Touching: the 2600's collision between the eyes' picture and this frame's sprite - and, for the drop
   search, between the sprite and the walls - worked out line by line, the way the game's drawing loop puts
   them on the screen (the spec, "Touching"). */
#include "state.h"
#include "mansion.h"
#include "engine.h"

#define SCREEN_WIDTH 160
#define EDGE_STRIP 4          /* pixels at each side drawn as wall in the middle row */
#define EYES_ROWS 3
#define WIDE_SPAN 16          /* a stretched sprite covers 16 columns */

static const u8 *shape_rows;   /* this frame's sprite picture, bottom row first... */
static u8 shape_first;         /* ...and where it starts in the shapes page */
/* A picture row as a bit per column from its start (bit 0 its leftmost pixel), looked up rather than worked
   out pixel by pixel. Filled once by set_up_columns(). */
static u16 narrow_columns[256];
static u16 wide_columns[256];   /* each pixel two columns wide */
/* The same for every row of the shapes page itself, by its place in the page: one lookup per row of a
   sprite, where the loops below can't afford two. */
static u16 shape_narrow[256];
static u16 shape_wide[256];
static u8 eyes_rows[EYES_ROWS];

/* The eyes' three rows, bottom first; the pupils look the way the stick is pushed now ($F318). */
static void eyes_picture(u8 stick)
{
    u8 pupils = PUPILS_AHEAD;
    u8 row = 1;
    eyes_rows[0] = EYES_ROW;
    eyes_rows[1] = EYES_ROW;
    eyes_rows[2] = EYES_ROW;
    if (stick & STICK_RIGHT) {
        pupils = PUPILS_RIGHT;
    }
    if (stick & STICK_LEFT) {
        pupils = PUPILS_LEFT;
    }
    if (stick & STICK_DOWN) {
        row -= 1;
    }
    if (stick & STICK_UP) {
        row += 1;
    }
    eyes_rows[row] = pupils;
}

/* The first line drawn and the line below the last ($F46D): the whole view, or with a match lit in games
   2-9, only the player's room. */
static void drawn_lines(u8 *top, u8 *below)
{
    u8 limited = (RAM(FLAGS) & MATCH_LIT) && !(RAM(DOORWAY) & IN_DOORWAY) && RAM(GAME_NUMBER);
    *top = TOP_LINE;
    *below = 0;
    if (limited && RAM(ROOM_BOTTOM)) {
        u8 bottom_line = line_of(RAM(ROOM_BOTTOM));
        if (bottom_line < 0x80) {
            *below = bottom_line;
        }
    }
    if (limited && RAM(ROOM_TOP)) {
        u8 top_line = line_of(RAM(ROOM_TOP));
        if (top_line < VIEW_LINES) {
            *top = top_line;
        }
    }
}

/* One row of an 8-pixel picture as a bit per column from its start: bit 0 its leftmost column, each pixel
   two columns wide if stretched. */
static u16 columns_of(u8 row, u8 wide)
{
    u16 lit = 0;
    u8 pixel;
    for (pixel = 0; pixel < 8; pixel++) {
        if (row & (0x80 >> pixel)) {
            lit |= wide ? (u16)3 << (pixel * 2) : (u16)1 << pixel;
        }
    }
    return lit;
}

void set_up_columns(void)
{
    u16 row;
    for (row = 0; row < 256; row++) {
        narrow_columns[row] = columns_of((u8)row, 0);
        wide_columns[row] = columns_of((u8)row, 1);
    }
    for (row = 0; row < 256; row++) {
        shape_narrow[row] = narrow_columns[shapes[row]];
        shape_wide[row] = wide_columns[shapes[row]];
    }
}

/* A picture row's columns, looked up. */
static u16 lit_columns(u8 row, u8 wide)
{
    return wide ? wide_columns[row] : narrow_columns[row];
}

/* The eyes' row drawn on a line, as columns from the player's x; 0 where they aren't. */
#define EYES_COLUMNS_ON(line) (eyes_index = (u8)((line) - RAM(EYES_LINE)), \
                               eyes_index < EYES_ROWS ? narrow_columns[eyes_rows[eyes_index]] : 0)
static u8 eyes_index;

/* Do columns `sprite_lit` from `start` share any with columns `eyes_lit` from the player's x, the two
   starts `offset` apart? */
static u8 columns_meet_at(u16 sprite_lit, u16 eyes_lit, s16 offset)
{
    u16 shifted;
    if (offset <= -8 || offset >= WIDE_SPAN) {
        return 0;
    }
    shifted = offset >= 0 ? eyes_lit >> offset : eyes_lit << (-offset);
    return (sprite_lit & shifted) != 0;
}

/* Do the sprite's columns (from `start`) share any with the eyes' (8 from the player's x)? Columns wrap
   round the 160-column screen, which only matters when either picture reaches the right edge. */
static u8 columns_meet(u16 sprite_lit, u8 start, u16 eyes_lit)
{
    s16 offset = (s16)start - RAM(POS_X);
    if (columns_meet_at(sprite_lit, eyes_lit, offset)) {
        return 1;
    }
    if (start < SCREEN_WIDTH - WIDE_SPAN && RAM(POS_X) < SCREEN_WIDTH - 8) {
        return 0;   /* neither wraps */
    }
    return columns_meet_at(sprite_lit, eyes_lit, offset - SCREEN_WIDTH)
           || columns_meet_at(sprite_lit, eyes_lit, offset + SCREEN_WIDTH);
}

/* The lowest n bits set, for n up to 16: a span of columns as bits. */
static const u16 low_bits[WIDE_SPAN + 1] = {
    0x0000, 0x0001, 0x0003, 0x0007, 0x000F, 0x001F, 0x003F, 0x007F, 0x00FF,
    0x01FF, 0x03FF, 0x07FF, 0x0FFF, 0x1FFF, 0x3FFF, 0x7FFF, 0xFFFF,
};

/* Outside the plan's columns on the middle row the screen is open but for the strip of wall at each side:
   which of a span of columns (within one cell: 0-15 or 144-159) are strip, as bits from the span's start. */
static u16 strip_bits(u8 column, u8 span)
{
    u16 bits = 0;
    u8 end = column + span;
    if (column < EDGE_STRIP) {
        u8 count = EDGE_STRIP - column;
        bits |= low_bits[count > span ? span : count];
    }
    if (end > SCREEN_WIDTH - EDGE_STRIP) {
        u8 first = column > SCREEN_WIDTH - EDGE_STRIP ? column : SCREEN_WIDTH - EDGE_STRIP;
        bits |= low_bits[end - first] << (first - column);
    }
    return bits;
}

/* The wall in the plan's row `row` under the sprite's 16 columns (from `start`, wrapping round the
   screen), as a bit per column: the plan's cells, the solid outside the plan's columns (but for the middle
   row), and the middle row's edge strips. Worked out a cell's span at a time rather than by wall_at, column
   by column, which costs more than a frame. floor_walls is this floor's plan. */
static u16 wall_columns_in_row(u8 row, u8 start, const u8 *floor_walls)
{
    u16 walls = 0;
    u8 column = start;
    u8 index = 0;
    u8 middle = row == MIDDLE_ROW;
    u8 plan = floor_walls[row];
    while (index < WIDE_SPAN) {
        u8 span;
        u8 cell;
        if (column >= SCREEN_WIDTH) {
            column -= SCREEN_WIDTH;
        }
        span = 16 - (column & 15);   /* to the end of this cell */
        if (span > WIDE_SPAN - index) {
            span = WIDE_SPAN - index;
        }
        cell = (u8)((column >> 4) - 1);
        if (!(cell & 0x08)) {
            if ((plan >> cell) & 1) {
                walls |= low_bits[span] << index;
            }
        } else if (!middle) {
            walls |= low_bits[span] << index;
        } else {
            walls |= strip_bits(column, span) << index;
        }
        index += span;
        column += span;
    }
    return walls;
}

/* A picture row's columns, looked up (a macro: a call costs too much where this is used). */
#define LIT_COLUMNS(row, wide) ((wide) ? wide_columns[row] : narrow_columns[row])

/* Did the sprite touch the eyes? The eyes are on three lines; a sprite row on line L meets the eyes' row
   on L (the line's second scanline) and the one on L - 1 (the first scanline of the line below, where the
   sprite shows the row of the line above). So for each of the eyes' lines e, the sprite's rows on e and
   on e + 1 are the only ones to test. */
static u8 eyes_touched(const Sprite *sprite, u8 start, u8 lowest, u8 top)
{
    u8 which;
    for (which = 0; which < EYES_ROWS; which++) {
        u16 eyes_lit = narrow_columns[eyes_rows[which]];
        u8 line = (u8)(RAM(EYES_LINE) + which);
        u8 pair;
        if (!eyes_lit) {
            continue;
        }
        for (pair = 0; pair < 2; pair++, line++) {
            u8 index = (u8)(line - sprite->line);
            u8 row;
            if (index >= sprite->height || line < lowest || line > top) {
                continue;
            }
            row = shape_rows[index];
            if (row && columns_meet(LIT_COLUMNS(row, sprite->wide), start, eyes_lit)) {
                return 1;
            }
        }
    }
    return 0;
}

#define GATHERED_ROWS 4       /* a sprite's 17 rows and the line below them span three plan rows at most */
static u16 gathered[GATHERED_ROWS];     /* the lit columns of the sprite's rows in each plan row touched... */
static u8 gathered_row[GATHERED_ROWS];  /* ...which plan row each is */
static u8 gathered_count;

/* Add lit columns to a plan row's: the one already gathered for it, else a new one. */
static void gather(u8 plan_row, u16 lit)
{
    u8 which;
    for (which = 0; which < gathered_count; which++) {
        if (gathered_row[which] == plan_row) {
            gathered[which] |= lit;
            return;
        }
    }
    if (gathered_count < GATHERED_ROWS) {
        gathered_row[gathered_count] = plan_row;
        gathered[gathered_count] = lit;
        gathered_count++;
    }
}

/* The lit columns of the sprite's rows `from` to `to`, together. (Kept to the least work per row: this
   compiler's code costs about four scanlines a loop round, so the loop round must do almost nothing.) */
static u16 rows_together(u8 from, u8 to, u8 wide)
{
    const u16 *columns = (wide ? shape_wide : shape_narrow) + shape_first;
    u16 lit = 0;
    u8 index;
    for (index = from; index <= to; index++) {
        lit |= columns[index];
    }
    return lit;
}

/* Gather the sprite's rows `from` to `to` (which are drawn) by the plan's 16-unit rows their lines fall
   in: each row against its own line's plan row, and a plan row's first line against the plan row below
   as well (its first scanline shows the row of the line above). first_y is row `from`'s floor y. */
static void gather_rows(u8 from, u8 to, s16 first_y, u8 wide)
{
    u8 index = from;
    s16 floor_y = first_y;
    while (index <= to) {
        u8 last = index + (15 - ((u8)floor_y & 15));   /* the last row in this plan row */
        u8 first_row;
        if (last > to) {
            last = to;
        }
        if (floor_y >= 0 && floor_y <= 255) {
            u16 lit = rows_together(index, last, wide);
            if (lit) {
                gather((u8)floor_y >> 4, lit);
            }
        }
        first_row = shape_rows[index];
        if (first_row && ((u8)floor_y & 15) == 0 && floor_y >= 1 && floor_y <= 256) {
            gather((u8)(floor_y - 1) >> 4, LIT_COLUMNS(first_row, wide));
        }
        floor_y += last - index + 1;
        index = last + 1;
    }
}

/* Did the sprite touch the walls (the drop search's question)? Only the rows on the lines drawn count
   (`lowest` to `top`); the rows' lines may wrap past 255 to 0, so there can be two runs of them. */
static u8 walls_touched(const Sprite *sprite, u8 start, u8 lowest, u8 top, const u8 *floor_walls)
{
    s16 first_y = (s16)sprite->line - RAM(EYES_LINE) + RAM(POS_Y);   /* the first row's floor y */
    u8 before_wrap = (u8)(255 - sprite->line) + 1 < sprite->height ? (u8)(255 - sprite->line) + 1
                                                                   : sprite->height;
    s16 from;
    s16 to;
    u8 index;
    gathered_count = 0;
    from = (s16)lowest - sprite->line;                /* the rows whose lines don't wrap */
    to = (s16)top - sprite->line;
    if (from < 0) {
        from = 0;
    }
    if (to > before_wrap - 1) {
        to = before_wrap - 1;
    }
    if (from <= to) {
        gather_rows((u8)from, (u8)to, first_y + from, sprite->wide);
    }
    if (before_wrap < sprite->height) {               /* the rows whose lines wrapped to 0, 1, 2... */
        from = (s16)before_wrap + lowest;
        to = (s16)before_wrap + top;
        if (to > sprite->height - 1) {
            to = sprite->height - 1;
        }
        if (from <= to) {
            gather_rows((u8)from, (u8)to, first_y + from, sprite->wide);
        }
    }
    for (index = 0; index < gathered_count; index++) {
        if (gathered[index] & wall_columns_in_row(gathered_row[index], start, floor_walls)) {
            return 1;
        }
    }
    return 0;
}

/* What this frame's sprite overlapped: the eyes, and (for the drop search) the walls.

   The 2600 draws the view from line `top` down to the line above `below`, two scanlines a line: on a
   line's first scanline the eyes show their row for that line and the sprite its row for the line above;
   on the second, both show their rows for that line. The first line drawn shows no eyes, and the last
   only its first scanline. Put together, a sprite row on line L is tested on L and on L - 1, for every L
   from the second line drawn down to two above `below`. */
void draw(const Sprite *sprite, u8 stick, Touches *touches)
{
    u8 top;
    u8 below;
    u8 lowest;
    u8 start = sprite->x + (sprite->wide ? 1 : 0);   /* the TIA starts a stretched player a pixel later */
    touches->eyes = 0;
    touches->walls = 0;
    if (!sprite->height) {
        return;
    }
    shape_rows = shapes + sprite->picture;
    shape_first = sprite->picture;
    eyes_picture(stick);
    drawn_lines(&top, &below);
    lowest = below < top ? below + 2 : 1;
    touches->eyes = eyes_touched(sprite, start, lowest, top);
    if (RAM(DROP_TRIES)) {
        const u8 *floor_walls = mansion_walls + RAM(FLOOR) * MANSION_WALLS_SIZE;
        touches->walls = walls_touched(sprite, start, lowest, top, floor_walls);
    }
}
