/* What's drawn each frame besides the eyes and the walls: one item, monster or the stairs, in turn (the
   spec, "What's drawn each frame"). Which one matters beyond looks: touching is tested only against it. */
#include "state.h"
#include "mansion.h"
#include "engine.h"

#define ITEM_REACH 0x11       /* items show while their light distance is under this */
#define FIRST_LOCKED_GAME 2   /* game 3: the first with locks, and a master key that shows */
#define SPRITE_ROW_BYTES 8
#define MONSTER_SECOND_FRAME 10
#define SHAPES_PAGE 0xFE      /* the high byte of every picture's address on the 2600 */
#define ROUNDS_TO_HANG 3      /* times round every slot without finding the one it started from */

/* The screen line a floor y is drawn on ($F4DB). */
u8 line_of(u8 y)
{
    return (u8)(y + RAM(EYES_LINE) - RAM(POS_Y));
}

/* Does a sprite whose bottom row is on this line show at all? ($F56D) */
u8 on_screen(u8 line)
{
    return line < VIEW_LINES || line >= LAST_LINE_BELOW;
}

/* Game over and select: COLOUR_CYCLE counts every 256 frames, and the colours drift with it ($F3E8). */
static void drift_colours(void)
{
    if (!(RAM(COLOUR_CYCLE) & ATTRACT)) {
        return;
    }
    if (RAM(CLOCK) == 0) {
        RAM(COLOUR_CYCLE) += 1;
    }
    RAM(COLOUR_CYCLE) |= ATTRACT;
}

/* The drawing reads these bytes; nothing found leaves no picture ($F4FE). */
static void remember(const Sprite *sprite)
{
    if (!sprite->height) {
        RAM(SPRITE_X) = 0;
        RAM(SPRITE_HEIGHT) = 0;
        return;
    }
    RAM(SPRITE_X) = sprite->x;
    RAM(SPRITE_LINE) = sprite->line;
    RAM(SPRITE_HEIGHT) = sprite->height;
    RAM(SPRITE_POINTER) = sprite->picture;
    RAM(SPRITE_POINTER + 1) = SHAPES_PAGE;
}

/* On RESET's frame and while won the game chooses nothing, and the drawing draws again whatever its bytes
   still hold: last frame's sprite, where it was, at normal width ($F2D8). */
static void leftover_sprite(Sprite *sprite)
{
    sprite->height = RAM(SPRITE_HEIGHT);
    sprite->x = RAM(SPRITE_X);
    sprite->line = RAM(SPRITE_LINE);
    sprite->picture = RAM(SPRITE_POINTER);
    sprite->wide = 0;
}

/* --- items --- */
/* Where an item's picture is in the shapes page: shape * 8 + 8, in one byte, plus the carry out of the
   shifts ($F4E2) - which only matters for a joined piece (shape $FF), whose "picture" is at 1. */
static u8 item_picture(u8 item)
{
    u8 shape = item < URN ? item : RAM(URN_SHAPES + item - URN);
    u16 shifted = (u16)shape << 3;
    return (u8)(shifted + SPRITE_ROW_BYTES + ((shifted >> 8) & 1));
}

static void item_sprite(u8 item, Sprite *sprite)
{
    sprite->x = RAM(ITEM_X + item);
    sprite->line = line_of(RAM(ITEM_Y + item));
    sprite->picture = item_picture(item);
    sprite->height = SPRITE_HEIGHT_ITEM;
    sprite->wide = 0;
}

/* The item being put down, drawn where the search is trying it ($F2ED, $F526): the place on the screen the
   search worked out last frame, before the player moved. */
static void dropped_item(Sprite *sprite)
{
    u8 item = RAM(DROPPED);
    RAM(ITEM_FLOOR + item) = RAM(FLOOR);
    RAM(ITEM_SHOWN) = item;
    sprite->x = RAM(SPRITE_X);
    sprite->line = RAM(SPRITE_LINE);
    sprite->picture = item_picture(item);
    sprite->height = SPRITE_HEIGHT_ITEM;
    sprite->wide = 0;
}

static u8 difference(u8 one, u8 other)
{
    return one > other ? one - other : other - one;
}

/* The game's cheap distance: the larger difference plus half the smaller ($F53D). */
static u8 light_distance(u8 item)
{
    u8 across = difference(RAM(POS_X), RAM(ITEM_X + item));
    u8 up_down = difference(RAM(POS_Y), RAM(ITEM_Y + item));
    if (up_down >= across) {
        return (u8)(up_down + (across >> 1));
    }
    return (u8)(across + (up_down >> 1));
}

static u8 item_may_show(u8 item)
{
    if (item == RAM(CARRIED)) {
        return 0;
    }
    if (item >= URN && (RAM(URN_SHAPES + item - URN) & 0x80)) {
        return 0;
    }
    if (RAM(GAME_NUMBER) < FIRST_LOCKED_GAME && item == KEY) {
        return 0;
    }
    if (RAM(ITEM_FLOOR + item) != RAM(FLOOR)) {
        return 0;
    }
    return light_distance(item) < ITEM_REACH && on_screen(line_of(RAM(ITEM_Y + item)));
}

