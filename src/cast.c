/* The cast on the screen: the eyes, the items, the monsters and the stairs as sprites, each where the game
   has it and only when the original would show it (the remaster's game/visibility.py: the original's
   rules), drawn with the pictures the remaster's SNES look draws them with (tools/make_pictures.py).

   Written for this compiler's cost - a scanline of the frame for every few statements: arithmetic is
   shifts and adds; the sprite table is written directly; and each kind of thing has sprite entries of its
   own, so the items and the stairs, which don't move, are only looked at every fourth frame. */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "mansion.h"
#include "cast.h"

/* The view (picture.c): where a floor place lands on the screen. */
#define VIEW_X 8
#define VIEW_Y 32
#define VIEW_LINES 80
#define VIEW_HEIGHT 160
#define EYES_HEIGHT 3            /* each kind's height on the floor, in lines (the look's HEIGHTS) */
#define ITEM_HEIGHT 8
#define MONSTER_HEIGHT 10
#define STAIRS_HEIGHT 17
#define ITEM_REACH 0x11          /* items show while their light distance is under this */
#define FIRST_LOCKED_GAME 2      /* the master key never shows in games 1-2 */
#define BLINK_EVERY 200          /* the eyes blink for 6 frames in every 200 */
#define BLINK_FRAMES 6
#define HAND_OFFSET 10           /* floor units from the eyes to the hand holding the match... */
#define HAND_DROP 2              /* ...and below them */
#define ANIMATION_SHIFT 3        /* a picture's frame lasts 8 frames: the frame count shifted by this */
#define WALK_MEMORY 8            /* a monster that hasn't moved in this many frames is standing still */
#define MONSTERS 5
#define IN_FRONT 3               /* sprites above both layers */
#define HIDDEN_Y 240             /* a sprite's y below the picture: not drawn */
#define FACING_DOWN 0
#define FACING_LEFT 1
#define FACING_UP 2
#define FACING_RIGHT 3
/* The sprite table's entries, by kind: the eyes (with the hood and the hand), the monsters, the items,
   the stairs. Each kind hides the entries it used last time and doesn't now. */
#define EYES_SLOTS 0
#define MONSTER_SLOTS 4
#define ITEM_SLOTS 20
#define STAIRS_SLOTS 26
#define SLOTS_END 28
#define ITEMS_ON_FRAME 1         /* the items are drawn on frames 1 of 4, the stairs on frames 3 */
#define STAIRS_ON_FRAME 3

/* What cast_put (src/fast.asm) takes: a picture's place and blocks; it writes the entries from cast_slot. */
u8 cast_slot;                                /* the next sprite entry to write */
u8 place_left;
u8 place_top;
u8 place_wide;
u8 place_high;
u8 place_tile;
u8 place_attr;
u8 place_mirrored;
u8 put_rows_left;                            /* cast_put's own working bytes */
u8 put_blocks_left;
u8 put_x;
u8 put_y;
u8 put_tile;
u8 put_row_tile;
void cast_put(void);
#define slot cast_slot
static u8 eyes_used;                         /* entries each kind used last time */
static u8 monsters_used;
static u8 items_used;
static u8 stairs_used;
static u8 monster_facing[MONSTERS];
static u8 monster_still[MONSTERS];           /* frames since it last moved */
static u8 monster_last_x[MONSTERS];
static u8 monster_last_y[MONSTERS];
static u8 hand_side = FACING_RIGHT;          /* the match's hand stays on the side last looked to */
static u8 blink_clock;                       /* counts the frames to the next blink */

#define TIMES_3_HALVED(value) ((((value) << 1) + (value)) >> 1)
#define DIFFERENCE(one, other) ((one) > (other) ? (one) - (other) : (other) - (one))
/* A floor place's middle on the screen: 1.5 pixels a unit across, 2 a line up; the line is the floor's
   y less the view's bottom line. */
