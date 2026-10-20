/* One whole frame of the game, in the game's own order (the spec, "One frame, in order"; the remaster's
   game/player.py): the switches, the player moving, the match, what's drawn and what touched, the items
   and the urn, dying and winning. Each function names the spec's section or the original's routine. */
#include "state.h"
#include "mansion.h"
#include "engine.h"

#define MATCH_SECONDS 20
#define FRAMES_PER_SECOND 60
#define SELECT_REPEAT 45      /* frames between game numbers while SELECT is held */
#define GAME_COUNT 9
#define PRESSED 0x7F          /* BUTTON_HISTORY for a press: pressed now, up for the 7 frames before */
#define DROP_SEARCH 5
#define DROP_UP 0x0A          /* the drop offset that points up */
#define GAME_3 2
#define FIRST_FAST_GAME 7     /* games 8-9: the ghost ignores the scepter */
#define FIRST_THEFT_GAME 6    /* games 7-9: the bat takes what the player held */
#define FIRST_FIVE_MONSTER_GAME 4
#define FOLLOW_FROM_GAME 5
#define SCROLL_STOPS 0xD7     /* from this y the view stops scrolling at the top... */
#define SCROLL_TOP_OFFSET 0xAF /* ...and the eyes' line is y minus this */
#define NEW_GAME_FROM 0x96    /* RESET copies the new_game table to $96-$9F... */
#define NEW_GAME_SIZE 10
#define CLEARED_TO 0x96       /* ...after clearing $80-$95 */

static void after_picture(const Controls *controls, Touches *touches);
static void button(const Controls *controls, const Touches *touches);

/* --- a new game and the switches ($F079) --- */
/* Game over and game select look the same ($F141): the match goes out, the colours start to drift. */
void select_mode(void)
{
    match_out();
    flip_turn();
    RAM(GAME_STATE) = SELECTING;
    RAM(COLOUR_CYCLE) = ATTRACT;
    RAM(MONSTER_SHOWN) = 0;
    RAM(DEATH_TIMER) = 0;
    RAM(MONSTERS_HERE) = 0;
}

/* RESET ($F082): done every frame the switch is held. */
void new_game(void)
{
    u8 swap = RAM(RANDOM_LOW);
    u8 address;
    u8 number;
    RAM(RANDOM_LOW) = RAM(RANDOM_HIGH);
    RAM(RANDOM_HIGH) = swap;
    for (address = 0x80; address < CLEARED_TO; address++) {
        RAM(address) = 0;
    }
    for (number = 0; number < NEW_GAME_SIZE; number++) {
        RAM(NEW_GAME_FROM + number) = new_game_bytes[number];
    }
    RAM(FLOOR) = FRONT_DOOR_FLOOR;
    scatter();
    RAM(MONSTER_FLOOR + GHOST) = GHOST_START_FLOOR;
    for (number = 0; number < 5; number++) {
        RAM(ITEM_FLOOR + number) = RAM(MONSTER_FLOOR + number);
        RAM(ITEM_X + number) = RAM(MONSTER_X + number);
        RAM(ITEM_Y + number) = RAM(MONSTER_Y + number);
    }
    if (RAM(GAME_NUMBER) == GAME_3) {
        RAM(ITEM_FLOOR + KEY) = GAME_3_KEY_FLOOR;
        RAM(ITEM_X + KEY) = GAME_3_KEY_X;
        RAM(ITEM_Y + KEY) = GAME_3_KEY_Y;
    }
    room_changed();
    RAM(LAST_MONSTER) = RAM(GAME_NUMBER) >= FIRST_FIVE_MONSTER_GAME ? 4 : 2;
    RAM(POS_X) = START_X;
    RAM(POS_Y) = START_Y;
    RAM(EYES_LINE) = MIDDLE_SCREEN_LINE;
}

static void switches(const Controls *controls)
{
    if (controls->reset) {
        new_game();
    } else if (!controls->select) {
        RAM(SELECT_DELAY) = 1;
    } else {
        RAM(SELECT_DELAY) -= 1;
        if (RAM(SELECT_DELAY) == 0) {
            RAM(SELECT_DELAY) = SELECT_REPEAT;
            RAM(GAME_NUMBER) += 1;
            if (RAM(GAME_NUMBER) == GAME_COUNT) {
                RAM(GAME_NUMBER) = 0;
            }
            select_mode();
        }
    }
}

/* --- moving ($F1A5, $F1BF) --- */
/* At the floor's limit: mark it (the stairs or the front door may take it from here); with no stairs in
   the room, it's a bump ($F254). */
