/* The mansion's tables, and the spec's wall test ($F2A1). */
#include "mansion.h"
#include "mansion_data.inc"

#define COLUMNS_START 16      /* the plan's column 0 covers x 16-31 */
#define OUTSIDE_COLUMNS 0x08  /* a column number with this bit is outside the plan: wall... */
#define MIDDLE_ROW_OPEN 8     /* ...except in the middle row, open at both sides */

/* Is the point (x, y) inside a wall? Exactly as the game tests it. */
u8 wall_at(u8 x, u8 y, u8 floor)
{
    u8 column = (u8)((x >> 4) - 1);
    u8 row = y >> 4;
    if (column & OUTSIDE_COLUMNS) {
        return row != MIDDLE_ROW_OPEN;
    }
    return (mansion_walls[floor * MANSION_WALLS_SIZE + row] & bit_mask(column)) != 0;
}

u8 bit_mask(u8 column)
{
    return (u8)(1 << column);
}

/* A room's way out: a door number, EDGE + room, or WALL. direction: 0 left, 1 right, 2 up, 3 down. */
u8 door_id(u8 floor, u8 room, u8 direction)
{
    return door_ids[floor * DOOR_IDS_SIZE + room * 4 + direction];
}

u8 waypoint_x_of(u8 floor, u8 index)
{
    return waypoint_x[floor * WAYPOINT_X_SIZE + index];
}

u8 waypoint_y_of(u8 floor, u8 index)
{
    return waypoint_y[floor * WAYPOINT_Y_SIZE + index];
}

/* The mood sound's random bit: bit 0 of the byte at $F000 + number in the original's code. */
u8 random_bit(u8 number)
{
    return (random_bits[number >> 3] >> (number & 7)) & 1;
}