#define SCREEN_X(x) (VIEW_X + TIMES_3_HALVED((s16)(x) + 4))
#define SCREEN_Y(y, height) (VIEW_Y + ((VIEW_LINES - ((s16)(y) - (s16)view_bottom)) << 1) - (height))

static u8 view_bottom;                       /* the view's bottom line, this frame */

/* A picture on the screen, its middle at (centre_x, centre_y), mirrored if asked: a sprite entry per
   16 x 16 block, written by cast_put (src/fast.asm). Nothing is drawn outside the view's lines; nothing
   ever reaches past the screen's left edge (the floor starts 8 pixels in), so a sprite's x fits a byte.
   The entry's fourth byte: flips, priority, palette, and the tile number's ninth bit. */
static void place(u8 picture, s16 centre_x, s16 centre_y, u8 mirrored)
{
    u8 high = cast_high[picture];
    u16 tile = cast_tile[picture];
    s16 top = centre_y - (high << 3);
    if (top + (high << 4) <= VIEW_Y || top >= VIEW_Y + VIEW_HEIGHT) {
        return;
    }
    place_wide = cast_wide[picture];
    place_high = high;
    place_left = (u8)(centre_x - (place_wide << 3));
    place_top = (u8)top;
    place_tile = (u8)tile;
    place_attr = (u8)((mirrored ? 0x40 : 0) | (IN_FRONT << 4) | (cast_palette[picture] << 1) | (tile >> 8));
    place_mirrored = mirrored;
    cast_put();
}

/* Hide the entries a kind used last time beyond the ones it used now. */
static void hide_rest(u8 used_before)
{
    while (used_before > slot) {
        used_before--;
        oamMemory[(used_before << 2) + 1] = HIDDEN_Y;
    }
}

/* The frame of a picture with 1, 2 or 4 frames, 8 game frames each. */
static u8 animation_frame(u8 frames)
{
    return (u8)(frame_count >> ANIMATION_SHIFT) & (frames - 1);
}

/* --- the eyes, and the hand with the match --- */
static u8 eyes_picture(void)
{
    u8 stick = RAM(JOYSTICK);
    if (++blink_clock >= BLINK_EVERY) {
        blink_clock = 0;
    }
    if (blink_clock < BLINK_FRAMES && RAM(GAME_STATE) == PLAYING) {
        return CAST_EYES_BLINK;
    }
    if (stick & STICK_LEFT) {
        return CAST_EYES_LEFT;
    }
    if (stick & STICK_RIGHT) {
        return CAST_EYES_RIGHT;
    }
    if (stick & STICK_UP) {
        return CAST_EYES_UP;
    }
    if (stick & STICK_DOWN) {
        return CAST_EYES_DOWN;
    }
    return CAST_EYES_CENTRE;
}

static void draw_eyes(void)
{
    u8 x = RAM(POS_X);
    u8 y = RAM(POS_Y);
    u8 stick = RAM(JOYSTICK);
    s16 centre_x = SCREEN_X(x);
    s16 centre_y = SCREEN_Y(y, EYES_HEIGHT);
    slot = EYES_SLOTS;
    place(eyes_picture(), centre_x, centre_y, 0);
    if (RAM(FLAGS) & MATCH_LIT) {
        u8 left_handed;
        if (stick & STICK_LEFT) {
            hand_side = FACING_LEFT;
        } else if (stick & STICK_RIGHT) {
            hand_side = FACING_RIGHT;
        }
        left_handed = hand_side == FACING_LEFT;
        place(CAST_HOOD_RIGHT, centre_x, centre_y, left_handed);
        place(CAST_MATCH_HAND_RIGHT + animation_frame(CAST_MATCH_HAND_RIGHT_FRAMES),
              left_handed ? centre_x - TIMES_3_HALVED(HAND_OFFSET) : centre_x + TIMES_3_HALVED(HAND_OFFSET),
              centre_y + (HAND_DROP << 1), left_handed);
    }
    hide_rest(eyes_used);
    eyes_used = slot;
}