static void reach_edge(void)
{
    RAM(STAIRS) |= AT_EDGE;
    if (RAM(STAIRS) == (AT_EDGE | NO_STAIRS)) {
        start_effect(EFFECT_BUMP);
    }
}

static void move_across(void)
{
    u8 stick = RAM(JOYSTICK);
    u8 x = RAM(POS_X);
    u8 y = RAM(POS_Y);
    u8 step;
    u8 limit;
    u8 probe_x;
    if (stick & STICK_LEFT) {
        step = 0xFF;
        limit = FLOOR_LEFT;
        probe_x = x - 1;
    } else if (stick & STICK_RIGHT) {
        step = 1;
        limit = FLOOR_RIGHT;
        probe_x = x + 8;
    } else {
        return;
    }
    RAM(STEP_X) = step;
    if (x == limit) {
        reach_edge();
    } else if (wall_at(probe_x, y + 2, RAM(FLOOR)) || wall_at(probe_x, y, RAM(FLOOR))) {
        start_effect(EFFECT_BUMP);
    } else {
        RAM(POS_X) = x + step;
    }
}

static void move_up_or_down(void)
{
    u8 pushed = RAM(JOYSTICK) & (STICK_UP | STICK_DOWN);
    u8 x = RAM(POS_X);
    u8 y = RAM(POS_Y);
    u8 step;
    u8 limit;
    u8 probe_y;
    if (!pushed) {
        return;
    }
    if (pushed == STICK_DOWN) {
        step = 0xFF;
        limit = FLOOR_BOTTOM;
        probe_y = y - 1;
    } else {
        step = 1;
        limit = FLOOR_TOP;
        probe_y = y + 3;
    }
    RAM(STEP_Y) = step;
    if (y == limit) {
        reach_edge();
    } else if (wall_at(x + 7, probe_y, RAM(FLOOR)) || wall_at(x, probe_y, RAM(FLOOR))) {
        start_effect(EFFECT_BUMP);
    } else {
        RAM(POS_Y) = y + step;
    }
}

/* The screen line the eyes are drawn on: mid-screen, except near the floor's ends ($F1AD). */
static u8 eyes_line(u8 y)
{
    if (y < MIDDLE_SCREEN_LINE) {
        return y;
    }
    if (y >= SCROLL_STOPS) {
        return y - SCROLL_TOP_OFFSET;
    }
    return MIDDLE_SCREEN_LINE;
}

static void move(void)
{
    RAM(STEP_X) = 0;
    RAM(STEP_Y) = 0;
    RAM(STAIRS) &= (u8)~AT_EDGE;
    if (!(RAM(BLOCKED) & 0x40)) {
        move_across();
    }
    if (!(RAM(BLOCKED) & 0x80)) {
        move_up_or_down();
    }
    RAM(BLOCKED) = 0;
    RAM(EYES_LINE) = eyes_line(RAM(POS_Y));
}

/* --- the front door and the match ($F155) --- */
void match_out(void)
{
    RAM(MONSTER_SHOWN) = 0;
    RAM(FLAGS) &= KEEP_ON_MATCH_OUT;
}

/* Items and monsters take turns to be drawn while a match is lit. */
void flip_turn(void)
{
    RAM(FLAGS) ^= MONSTER_TURN;
}

static void front_door_and_match(void)
{
    u8 at_front_door = (RAM(STAIRS) & AT_EDGE) && RAM(FLOOR) == FRONT_DOOR_FLOOR
                       && RAM(ROOM) == FRONT_DOOR_ROOM;
    if (at_front_door) {
        if (RAM(CARRIED) == URN && RAM(URN_SHAPES) == WHOLE_URN) {
            RAM(CLOCK) = 1;
            RAM(FLAGS) = WON_FLAG;
            RAM(GAME_STATE) = WON;
        } else {
            start_effect(EFFECT_BLOCKED);
        }
    }
    RAM(SECOND_COUNTER) -= 1;
    if (RAM(SECOND_COUNTER) == 0) {
        RAM(SECOND_COUNTER) = FRAMES_PER_SECOND;
        RAM(MATCH_TIME) -= 1;
    }
    if ((RAM(FLAGS) & MATCH_LIT) && (RAM(MONSTERS_HERE) || RAM(MATCH_TIME) == 0)) {
        match_out();
    }
    flip_turn();
}

/* --- one frame ($F016) --- */
void game_frame(const Controls *controls)
{
    Sprite sprite;
    Touches touches;
    RAM(CLOCK) += 1;
    switches(controls);
    if (!(RAM(GAME_STATE) & NO_PLAY)) {
        move();
        front_door_and_match();
    }
    choose_sprite(&sprite);
    next_random();
    draw(&sprite, controls->stick, &touches);
    sound_frame();
    if (!(RAM(GAME_STATE) & NO_LOGIC)) {
        after_picture(controls, &touches);
    }
}

