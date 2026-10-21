/* The remaster's hints and notes (its game/hints.py; the NES game's hints.s), in the band below the view:
   X during play says what you need next and which way - the nearest piece of the urn (up or down the
   stairs, or which way across the floor), how to take it once you're in its room, and with the whole urn
   in hand, the way out. Notes come by themselves: when the urn becomes whole, when taking something puts
   down what you held, and when the lights cheat goes on or off. A note shows for a while, then the
   floor's name comes back (status.c). Nothing here touches the game's state; it only reads it. */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "mansion.h"

#define HINT_FRAMES 360              /* a hint, or a note that matters, shows this long... */
#define NOTE_FRAMES 120              /* ...a small note this long */
#define LINE_LETTERS 31              /* a line: up to 30 letters, and its end */
#define LINES 3
#define ROOMS 6
#define FRONT_DOOR_ROOM 2            /* on the front door's floor: walk out of its right edge */
#define URN_PIECES 3
#define LAST_SHAPE 8
#define OTHER_FLOOR 1000             /* another floor counts this far, against distances across one */
#define NO_ITEM 0xFF

static char lines[LINES][LINE_LETTERS];
static u16 note_left;                /* frames the note on show has left */
static u8 was_carried;
static u8 was_whole;
static u8 was_lights;
static u8 was_shapes;               /* the urn's shapes, folded together: a change wakes the notes */
static u8 hint_asked;
static const u8 shape_pieces[LAST_SHAPE + 1] = {0, 0, 1, 1, 1, 2, 2, 2, 3};

/* --- writing the lines ------------------------------------------------------------------------------- */
static void clear_lines(void)
{
    u8 line;
    for (line = 0; line < LINES; line++) {
        lines[line][0] = 0;
    }
}

/* `text` onto the end of a line. */
static void add(u8 line, const char *text)
{
    char *end = lines[line];
    while (*end) {
        end++;
    }
    while (*text && end < lines[line] + LINE_LETTERS - 1) {
        *end++ = *text++;
    }
    *end = 0;
}

static void add_digit(u8 line, u8 digit)
{
    char text[2];
    text[0] = '0' + digit;
    text[1] = 0;
    add(line, text);
}

static void show(u16 frames)
{
    status_note(lines[0], lines[1], lines[2]);
    note_left = frames;
}

/* --- what you hold, and where the urn is ------------------------------------------------------------- */
static u8 holding_whole_urn(void)
{
    u8 carried = RAM(CARRIED);
    return carried >= URN && carried != NOTHING && RAM(URN_SHAPES + carried - URN) == WHOLE_URN;
}

static u8 pieces_of(u8 item)
{
    u8 shape = RAM(URN_SHAPES + item - URN);
    return shape <= LAST_SHAPE ? shape_pieces[shape] : 0;
}

static u8 difference(u8 one, u8 other)
{
    return one > other ? one - other : other - one;
}

/* The nearest piece, pieces or whole urn that isn't in your hands (another floor is always further
   than anywhere on this one); NO_ITEM if there's none. */
static u8 nearest_urn(void)
{
    u8 item;
    u8 nearest = NO_ITEM;
    u16 best = 0xFFFF;
    for (item = URN; item < URN + URN_PIECES; item++) {
        u16 distance;
        u8 floor = RAM(ITEM_FLOOR + item);
        if (RAM(URN_SHAPES + item - URN) == JOINED || item == RAM(CARRIED)) {
            continue;
        }
        distance = (u16)difference(floor, RAM(FLOOR)) * OTHER_FLOOR
                   + difference(RAM(ITEM_X + item), RAM(POS_X)) + difference(RAM(ITEM_Y + item), RAM(POS_Y));
        if (distance < best) {
            best = distance;
            nearest = item;
        }
    }
    return nearest;
}

/* The room whose middle is nearest a place on a floor (the room's waypoint, as the remaster). */
static u8 room_at(u8 floor, u8 x, u8 y)
{
    u8 room;
    u8 nearest = 0;
    u32 best = 0xFFFFFFFF;
    for (room = 0; room < ROOMS; room++) {
        u32 across = difference(waypoint_x_of(floor, room), x);
        u32 down = difference(waypoint_y_of(floor, room), y);
        u32 distance = across * across + down * down;
        if (distance < best) {
            best = distance;
            nearest = room;
        }
    }
    return nearest;
}

/* --- which way --------------------------------------------------------------------------------------- */
/* Across a floor: up or down a row, left or right a column (rooms: even on the right, 0-1 at the
   bottom) - never which room exactly. */
static void across(u8 line, u8 to_room)
{
    u8 from_row = RAM(ROOM) >> 1;
    u8 to_row = to_room >> 1;
    u8 from_left = RAM(ROOM) & 1;
    u8 to_left = to_room & 1;
    if (to_row != from_row) {
        add(line, to_row > from_row ? "UP" : "DOWN");
        if (from_left != to_left) {
            add(line, " AND ");
        }
    }
    if (from_left > to_left) {
        add(line, "TO THE RIGHT");
    } else if (from_left < to_left) {
        add(line, "TO THE LEFT");
    }
    add(line, ".");
}

/* Up or down the stairs, so many floors; else across this floor. */
static void way(u8 line, u8 floor, u8 room)
{
    u8 climbs = difference(floor, RAM(FLOOR));
    if (climbs == 0) {
        across(line, room);
        return;
    }
    add(line, floor > RAM(FLOOR) ? "UP THE STAIRS, " : "DOWN THE STAIRS, ");
    add_digit(line, climbs);
    add(line, climbs > 1 ? " FLOORS." : " FLOOR.");
}

