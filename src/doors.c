/* Doors and rooms: the room number changes only as the player walks through a doorway, and a room's limits
   and stairs are worked out whenever the room or floor changes (the spec, "Doors and rooms"). */
#include "state.h"
#include "mansion.h"
#include "engine.h"

#define DOORWAY_CROSSINGS 6
#define BLOCK_ACROSS 0x40     /* BLOCKED's bits: a locked door across, or up and down */
#define BLOCK_UP_DOWN 0x80

/* The six crossings in the order they're tested, as directions (0 left, 1 right, 2 up, 3 down): up from
   the bottom row, up from the middle, down into the middle, down into the bottom, left, right. */
static const u8 crossing_direction[DOORWAY_CROSSINGS] = {2, 2, 3, 3, 0, 1};
static const u8 direction_stick[4] = {STICK_LEFT, STICK_RIGHT, STICK_UP, STICK_DOWN};

/* Game 1 has no door sounds ($FCD1). */
static void door_sound(u8 effect)
{
    if (RAM(GAME_NUMBER)) {
        start_effect(effect);
    }
}

/* Is the way out of this room locked (or not a door at all)? ($FDA6) */
static u8 door_shut(u8 direction)
{
    u8 neighbour = door_id(RAM(FLOOR), RAM(ROOM), direction);
    if (neighbour & EDGE) {
        return 1;
    }
    return door_locked(RAM(FLOOR), neighbour);
}

/* ($FCA5) */
static void enter_doorway(u8 direction)
{
    if (RAM(DOORWAY) & IN_DOORWAY) {
        return;
    }
    if (door_shut(direction) && RAM(CARRIED) != KEY) {
        RAM(BLOCKED) = direction < 2 ? BLOCK_ACROSS : BLOCK_UP_DOWN;
        door_sound(EFFECT_BLOCKED);
        return;
    }
    RAM(ROOM_BEYOND) = (u8)(RAM(ROOM) + room_step[direction]);
    RAM(DOORWAY) = direction | IN_DOORWAY;
    door_sound(EFFECT_DOORWAY);
}

/* Out of the far side of a doorway: into the next room ($FC7E). Turning back counts from the room beyond,
   so the step lands back where the player came from. */
static void leave_doorway(u8 direction)
{
    if (!(RAM(DOORWAY) & IN_DOORWAY)) {
        return;
    }
    if (RAM(DOORWAY) != (direction | IN_DOORWAY)) {
        RAM(ROOM) = RAM(ROOM_BEYOND);
    }
    follow_through_door(RAM(ROOM), direction);
    RAM(DOORWAY) = direction;
    RAM(ROOM) = (u8)(RAM(ROOM) + room_step[direction]);
    RAM(ROOM_BEYOND) = NOTHING;
    room_changed();
    door_sound(EFFECT_NEW_ROOM);
}

/* Test the six crossings in order; the first whose start or end the player is on, pushing that way, ends
   the search ($FC3C). */
void doorways(void)
{
    const u8 *lines = doorway_lines + RAM(FLOOR) * DOORWAY_LINES_SIZE;
    u8 crossing;
    for (crossing = 0; crossing < DOORWAY_CROSSINGS; crossing++) {
        u8 direction = crossing_direction[crossing];
        u8 where;
        if (!(RAM(JOYSTICK) & direction_stick[direction])) {
            continue;
        }
        where = direction < 2 ? RAM(POS_X) : RAM(POS_Y);
        if (where == lines[crossing * 2]) {
            enter_doorway(direction);
            return;
        }
        if (where == lines[crossing * 2 + 1]) {
            leave_doorway(direction);
            return;
        }
    }
}

/* The y limit through the door this way, or 0 for none ($FD6C). */
u8 room_bound(u8 direction)
{
    u8 neighbour = door_id(RAM(FLOOR), RAM(ROOM), direction);
    if (neighbour & EDGE) {
        return 0;
    }
    return room_bounds[RAM(FLOOR) * ROOM_BOUNDS_SIZE + (neighbour >> 1)];
}

/* STAIRS for the room: $0F for none, else the edge plus 4 if they go up ($FD4C). */
u8 stairs_here(void)
{
    u8 room = RAM(ROOM);
    u8 index = floor_index(RAM(FLOOR));
    u8 going_up;
    if (!(rooms_with_stairs[index] & bit(room))) {
        return NO_STAIRS;
    }
    going_up = stairs_go_up[index] & bit(room);
    return (going_up ? GOES_UP : 0) | stairs_edge[RAM(FLOOR) * STAIRS_EDGE_SIZE + room];
}

/* A room's limits and stairs ($FD0A), whenever the room or floor changes. */
void room_changed(void)
{
    u8 has_left_door;
    RAM(ROOM_TOP) = room_bound(2);
    RAM(ROOM_BOTTOM) = room_bound(3);
    has_left_door = room_bound(0) != 0;
    RAM(MASK_X) = has_left_door ? MASK_WITH_LEFT_DOOR : MASK_WITHOUT;
    RAM(MASK_X_2) = has_left_door ? MASK_2_WITH_LEFT_DOOR : MASK_2_WITHOUT;
    RAM(STAIRS) = stairs_here();
}