/* --- below the picture: dying ($F8AC) --- */
/* Games 7-9: the bat leaves what it took where it is. */
static void bat_takes_item(void)
{
    u8 carried = RAM(CARRIED);
    if (RAM(KILLED_BY) != BAT || RAM(GAME_NUMBER) < FIRST_THEFT_GAME || carried == NOTHING) {
        return;
    }
    RAM(ITEM_FLOOR + carried) = RAM(MONSTER_FLOOR + BAT);
    RAM(ITEM_X + carried) = RAM(MONSTER_X + BAT);
    RAM(ITEM_Y + carried) = RAM(MONSTER_Y + BAT);
    RAM(CARRIED) = NOTHING;
}

/* Count down a death. True on the frame it ends, when the monsters don't move. */
static u8 death_timer(void)
{
    RAM(GAME_STATE) &= (u8)~JUST_RESET;
    if (!(RAM(GAME_STATE) & DYING)) {
        return 0;
    }
    RAM(DEATH_TIMER) -= 1;
    if (RAM(DEATH_TIMER)) {
        return 0;
    }
    RAM(GAME_STATE) = PLAYING;
    RAM(SOUND) = 0;
    if (RAM(LIVES) == 0) {
        select_mode();
    }
    scatter();
    bat_takes_item();
    return 1;
}

/* --- stairs ($FB68) --- */
/* Take the stairs if the player is at the edge of a room that has them. In games 1-5 the routine that
   sends monsters after the player jumps into the button's code instead of returning, so on that frame the
   button is read twice ($FB2B). */
static void stairs(const Controls *controls, const Touches *touches)
{
    u8 here = RAM(STAIRS);
    u8 going_up;
    if ((here & NO_STAIRS) == NO_STAIRS) {
        return;
    }
    if (!(here & AT_EDGE)) {
        RAM(STAIRS) = here & NO_STAIRS;
        return;
    }
    if (here & JUST_USED_STAIRS) {
        return;
    }
    if (RAM(GAME_NUMBER) < FOLLOW_FROM_GAME) {
        button(controls, touches);
    } else {
        follow_up_stairs(RAM(ROOM), here);
    }
    going_up = here & GOES_UP;
    RAM(FLOOR) += going_up ? 1 : 0xFF;
    start_effect(going_up ? EFFECT_STAIRS_UP : EFFECT_STAIRS_DOWN);
    room_changed();
    RAM(STAIRS) |= JUST_USED_STAIRS;
}

/* --- the button ($FB92) and dropping ($FBE2) --- */
/* Two decimal digits in a byte, plus one (the 6502 in decimal mode). */
static u8 bcd_plus_one(u8 number)
{
    u8 ones = (number & 0x0F) + 1;
    u8 tens = number >> 4;
    if (ones > 9) {
        ones -= 10;
        tens += 1;
    }
    if (tens > 9) {
        tens -= 10;
    }
    return (u8)((tens << 4) | ones);
}

static void light_match(void)
{
    RAM(MATCH_TIME) = MATCH_SECONDS;
    RAM(MATCHES_USED) = bcd_plus_one(RAM(MATCHES_USED));
    RAM(FLAGS) |= MATCH_LIT;
}

/* Move the dropped item to an offset from the player; 0 if that's off the floor ($FC0B). The y is written
   even when the x fails. */
static u8 try_drop_spot(u8 y_index, u8 x_index)
{
    u8 item = RAM(DROPPED);
    u8 offset_y = drop_offsets[1 + y_index];
    u8 new_y;
    u8 new_x;
    if (RAM(POS_Y) >= DROP_TOO_HIGH && offset_y == DROP_UP) {
        return 0;
    }
    new_y = (u8)(offset_y + RAM(POS_Y));
    if (new_y >= DROP_TOO_HIGH) {
        return 0;
    }
    RAM(ITEM_Y + item) = new_y;
    RAM(SPRITE_LINE) = line_of(new_y);
    new_x = (u8)(drop_offsets[x_index] + RAM(POS_X));
    if (new_x >= DROP_TOO_FAR_RIGHT) {
        return 0;
    }
    RAM(ITEM_X + item) = new_x;
    RAM(SPRITE_X) = new_x;
    return 1;
}

/* Try the next spots in turn - left, below, right, above - until one is on the floor ($FBFB). */
static void next_drop_spot(void)
{
    while (1) {
        u8 spot;
        RAM(DROP_TRIES) -= 1;
        if (RAM(DROP_TRIES) == 0) {
            return;
        }
        spot = RAM(DROP_TRIES) - 1;
        if (try_drop_spot(spot, spot)) {
            return;
        }
    }
}