/* --- the items (with a match lit) --- */
static u8 light_distance(u8 x, u8 y)
{
    u8 player_x = RAM(POS_X);
    u8 player_y = RAM(POS_Y);
    u8 across = DIFFERENCE(player_x, x);
    u8 up_down = DIFFERENCE(player_y, y);
    return up_down >= across ? (u8)(up_down + (across >> 1)) : (u8)(across + (up_down >> 1));
}

static u8 item_visible(u8 item)
{
    if (RAM(ITEM_FLOOR + item) != RAM(FLOOR) || item == RAM(CARRIED)) {
        return 0;
    }
    if (item == KEY && RAM(GAME_NUMBER) < FIRST_LOCKED_GAME) {
        return 0;
    }
    if (item >= URN && RAM(URN_SHAPES + item - URN) == JOINED) {
        return 0;
    }
    if (lights_on) {
        return 1;
    }
    return light_distance(RAM(ITEM_X + item), RAM(ITEM_Y + item)) < ITEM_REACH;
}

static void draw_items(void)
{
    u8 item;
    u8 lit = RAM(FLAGS) & MATCH_LIT;
    slot = ITEM_SLOTS;
    if (lights_on) {
        lit = 1;
    }
    if (lit) {
        for (item = 0; item < 5; item++) {
            u8 picture;
            if (!item_visible(item)) {
                continue;
            }
            if (item == KEY) {
                picture = CAST_KEY;
            } else if (item == SCEPTER) {
                picture = CAST_SCEPTER;
            } else {   /* an urn piece's shape, 2-8: 4 frames a shape */
                picture = CAST_URN2 + ((RAM(URN_SHAPES + item - URN) - 2) << 2) + animation_frame(4);
            }
            place(picture, SCREEN_X(RAM(ITEM_X + item)), SCREEN_Y(RAM(ITEM_Y + item), ITEM_HEIGHT), 0);
        }
    }
    hide_rest(items_used);
    items_used = slot;
}

/* --- the monsters (on the player's floor) --- */
static u8 monster_visible(u8 monster)
{
    u8 room;
    if (RAM(GAME_NUMBER) == 0 || RAM(DEATH_TIMER) || lights_on) {
        return 1;
    }
    room = RAM(MONSTER_ROOM + monster);
    return room == RAM(ROOM) || room == RAM(ROOM_BEYOND);
}

/* Which way a monster faces: the way it last moved. */
static void watch_facing(u8 monster)
{
    u8 x = RAM(MONSTER_X + monster);
    u8 y = RAM(MONSTER_Y + monster);
    u8 last_x = monster_last_x[monster];
    u8 last_y = monster_last_y[monster];
    u8 across = DIFFERENCE(x, last_x);
    u8 up_down = DIFFERENCE(y, last_y);
    if (across == 0 && up_down == 0) {
        if (monster_still[monster] < WALK_MEMORY) {
            monster_still[monster]++;
        }
        return;
    }
    monster_still[monster] = 0;
    if (across >= up_down) {
        monster_facing[monster] = x > last_x ? FACING_RIGHT : FACING_LEFT;
    } else {
        monster_facing[monster] = y > last_y ? FACING_UP : FACING_DOWN;
    }
    monster_last_x[monster] = x;
    monster_last_y[monster] = y;
}

/* A monster's picture facing its way: the ghost and the bat have no right-facing pictures, so their
   left ones serve, mirrored. */
