/* How the monsters move (the spec, "Monsters"; the remaster's game/monsters.py): they walk between
   waypoints, chase the player in their room, follow from game 6, and are scattered on RESET and after a
   death. The random numbers live here too. */
#include "state.h"
#include "mansion.h"
#include "engine.h"

#define WANDER_FRAMES 0x88    /* the frames of 8 a wandering monster steps on: 3 and 7 */
#define KIND_CENTRE 0         /* a plan's kinds: to a room's centre, a door, stairs down, stairs up */
#define KIND_DOOR 1
#define KIND_STAIRS_DOWN 2
#define KIND_STAIRS_UP 3
#define FAST_FROM_GAME 7      /* games 8-9: the fast chase table; the ghost ignores the scepter */
#define FOLLOW_FROM_GAME 5    /* games 6-9: monsters follow the player through doors and stairs */
#define LOCKS_FROM_GAME 2     /* games 3-9 have locked doors */
#define FOUR_FLOORS_MASK 3
#define EIGHT_FLOORS_MASK 7

typedef struct {
    u8 x;
    u8 y;
} Point;

u8 bit(u8 number)
{
    return (u8)(1 << number);
}

/* --- the random number generator ($F4C9): a 16-bit shift register --- */
u8 next_random(void)
{
    u8 mixed = RAM(RANDOM_HIGH) ^ RAM(RANDOM_LOW);
    u8 carry_in = (mixed >> 6) & 1;
    u8 low = RAM(RANDOM_LOW);
    u8 high = RAM(RANDOM_HIGH);
    RAM(RANDOM_LOW) = (u8)((low << 1) | carry_in);
    RAM(RANDOM_HIGH) = (u8)((high << 1) | (low >> 7));
    return RAM(RANDOM_LOW);
}

/* A floor's place in the tables that differ by game: game 9's follow the other games'. */
u8 floor_index(u8 floor)
{
    return RAM(GAME_NUMBER) == GAME_9 ? floor + FLOOR_COUNT : floor;
}

u8 door_locked(u8 floor, u8 door)
{
    if (RAM(GAME_NUMBER) < LOCKS_FROM_GAME) {
        return 0;
    }
    return (locked_doors[floor_index(floor)] & bit(door)) != 0;
}

static u8 in_players_room(u8 monster)
{
    u8 room;
    if (RAM(MONSTER_FLOOR + monster) != RAM(FLOOR)) {
        return 0;
    }
    room = RAM(MONSTER_ROOM + monster);
    return room == RAM(ROOM) || room == RAM(ROOM_BEYOND);
}

static u8 ignores_scepter(u8 monster)
{
    return monster == GHOST && RAM(GAME_NUMBER) >= FAST_FROM_GAME;
}

/* Does a chasing monster step on this frame? ($FA6F) */
static u8 chase_step(u8 monster, u8 phase)
{
    const u8 *speeds = RAM(GAME_NUMBER) >= FAST_FROM_GAME ? monster_speed_fast : monster_speed;
    return (speeds[monster] & bit(phase)) != 0;
}

/* The point near the player a chasing monster heads for. The offsets are subtracted as plain bytes, and
   the player's own x or y stands in whenever that borrows. */
static void chase_point(u8 monster, Point *target)
{
    s16 x = (s16)RAM(POS_X) - chase_offset_x[monster];
    s16 y = (s16)RAM(POS_Y) - chase_offset_y[monster];
    target->x = x < 0 ? RAM(POS_X) : (u8)x;
    target->y = y < 0 ? RAM(POS_Y) : (u8)y;
}

static void waypoint(u8 route, u8 floor, Point *point)
{
    u8 kind = (route & 0x3F) >> 4;
    u8 index = waypoint_start[kind] + (route & 0x0F);
    point->x = waypoint_x_of(floor, index);
    point->y = waypoint_y_of(floor, index);
}

/* The waypoint of the monster's plan; if it's already there, mark it arrived and stand still. */
static u8 route_point(u8 monster, Point *target)
{
    waypoint(RAM(MONSTER_ROUTE + monster), RAM(MONSTER_FLOOR + monster), target);
    if (RAM(MONSTER_X + monster) == target->x && RAM(MONSTER_Y + monster) == target->y) {
        RAM(ARRIVED) |= bit(monster);
        return 0;
    }
    return 1;
}