/* Put the carried item down: first behind the player, if they tried to move this frame. */
void start_drop(void)
{
    u8 step_x = RAM(STEP_X);
    u8 step_y = RAM(STEP_Y);
    RAM(DROP_TRIES) = DROP_SEARCH;
    RAM(DROPPED) = RAM(CARRIED);
    if (step_x | step_y) {
        if (try_drop_spot((u8)(step_y + 1), (u8)(step_x + 2))) {
            return;
        }
    }
    next_drop_spot();
}

/* Read the stick for next frame; a press lights a match, or with one lit drops what's carried; and move
   the drop search on. */
static void button(const Controls *controls, const Touches *touches)
{
    RAM(JOYSTICK) = controls->stick;
    if (!RAM(MONSTERS_HERE)) {
        RAM(BUTTON_HISTORY) = (RAM(BUTTON_HISTORY) >> 1) | (controls->button ? 0 : 0x80);
        if (RAM(BUTTON_HISTORY) == PRESSED) {
            if (!(RAM(FLAGS) & MATCH_LIT)) {
                light_match();
                return;
            }
            if (RAM(CARRIED) != NOTHING) {
                start_effect(EFFECT_DROP);
                start_drop();
                RAM(CARRIED) = NOTHING;
                return;
            }
        }
    }
    if (RAM(DROP_TRIES)) {
        if (touches->walls) {
            next_drop_spot();
        } else {
            RAM(DROP_TRIES) = 0;
        }
    }
}

/* --- touching ($FA90): caught, or picking up --- */
/* The scepter saves the player, except from the ghost in games 8-9 ($FB0C). */
static void maybe_caught(void)
{
    u8 monster = RAM(MONSTER_SHOWN);
    u8 ghost_ignores_scepter = RAM(GAME_NUMBER) >= FIRST_FAST_GAME && monster == GHOST;
    if (RAM(CARRIED) == SCEPTER && !ghost_ignores_scepter) {
        return;
    }
    RAM(GAME_STATE) = DYING;
    RAM(DEATH_TIMER) = 0xFF;
    RAM(LIVES) -= 1;
    RAM(KILLED_BY) = monster;
}

/* Two urn pieces join; `pieces` is the sum of their item numbers. Returns the item now carried. */
static u8 join(u8 pieces)
{
    u8 holder;
    start_effect(EFFECT_JOIN);
    if ((RAM(URN_SHAPES + 1) | RAM(URN_SHAPES + 2)) & 0x80) {
        start_effect(EFFECT_URN_WHOLE);
        RAM(URN_SHAPES) = WHOLE_URN;
        RAM(URN_SHAPES + 1) = JOINED;
        RAM(URN_SHAPES + 2) = JOINED;
        return URN;
    }
    RAM(URN_SHAPES + (pieces == 5 ? 1 : 2)) = JOINED;
    holder = pieces == 7 ? 1 : 0;
    RAM(URN_SHAPES + holder) = pieces;
    return URN + holder;
}

/* Take the item touched; an urn piece touching the carried one joins it; anything else carried is put
   down ($FAAC). */
static void pick_up(void)
{
    u8 carried = RAM(CARRIED);
    u8 touched = RAM(ITEM_SHOWN);
    u8 joins = carried != NOTHING && carried != touched && carried >= URN && touched >= URN;
    u8 now_carried;
    start_effect(EFFECT_PICK_UP);
    now_carried = joins ? join(carried + touched) : touched;
    if (carried != NOTHING) {
        start_drop();
    }
    RAM(CARRIED) = now_carried;
}

static void touching(const Touches *touches)
{
    if (RAM(DEATH_TIMER)) {   /* (three tests, not one "or": the compiler got the one wrong) */
        return;
    }
    if (!touches->eyes) {
        return;
    }
    if (RAM(DROP_TRIES)) {
        return;
    }
    if (!(RAM(FLAGS) & MATCH_LIT)) {
        if (RAM(MONSTER_SHOWN) <= RAM(LAST_MONSTER)) {
            maybe_caught();
        }
    } else if (!(RAM(FLAGS) & MONSTER_TURN)) {
        pick_up();
    }
}

/* The work done below the picture ($F05E). */
static void after_picture(const Controls *controls, Touches *touches)
{
    if (death_timer()) {
        touches->eyes = 0;     /* the collisions were cleared ($F8C9) */
        touches->walls = 0;
    } else {
        move_monsters();
    }
    stairs(controls, touches);
    button(controls, touches);
    touching(touches);
    doorways();
}