/* The next item in turn that may show, counting down from the last one shown ($F4F1). */
static u8 next_item(Sprite *sprite)
{
    u8 last = RAM(ITEM_SHOWN);
    u8 item = last;
    while (1) {
        item = item > 0 ? item - 1 : 4;
        if (item_may_show(item)) {
            RAM(ITEM_SHOWN) = item;
            item_sprite(item, sprite);
            return 1;
        }
        if (item == last) {
            return 0;
        }
    }
}

/* --- monsters and the stairs --- */
/* Is this monster one that may be drawn, wherever it is on the screen? ($F59E) */
static u8 monster_rules_allow(u8 monster)
{
    u8 room;
    if (RAM(MONSTER_FLOOR + monster) != RAM(FLOOR)) {
        return 0;
    }
    if (RAM(GAME_NUMBER) == 0 || RAM(DEATH_TIMER)) {
        return 1;
    }
    room = RAM(MONSTER_ROOM + monster);
    return RAM(MONSTERS_HERE) != 0 && (room == RAM(ROOM) || room == RAM(ROOM_BEYOND));
}

static void monster_sprite(u8 monster, Sprite *sprite)
{
    u8 first = MONSTER_SHAPES + monster_frames[monster];
    sprite->x = RAM(MONSTER_X + monster);
    sprite->line = line_of(RAM(MONSTER_Y + monster));
    sprite->picture = (RAM(RANDOM_LOW) & 0x40) ? first : first + MONSTER_SECOND_FRAME;
    sprite->height = SPRITE_HEIGHT_MONSTER;
    sprite->wide = 0;
}

/* This room's stairs: the picture by edge and direction, drawn at the edge's line ($F5E7), double width. */
static void stairs_sprite(Sprite *sprite)
{
    u8 here = RAM(STAIRS) & NO_STAIRS;
    u8 picture = here >= GOES_UP ? (here & 3) ^ 1 : here;
    u8 floor = RAM(FLOOR);
    sprite->x = stairs_x[floor * STAIRS_X_SIZE + RAM(ROOM)];
    sprite->line = line_of(stairs_y[floor * STAIRS_Y_SIZE + (here & 3)]);
    sprite->picture = STAIRS_SHAPES + picture * SPRITE_HEIGHT_STAIRS;
    sprite->height = SPRITE_HEIGHT_STAIRS;
    sprite->wide = 1;
}

/* The next monster in turn that may show; with a match lit, the stairs take the slot after the last
   monster ($F57D). Where the original crashes here (the spec, "A crash in the original") this just goes on;
   where it would go round for ever, nothing is drawn. */
static u8 next_monster(Sprite *sprite)
{
    u8 last = RAM(MONSTER_SHOWN);
    s8 slot = (s8)last;
    u8 rounds = ROUNDS_TO_HANG * (RAM(LAST_MONSTER) + 2);
    while (rounds--) {
        slot -= 1;
        if (slot < 0) {
            slot = (s8)RAM(LAST_MONSTER);
            if (RAM(FLAGS) & MATCH_LIT) {
                slot += 1;
                if ((RAM(STAIRS) & NO_STAIRS) != NO_STAIRS) {
                    RAM(MONSTER_SHOWN) = (u8)slot;
                    stairs_sprite(sprite);
                    return 1;
                }
                if ((u8)slot == last) {
                    return 0;
                }
                continue;
            }
        }
        if (monster_rules_allow((u8)slot) && on_screen(line_of(RAM(MONSTER_Y + slot)))) {
            RAM(MONSTER_SHOWN) = (u8)slot;
            monster_sprite((u8)slot, sprite);
            return 1;
        }
        if ((u8)slot == last) {
            return 0;
        }
    }
    return 0;
}

/* The one item, monster or stairs drawn this frame, and the turn bytes it moves on ($F2B7).
   height 0: none. */
void choose_sprite(Sprite *sprite)
{
    u8 mode = RAM(GAME_STATE);
    u8 found;
    sprite->height = 0;
    if (mode == JUST_RESET || (mode & WON_BIT)) {
        if ((mode & WON_BIT) && RAM(CLOCK) == 0) {
            select_mode();
        }
        drift_colours();
        leftover_sprite(sprite);
        return;
    }
    if (RAM(DEATH_TIMER)) {
        found = next_monster(sprite);
    } else if (RAM(DROP_TRIES)) {
        dropped_item(sprite);
        found = 1;
    } else if ((RAM(FLAGS) & MATCH_LIT) && !(RAM(FLAGS) & MONSTER_TURN)) {
        found = next_item(sprite);
    } else {
        found = next_monster(sprite);
    }
    if (!found) {
        sprite->height = 0;
    }
    remember(sprite);
    drift_colours();
}