/* Where the monster steps towards this frame; 0 if it stands still. */
static u8 choose_target(u8 monster, u8 phase, u8 wander_step, Point *target)
{
    u8 moving;
    if (in_players_room(monster)) {
        u8 dying = RAM(DEATH_TIMER) != 0;
        u8 scepter = RAM(CARRIED) == SCEPTER && !ignores_scepter(monster);
        RAM(MONSTERS_HERE) += 1;
        if (dying == 0 && scepter == 0) {   /* (not "!dying && !scepter": the compiler gets that wrong) */
            if (!chase_step(monster, phase)) {
                return 0;
            }
            chase_point(monster, target);
            return 1;
        }
        moving = wander_step;
    } else if (RAM(FOLLOWING) & bit(monster)) {
        moving = chase_step(monster, phase);
    } else {
        moving = wander_step;
    }
    if (!moving) {
        return 0;
    }
    return route_point(monster, target);
}

/* One unit towards the target in x and in y at once ($F983). A step left that would reach x = 0 is undone
   by the code's shape. */
static void step_towards(u8 monster, const Point *target)
{
    u8 x = RAM(MONSTER_X + monster);
    u8 y = RAM(MONSTER_Y + monster);
    if (x > target->x) {
        x -= 1;
        if (x == 0) {
            x += 1;
        }
    } else if (x < target->x) {
        x += 1;
    }
    if (y > target->y) {
        y -= 1;
    } else if (y < target->y) {
        y += 1;
    }
    RAM(MONSTER_X + monster) = x;
    RAM(MONSTER_Y + monster) = y;
}

/* --- arriving at a waypoint ($F9A6) --- */
static u8 may_pass_locks(u8 monster)
{
    return monster == GHOST || RAM(GAME_NUMBER) == GAME_9;
}

/* Set a plan to leave the room this way, if the monster may; return whether it did ($FA1F). */
static u8 try_direction(u8 monster, u8 direction)
{
    u8 room = RAM(MONSTER_ROOM + monster);
    u8 floor = RAM(MONSTER_FLOOR + monster);
    u8 neighbour = door_id(floor, room, direction);
    u8 kind;
    u8 target;
    if (neighbour == WALL) {
        return 0;
    }
    if (neighbour & EDGE) {
        u8 index = floor_index(floor);
        if (!(rooms_with_stairs[index] & bit(room))) {
            return 0;
        }
        kind = (stairs_go_up[index] & bit(room)) ? KIND_STAIRS_UP : KIND_STAIRS_DOWN;
        target = room;
    } else {
        if (door_locked(floor, neighbour) && !may_pass_locks(monster)) {
            return 0;
        }
        kind = KIND_DOOR;
        target = neighbour;
    }
    RAM(MONSTER_ROUTE + monster) = (u8)((direction << 6) | (kind << 4) | target);
    return 1;
}

/* At a room centre: try directions in turn from a random one, skipping the way it came; if none will do,
   go back the way it came ($F9F3). */
static void pick_direction(u8 monster)
{
    u8 came_from = (RAM(MONSTER_ROUTE + monster) >> 6) ^ 1;
    u8 first = RAM(RANDOM_LOW) & 3;
    u8 direction = first;
    while (1) {
        if (direction != came_from && try_direction(monster, direction)) {
            return;
        }
        direction = (direction + 1) & 3;
        if (direction == first) {
            try_direction(monster, came_from);
            return;
        }
    }
}

static void new_plan(u8 monster)
{
    u8 route = RAM(MONSTER_ROUTE + monster);
    u8 kind = (route & 0x30) >> 4;
    u8 direction_bits = route & 0xC0;
    u8 room = RAM(MONSTER_ROOM + monster);
    if (kind == KIND_CENTRE) {
        pick_direction(monster);
    } else if (kind == KIND_DOOR) {
        u8 step = room_step[direction_bits >> 6];
        RAM(MONSTER_ROOM + monster) = (u8)(room + step);
        RAM(MONSTER_ROUTE + monster) = RAM(MONSTER_ROOM + monster) | direction_bits;
    } else {
        /* up or down the stairs; the direction flips, so the stairs count as "the way it came" */
        RAM(MONSTER_FLOOR + monster) += kind == KIND_STAIRS_UP ? 1 : 0xFF;
        RAM(MONSTER_ROUTE + monster) = room | (direction_bits ^ 0x40);
    }
}