/* --- the hints --------------------------------------------------------------------------------------- */
static void get_out(void)
{
    add(0, "YOU HAVE THE URN! GET OUT NOW!");
    if (RAM(FLOOR) == FRONT_DOOR_FLOOR && RAM(ROOM) == FRONT_DOOR_ROOM) {
        add(1, "WALK OUT OF THIS ROOM'S");
        add(2, "RIGHT-HAND EDGE.");
        return;
    }
    add(1, "THE FRONT DOOR IS");
    way(2, FRONT_DOOR_FLOOR, FRONT_DOOR_ROOM);
}

static void take_it(u8 item)
{
    add(0, RAM(URN_SHAPES + item - URN) == WHOLE_URN ? "THE URN IS" : "A PIECE IS");
    add(0, " IN THIS ROOM.");
    if (RAM(FLAGS) & MATCH_LIT) {
        add(1, "WALK INTO IT WHILE THE");
        add(2, "MATCH BURNS.");
    } else {
        add(1, "LIGHT A MATCH - B - AND");
        add(2, "WALK INTO IT.");
    }
}

/* '3 PIECES LEFT. THE NEAREST IS' - what's in your hands counted as found - then which way. */
static void find_it(u8 item)
{
    u8 left = URN_PIECES;
    u8 floor = RAM(ITEM_FLOOR + item);
    if (RAM(CARRIED) >= URN && RAM(CARRIED) != NOTHING) {
        left -= pieces_of(RAM(CARRIED));
    }
    if (left == 1) {
        add(0, "1 PIECE LEFT. IT IS");
    } else {
        add_digit(0, left);
        add(0, " PIECES LEFT. THE NEAREST IS");
    }
    way(1, floor, room_at(floor, RAM(ITEM_X + item), RAM(ITEM_Y + item)));
}

static void hint(void)
{
    u8 item;
    clear_lines();
    if (RAM(GAME_STATE) != PLAYING) {
        add(0, "PRESS START TO PLAY.");
        add(1, "SELECT CHOOSES THE GAME.");
    } else if (holding_whole_urn()) {
        get_out();
    } else {
        item = nearest_urn();
        if (item == NO_ITEM) {
            add(0, "NOTHING LEFT TO FIND.");
        } else if (RAM(ITEM_FLOOR + item) == RAM(FLOOR)
                   && room_at(RAM(FLOOR), RAM(ITEM_X + item), RAM(ITEM_Y + item)) == RAM(ROOM)) {
            take_it(item);
        } else {
            find_it(item);
        }
    }
    show(HINT_FRAMES);
}

/* --- the notes --------------------------------------------------------------------------------------- */
/* What a held item is called in a note: THE KEY, THE SCEPTER, THE PIECE, THE URN (more than one piece). */
static const char *thing_name(u8 item)
{
    if (item == KEY) {
        return "THE KEY";
    }
    if (item == SCEPTER) {
        return "THE SCEPTER";
    }
    return pieces_of(item) > 1 ? "THE URN" : "THE PIECE";
}

/* You hold one thing at a time (joined pieces are one urn): taking something puts down what you held. */
static void swap_note(u8 put_down)
{
    clear_lines();
    add(0, "YOU PUT DOWN ");
    add(0, thing_name(put_down));
    add(1, "TO TAKE ");
    add(1, thing_name(RAM(CARRIED)));
    add(1, ".");
    add(2, "YOU HOLD ONE THING AT A TIME.");
    show(HINT_FRAMES);
}

static void whole_urn_note(void)
{
    clear_lines();
    add(0, "THE URN IS WHOLE!");
    add(1, "NOW GET IT OUT OF THE");
    add(2, "FRONT DOOR - FLOOR 1, RIGHT.");
    show(HINT_FRAMES);
}

static void lights_note(void)
{
    clear_lines();
    if (lights_on) {
        add(0, "LIGHTS ON - A CHEAT.");
        add(1, "PICKING UP NEEDS A MATCH LIT.");
        add(2, "B AND SELECT TURN THEM OFF.");
        show(HINT_FRAMES);
    } else {
        add(0, "LIGHTS OFF.");
        show(NOTE_FRAMES);
    }
}

/* The notes that come by themselves, from what's changed since last frame. */
static void notes(void)
{
    u8 carried = RAM(CARRIED);
    u8 whole;
    whole = holding_whole_urn();
    if (whole && was_whole == 0) {
        whole_urn_note();
    } else if (carried != was_carried && carried != NOTHING && was_carried != NOTHING) {
        swap_note(was_carried);
    }
    if (lights_on != was_lights) {
        lights_note();
    }
    was_carried = carried;
    was_whole = whole;
    was_lights = lights_on;
}

/* --- each frame -------------------------------------------------------------------------------------- */
void set_up_hints(void)
{
    note_left = 0;
    was_carried = NOTHING;
    was_whole = 0;
    was_lights = 0;
    was_shapes = 0;
    hint_asked = 0;
}

/* A note cut short (a new screen): the floor's name back at once. */
void end_note(void)
{
    if (note_left) {
        note_left = 0;
        status_note_over();
    }
}

/* X in play: a hint (screens.c hears the button). */
void ask_for_hint(void)
{
    hint_asked = 1;
}

/* Each frame in play: the notes, a hint if asked for, and the floor's name back when a note is done. */
void hints_frame(void)
{
    u8 shape = RAM(URN_SHAPES) ^ RAM(URN_SHAPES + 1) ^ RAM(URN_SHAPES + 2);   /* (any change shows) */
    if (RAM(CARRIED) != was_carried || lights_on != was_lights || shape != was_shapes) {
        notes();                     /* (only when what they hear has changed: a frame in play is full) */
        was_shapes = shape;
    }
    if (hint_asked) {
        hint_asked = 0;
        hint();
    }
    if (note_left) {
        note_left--;
        if (note_left == 0) {
            status_note_over();
        }
    }
}
