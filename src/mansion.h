/* The mansion as data: the plan, doors, stairs and waypoints of every floor, and the rules' tables (the
   spec, "The mansion"). The tables are generated into build/ by tools/make_mansion.py. */
#ifndef MANSION_H
#define MANSION_H
#include "mansion_tables.h"

#define WALL 0xFF             /* a room's way out that is wall */
#define EDGE 0x80             /* ...or the floor's outer edge (plus the room) */
#define GAME_9 8

u8 bit_mask(u8 column);
u8 wall_at(u8 x, u8 y, u8 floor);
u8 door_id(u8 floor, u8 room, u8 direction);
u8 waypoint_x_of(u8 floor, u8 index);
u8 waypoint_y_of(u8 floor, u8 index);
u8 random_bit(u8 number);

#endif