/* Only the lowest-numbered arrived monster gets a new plan this frame; the others wait their turn. */
static void handle_one_arrival(void)
{
    u8 monster;
    for (monster = 0; monster <= RAM(LAST_MONSTER); monster++) {
        if (RAM(ARRIVED) & bit(monster)) {
            RAM(ARRIVED) ^= bit(monster);
            new_plan(monster);
            return;
        }
    }
}

/* --- one frame of monster movement ($F8EC): not while the player dies --- */
void move_monsters(void)
{
    u8 phase = RAM(CLOCK) & 7;
    u8 wander_step = WANDER_FRAMES & bit(phase);
    s8 monster;
    Point target;
    RAM(MONSTERS_HERE) = 0;
    for (monster = (s8)RAM(LAST_MONSTER); monster >= 0; monster--) {
        if (choose_target((u8)monster, phase, wander_step, &target)) {
            step_towards((u8)monster, &target);
        }
    }
    handle_one_arrival();
}

/* --- following the player (games 6-9) --- */
/* Give every monster on the player's floor in `room` the plan, and mark them chasing ($FB47); with
   `only_ghost`, just the ghost. */
static void send_followers(u8 room, u8 plan, u8 only_ghost)
{
    s8 monster;
    RAM(FOLLOWING) = 0;
    for (monster = only_ghost ? GHOST : (s8)RAM(LAST_MONSTER); monster >= 0; monster--) {
        u8 same_floor = RAM(MONSTER_FLOOR + monster) == RAM(FLOOR);
        if (same_floor && RAM(MONSTER_ROOM + monster) == room) {
            RAM(MONSTER_ROUTE + monster) = plan;
            RAM(FOLLOWING) |= bit((u8)monster);
        }
        if (only_ghost) {
            return;
        }
    }
}

/* The player just went through a door out of `room`: monsters there follow ($FCD8). Through a locked
   door only the ghost follows. */
void follow_through_door(u8 room, u8 direction)
{
    u8 door;
    u8 plan;
    if (RAM(GAME_NUMBER) < FOLLOW_FROM_GAME) {
        return;
    }
    door = door_id(RAM(FLOOR), room, direction);
    plan = (u8)((direction << 6) | (KIND_DOOR << 4) | door);
    send_followers(room, plan, door_locked(RAM(FLOOR), door));
}

/* The player just took the stairs out of `room`: monsters there follow ($FB2B). */
void follow_up_stairs(u8 room, u8 stairs_byte)
{
    u8 edge = stairs_byte & 3;
    u8 going_up = (stairs_byte >> 2) & 1;
    if (RAM(GAME_NUMBER) < FOLLOW_FROM_GAME) {
        return;
    }
    send_followers(room, (u8)((edge << 6) | ((KIND_STAIRS_DOWN + going_up) << 4) | room), 0);
}

/* --- scattering ($F0E7): all five monsters to random room centres, never the player's --- */
static u8 random_floor(void)
{
    u8 mask = FLOOR_COUNT <= 4 ? FOUR_FLOORS_MASK : EIGHT_FLOORS_MASK;
    u8 floor = next_random() & mask;
    while (floor >= FLOOR_COUNT) {
        floor = next_random() & mask;
    }
    return floor;
}

static u8 room_mod(u8 number)
{
    while (number >= ROOM_COUNT) {
        number -= ROOM_COUNT;
    }
    return number;
}

void scatter(void)
{
    u8 base = next_random() & 7;
    s8 monster;
    while (base >= ROOM_COUNT) {
        base = next_random() & 7;
    }
    for (monster = 4; monster >= 0; monster--) {
        u8 floor = random_floor();
        u8 room = room_mod((u8)monster + base);
        RAM(MONSTER_FLOOR + monster) = floor;
        if (room == RAM(ROOM) && floor == RAM(FLOOR)) {
            room = room_mod(5 + base);
        }
        RAM(MONSTER_ROOM + monster) = room;
        RAM(MONSTER_ROUTE + monster) = room;
        RAM(MONSTER_X + monster) = waypoint_x_of(floor, room);
        RAM(MONSTER_Y + monster) = waypoint_y_of(floor, room);
    }
}