static void draw_monster(u8 monster)
{
    u8 facing = monster_facing[monster];
    u8 mirrored = 0;
    u8 picture;
    if (monster == GHOST) {
        picture = facing == FACING_UP ? CAST_GHOST_UP : facing == FACING_DOWN ? CAST_GHOST_DOWN : CAST_GHOST_LEFT;
        picture += animation_frame(CAST_GHOST_DOWN_FRAMES);
        mirrored = facing == FACING_RIGHT;
    } else if (monster == BAT) {
        picture = facing == FACING_UP ? CAST_BAT_UP : facing == FACING_DOWN ? CAST_BAT_DOWN : CAST_BAT_LEFT;
        picture += animation_frame(CAST_BAT_DOWN_FRAMES);
        mirrored = facing == FACING_RIGHT;
    } else {   /* tarantula 2, 3 or 4's pictures: 4 ways of 2 frames each; legs still when standing */
        picture = CAST_TARANTULA2_DOWN + ((monster - 2) << 3) + (facing << 1);
        if (monster_still[monster] < WALK_MEMORY) {
            picture += animation_frame(CAST_TARANTULA2_DOWN_FRAMES);
        }
    }
    place(picture, SCREEN_X(RAM(MONSTER_X + monster)), SCREEN_Y(RAM(MONSTER_Y + monster), MONSTER_HEIGHT),
          mirrored);
}

static void draw_monsters(void)
{
    u8 monster;
    u8 last = RAM(LAST_MONSTER);
    slot = MONSTER_SLOTS;
    for (monster = 0; monster <= last; monster++) {
        if (RAM(MONSTER_FLOOR + monster) != RAM(FLOOR)) {
            continue;
        }
        watch_facing(monster);
        if (monster_visible(monster)) {
            draw_monster(monster);
        }
    }
    hide_rest(monsters_used);
    monsters_used = slot;
}

/* --- the stairs (with a match lit) --- */
static void draw_stairs(void)
{
    u8 here = RAM(STAIRS) & NO_STAIRS;
    u8 floor = RAM(FLOOR);
    u8 lit = RAM(FLAGS) & MATCH_LIT;
    slot = STAIRS_SLOTS;
    if (lights_on) {
        lit = 1;
    }
    if (lit && here != NO_STAIRS) {
        u8 x = stairs_x[(floor << 2) + (floor << 1) + RAM(ROOM)];   /* (6 a floor) */
        u8 y = stairs_y[(floor << 2) + (here & 3)];                  /* (4 a floor) */
        place((here & GOES_UP) ? CAST_STAIRS_UP : CAST_STAIRS_DOWN, SCREEN_X(x), SCREEN_Y(y, STAIRS_HEIGHT), 0);
    }
    hide_rest(stairs_used);
    stairs_used = slot;
}

/* Everyone on the screen this frame: the eyes and the monsters every frame, the items and the stairs
   every fourth (they don't move; their entries stay). */
void draw_cast(void)
{
    u8 phase = (u8)frame_count & 3;
    view_bottom = (u8)(RAM(POS_Y) - RAM(EYES_LINE));
    draw_eyes();
    if (RAM(GAME_STATE) & NO_LOGIC) {   /* select, game over: the eyes only */
        slot = MONSTER_SLOTS;
        hide_rest(monsters_used);
        monsters_used = slot;
        slot = ITEM_SLOTS;
        hide_rest(items_used);
        items_used = slot;
        slot = STAIRS_SLOTS;
        hide_rest(stairs_used);
        stairs_used = slot;
        oamUpdate();
        return;
    }
    draw_monsters();
    if (phase == ITEMS_ON_FRAME) {
        draw_items();
    } else if (phase == STAIRS_ON_FRAME) {
        draw_stairs();
    }
    oamUpdate();   /* the table to the SNES (the library's own sprite calls would ask for this themselves) */
}

void set_up_cast(void)
{
    u16 index;
    oamInit();
    for (index = 512; index < 512 + 32; index++) {   /* every sprite small, and on the screen's left side */
        oamMemory[index] = 0;
    }
    eyes_used = EYES_SLOTS;
    monsters_used = MONSTER_SLOTS;
    items_used = ITEM_SLOTS;
    stairs_used = STAIRS_SLOTS;
}
