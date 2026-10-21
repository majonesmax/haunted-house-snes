/* The full screens (docs/plan.md, step 4), as the remaster's SNES look draws them: the story at
   power-on, the title (game select) with the mansion under the moon, the eyes in the tower window, rain
   and lightning; game over, the eyes closing and the window going dark; the help; and the ending at dawn,
   the eyes walking off down the hill with the urn. Which shows follows the game's state, as in the NES
   game (its screens.s, choose_screen).

   A screen's picture is a picture set like a floor's (tools/make_screens.py), loaded by picture.c; its
   sky is the backdrop by HDMA (status.c); its words are on the third layer, composed here into a map
   that's sent whole when it changes. Everything here only reads the state. */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "art.h"
#include "cast.h"
#include "status.h"
#include "screens.h"

#define MAP_COLUMNS 32
#define MAP_ROWS 28
#define VRAM_TEXT_MAP 0x1800         /* the third layer's map (status.c) */
#define WORDS_WHITE 1                /* the third layer's word palettes (status.c) */
#define WORDS_GREY 2
#define WORDS_DIM 3
#define PRIORITY 0x2000
#define PALETTE_SHIFT 10
/* The words' rows (the remaster's places, less the 8 lines the SNES doesn't show, on 8-line rows). */
#define LOGO_ROW 2                   /* the logo's big letters: two rows */
#define SUBTITLE_ROW 4
#define GAME_ROW 6
#define RULES_ROW 8
#define RULES_COLUMN 1
#define HINT_ROW 27
#define MATCHES_ROW 7                /* game over: the matches used */
#define ENDING_GAME_ROW 5            /* the ending: with the urn, the game... */
#define ENDING_MATCHES_ROW 6         /* ...the matches used... */
#define VERDICT_ROW 8                /* ...how you did... */
#define ENDING_HINT_ROW 10           /* ...and the keys */
#define STORY_ROW 5                  /* the story's first line, then every other row */
#define HELP_ROW 2
#define HELP_COLUMN 1
/* The timings (the remaster's NES look). */
#define GAME_OVER_WORDS 170          /* game over: the words, this many frames in */
#define EYES_CLOSE 90                /* the eyes close... */
#define LIGHT_FLICKER 110            /* ...the window's light flickers... */
#define LIGHT_OUT 150                /* ...and goes out */
#define FLICKER_STEPS 10
#define FLICKER_STEP_FRAMES 4
#define ENDING_WORDS 60
#define ENDING_VERDICT 110
#define STORY_LINE_FRAMES 45
#define LOOK_FRAMES 40               /* the eyes in the window look one way this long */
#define LOOKS 6
#define BLINK_EVERY 180
#define BLINK_FRAMES 8
#define STORY_BLINK_EVERY 120
#define STORY_BLINK_FRAMES 6
#define WALK_START 40                /* the ending: the eyes leave the door this many frames in... */
#define WALK_SPEED 115               /* ...0.45 pixels a frame (in 256ths)... */
#define LOOK_BACK_AT 172             /* ...stop here to look back... */
#define LOOK_BACK_FRAMES 60
#define REST_MARGIN 27               /* ...and stand this far in from the hill's end */
#define BOB_EVERY 8
#define MOST_WALKING 400             /* frames: by then the eyes are resting at the hill's end */
#define URN_GAP 2
#define FLASH_EVERY 330              /* the title's lightning: a flash this often, fading over FLASH_LEVELS */
#define STORY_OVER 2                 /* story_state: the story is showing (0), ending (1), over */
#define STORY_ENDING 1
/* The sprite table's entries the screens use (the play's cast is hidden meanwhile: cast.c). */
#define SCREEN_SLOTS 0
#define SCREEN_SLOTS_END 4
#define RAIN_SLOTS 40
#define HIDDEN_Y 240
#define IN_FRONT 3

u8 screen_shown;                     /* the screen on show */
u16 screen_frames;                   /* frames it's been showing */
static u8 story_state;
static u8 help_open;
static u16 text_map[MAP_ROWS * MAP_COLUMNS];   /* the words, as the third layer's map wants them */
u8 screen_words_changed;             /* ...and whether they're yet to be sent */
static u8 shown_game;                /* the game number the title's words show */
static const u8 flicker[FLICKER_STEPS] = {1, 0, 1, 1, 0, 1, 0, 0, 1, 0};
static const u8 looks[LOOKS] = {CAST_EYES_CENTRE, CAST_EYES_LEFT, CAST_EYES_CENTRE, CAST_EYES_RIGHT,
                                CAST_EYES_UP, CAST_EYES_CENTRE};

/* What rain_frame (src/fast.asm) works with: each drop's place (x in 256ths) and fall, its sprite. */
u16 rain_x[RAIN_DROPS];
u8 rain_y[RAIN_DROPS];
u8 rain_fall[RAIN_DROPS];
u16 rain_drift[RAIN_DROPS];          /* x moves left a third of the fall a frame, in 256ths */
u8 rain_tile;
u8 rain_attr;
u8 rain_hidden;                      /* 1: rain_frame hides the drops instead */
void rain_frame(void);
void cast_put(void);
extern u8 cast_slot, place_left, place_top, place_wide, place_high, place_tile, place_attr, place_mirrored;

/* --- the words ------------------------------------------------------------------------------------- */
static void clear_text(void)
{
    u16 entry;
    for (entry = 0; entry < MAP_ROWS * MAP_COLUMNS; entry++) {
        text_map[entry] = 0;
    }
    screen_words_changed = 1;
}

static u8 text_length(const char *text)
{
    u8 length = 0;
    while (text[length]) {
        length++;
    }
    return length;
}

static void put_text(u8 row, u8 column, const char *text, u8 palette)
{
    u16 at = (row << 5) + column;
    while (*text) {
        text_map[at] = font_tiles[*text - FONT_FIRST_LETTER] | ((u16)palette << PALETTE_SHIFT) | PRIORITY;
        at++;
        text++;
    }
    screen_words_changed = 1;
}

static void put_centred(u8 row, const char *text, u8 palette)
{
    put_text(row, (MAP_COLUMNS - text_length(text)) >> 1, text, palette);
}

/* A number, 0-99, its tens left out when 0; returns the columns used. */
static u8 put_number(u8 row, u8 column, u8 number, u8 palette)
{
    char digits[3];
    u8 at = 0;
    if (number >= 10) {
        digits[at++] = '0' + number / 10;
    }
    digits[at++] = '0' + number % 10;
    digits[at] = 0;
    put_text(row, column, digits, palette);
    return at;
}

/* The logo: the font's letters at twice the size, in white with their shadows, over two rows. */
static void put_logo(const char *text)
{
    u16 at = (LOGO_ROW << 5) + ((MAP_COLUMNS - (text_length(text) << 1)) >> 1);
    u16 ink = ((u16)WORDS_WHITE << PALETTE_SHIFT) | PRIORITY;
    while (*text) {
        u8 big = big_letter_tiles[*text - FONT_FIRST_LETTER];
        if (big) {
            u16 tile = BIG_LETTERS + big - 1;
            text_map[at] = tile | ink;
            text_map[at + 1] = (tile + 1) | ink;
            text_map[at + MAP_COLUMNS] = (tile + 2) | ink;
            text_map[at + MAP_COLUMNS + 1] = (tile + 3) | ink;
        }
        at += 2;
        text++;
    }
    screen_words_changed = 1;
}

/* The matches used, from the state's two decimal digits in a byte. */
static u8 matches_used(void)
{
    u8 used = RAM(MATCHES_USED);
    return (used >> 4) * 10 + (used & 0x0F);
}

/* "GAME n", centred. */
static void put_game(u8 row, u8 palette)
{
    put_text(row, (MAP_COLUMNS - 6) >> 1, "GAME ", palette);
    put_number(row, ((MAP_COLUMNS - 6) >> 1) + 5, RAM(GAME_NUMBER) + 1, palette);
}

static void title_words(void)
{
    u8 line = rules_start[RAM(GAME_NUMBER)];
    u8 row = RULES_ROW;
    put_logo("HAUNTED HOUSE");
    put_centred(SUBTITLE_ROW, "BY MATCHLIGHT", WORDS_GREY);
    put_game(GAME_ROW, WORDS_WHITE);
    while (rules_lines[line][0]) {
        put_text(row, RULES_COLUMN, rules_lines[line], WORDS_GREY);
        line++;
        row++;
    }
    put_centred(HINT_ROW, TITLE_HINT, WORDS_GREY);
    shown_game = RAM(GAME_NUMBER);
}

static void game_over_words(void)
{
    u8 column;
    put_logo("GAME OVER");
    put_game(GAME_ROW, WORDS_WHITE);
    column = (MAP_COLUMNS - 15) >> 1;
    put_text(MATCHES_ROW, column, "MATCHES USED ", WORDS_GREY);
    put_number(MATCHES_ROW, column + 13, matches_used(), WORDS_GREY);
    put_centred(HINT_ROW, TITLE_HINT, WORDS_GREY);
}

static void ending_words(void)
{
    u8 used = matches_used();
    u8 width = used >= 10 ? 2 : 1;
    u8 column;
    put_logo("YOU ESCAPED!");
    column = (MAP_COLUMNS - 21) >> 1;
    put_text(ENDING_GAME_ROW, column, "WITH THE URN - GAME ", WORDS_WHITE);
    put_number(ENDING_GAME_ROW, column + 20, RAM(GAME_NUMBER) + 1, WORDS_WHITE);
    if (used == 1) {
        put_centred(ENDING_MATCHES_ROW, "1 MATCH USED", WORDS_WHITE);
        return;
    }
    column = (MAP_COLUMNS - width - 13) >> 1;
    put_number(ENDING_MATCHES_ROW, column, used, WORDS_WHITE);
    put_text(ENDING_MATCHES_ROW, column + width, " MATCHES USED", WORDS_WHITE);
}

static void verdict_words(void)
{
    u8 used = matches_used();
    u8 verdict = 0;
    while (verdict < VERDICTS - 1 && used > verdict_most[verdict]) {
        verdict++;
    }
    put_centred(VERDICT_ROW, verdict_lines[verdict], WORDS_GREY);
    put_centred(ENDING_HINT_ROW, ENDING_HINT, WORDS_WHITE);
}

static void help_words(void)
{
    u8 line;
    for (line = 0; line < HELP_LINES; line++) {
        put_text(HELP_ROW + line, HELP_COLUMN, help_lines[line], help_heading[line] ? WORDS_WHITE : WORDS_GREY);
    }
    put_centred(HINT_ROW, HELP_HINT, WORDS_GREY);
}

/* The story: a line every STORY_LINE_FRAMES, then the hint. */
static void story_words(void)
{
    u8 line;
    if (screen_frames % STORY_LINE_FRAMES) {
        return;
    }
    line = (u8)(screen_frames / STORY_LINE_FRAMES);
    if (line < STORY_LINES) {
        put_centred(STORY_ROW + (line << 1), story_lines[line], WORDS_WHITE);
    }
    if (line == STORY_LINES - 1) {
        put_centred(HINT_ROW, STORY_HINT, WORDS_DIM);
    }
}

/* --- which screen ------------------------------------------------------------------------------------ */
static u8 screen_wanted(void)
{
    if (story_state != STORY_OVER) {
        return SCREEN_STORY;
    }
    if (RAM(GAME_STATE) != SELECTING) {
        help_open = 0;
        return SCREEN_PLAY;
    }
    if (RAM(FLAGS) & WON_FLAG) {
        return SCREEN_ENDING;
    }
    if (RAM(LIVES) == 0) {
        return SCREEN_GAME_OVER;
    }
    return help_open ? SCREEN_HELP : SCREEN_TITLE;
}

/* A new screen: its words from the start, its sprites cleared. */
static void start_screen(u8 screen)
{
    screen_shown = screen;
    screen_frames = 0;
    clear_text();
    hide_screen_sprites();
    if (screen == SCREEN_PLAY) {
        show_cast_again();
        status_show_again();
    } else {
        hide_cast();
    }
    if (screen == SCREEN_TITLE) {
        title_words();
    } else if (screen == SCREEN_HELP) {
        help_words();
    } else if (screen == SCREEN_STORY) {
        story_words();
    }
}

/* The words that come with time, or with a new game chosen. */
static void timed_words(void)
{
    if (screen_shown == SCREEN_TITLE && RAM(GAME_NUMBER) != shown_game) {
        clear_text();
        title_words();
    } else if (screen_shown == SCREEN_GAME_OVER && screen_frames == GAME_OVER_WORDS) {
        game_over_words();
    } else if (screen_shown == SCREEN_ENDING && screen_frames == ENDING_WORDS) {
        ending_words();
    } else if (screen_shown == SCREEN_ENDING && screen_frames == ENDING_VERDICT) {
        verdict_words();
    } else if (screen_shown == SCREEN_STORY) {
        story_words();
    }
}

/* --- the sprites --------------------------------------------------------------------------------------- */
/* A cast picture with its middle at (x, y) on the screen, into the sprite table from cast_slot. */
static void put_sprite(u8 picture, s16 middle_x, s16 middle_y)
{
    u16 tile = cast_tile[picture];
    place_wide = cast_wide[picture];
    place_high = cast_high[picture];
    place_left = (u8)(middle_x - (place_wide << 3));
    place_top = (u8)(middle_y - (place_high << 3));
    place_tile = (u8)tile;
    place_attr = (u8)((IN_FRONT << 4) | (cast_palette[picture] << 1) | (tile >> 8));
    place_mirrored = 0;
    cast_put();
}

void hide_screen_sprites(void)
{
    u8 slot;
    for (slot = SCREEN_SLOTS; slot < SCREEN_SLOTS_END; slot++) {
        oamMemory[(slot << 2) + 1] = HIDDEN_Y;
    }
    rain_hidden = 1;
    rain_frame();
}

/* Game over: the window still lit, `since` frames in? Lit, then flickering, then out. */
static u8 window_lit(u16 since)
{
    if (since < LIGHT_FLICKER) {
        return 1;
    }
    if (since >= LIGHT_OUT) {
        return 0;
    }
    return flicker[((since - LIGHT_FLICKER) >> 2) % FLICKER_STEPS];
}

/* The eyes in the tower window, looking about and blinking (closed for good at game over), in their
   dark room; or the window dark. */
static void window_sprites(void)
{
    u8 game_over = screen_shown == SCREEN_GAME_OVER;
    s16 middle_x = WINDOW_X + (WINDOW_WIDE >> 1);
    s16 middle_y = WINDOW_Y + (WINDOW_HIGH >> 1);
    u8 eyes = looks[(frame_count / LOOK_FRAMES) % LOOKS];
    cast_slot = SCREEN_SLOTS;
    if (game_over && window_lit(screen_frames) == 0) {
        put_sprite(CAST_DARK_WINDOW, middle_x, middle_y);
    } else {
        if (frame_count % BLINK_EVERY < BLINK_FRAMES || (game_over && screen_frames >= EYES_CLOSE)) {
            eyes = CAST_EYES_BLINK;
        }
        put_sprite(eyes, middle_x, middle_y);
        put_sprite(CAST_WINDOW_ROOM, middle_x, middle_y);
    }
}

static void story_sprites(void)
{
    u8 eyes = CAST_EYES_CENTRE;
    if (screen_frames % STORY_BLINK_EVERY < STORY_BLINK_FRAMES) {
        eyes = CAST_EYES_BLINK;
    }
    cast_slot = SCREEN_SLOTS;
    put_sprite(eyes, 128, STORY_EYES_Y + (EYES_HIGH >> 1));
}

/* The ending: from the front door the eyes walk down the hill to the right with the urn, stop once to
   look back at the house, then go on to the end of the hill (the remaster's walk). Out: 256ths walked;
   looking_back set while they look back. */
static u8 looking_back;
static u16 walked(void)
{
    u16 walking = screen_frames > WALK_START ? screen_frames - WALK_START : 0;
    u16 stop_at = (u16)(((u16)(LOOK_BACK_AT - DOOR_MIDDLE_X) << 8) / WALK_SPEED);
    u16 rest = (u16)(HILL_END_X - REST_MARGIN - DOOR_MIDDLE_X) << 8;
    u16 far;
    looking_back = 0;
    if (walking > MOST_WALKING) {
        walking = MOST_WALKING;          /* (long since resting: and the sums stay in 16 bits) */
    }
    if (walking < stop_at) {
        return walking * WALK_SPEED;
    }
    if (walking < stop_at + LOOK_BACK_FRAMES) {
        looking_back = 1;
        return stop_at * WALK_SPEED;
    }
    far = (walking - LOOK_BACK_FRAMES) * WALK_SPEED;
    return far < rest ? far : rest;
}

static void ending_sprites(void)
{
    u16 far = walked();
    s16 x = DOOR_MIDDLE_X + (far >> 8);
    u8 resting = x >= HILL_END_X - REST_MARGIN;
    u8 bob = 0;
    if (looking_back == 0 && resting == 0) {
        bob = (screen_frames >> 3) & 1;
    }
    cast_slot = SCREEN_SLOTS;
    put_sprite(looking_back ? CAST_EYES_LEFT : CAST_EYES_RIGHT, x, GROUND_Y - (EYES_HIGH >> 1) - bob);
    put_sprite(CAST_URN8, x + (EYES_WIDE >> 1) + URN_GAP + (URN_WIDE >> 1),
               GROUND_Y - (URN_HIGH >> 1) + 2 - bob);
}

static void screen_sprites(void)
{
    if (screen_shown == SCREEN_TITLE || screen_shown == SCREEN_GAME_OVER) {
        window_sprites();
        rain_hidden = 0;
        rain_frame();
    } else if (screen_shown == SCREEN_STORY) {
        story_sprites();
    } else if (screen_shown == SCREEN_ENDING) {
        ending_sprites();
    }
}

/* The title's lightning: a flash every FLASH_EVERY frames, fading over FLASH_LEVELS - each frame of it its
   own sky table, brightened (tools/make_screens.py), the first the plain sky. */
static void title_lightning(void)
{
    u16 since = frame_count % FLASH_EVERY;
    sky_offset = 0;
    if (since < FLASH_LEVELS) {
        sky_offset = (since + 1) * SKY_TABLE_BYTES;
    }
}

/* --- each frame ---------------------------------------------------------------------------------------- */
void set_up_screens(void)
{
    u8 drop;
    for (drop = 0; drop < RAIN_DROPS; drop++) {
        rain_x[drop] = (u16)rain_start_x[drop] << 8;
        rain_y[drop] = rain_start_y[drop];
        rain_fall[drop] = rain_speed[drop];
        rain_drift[drop] = (u16)(((u16)rain_speed[drop] << 8) / 3);
    }
    rain_tile = (u8)cast_tile[CAST_RAIN];
    rain_attr = (u8)((IN_FRONT << 4) | (cast_palette[CAST_RAIN] << 1) | (cast_tile[CAST_RAIN] >> 8));
    story_state = 0;
    help_open = 0;
    screen_shown = SCREEN_PLAY;
    start_screen(SCREEN_STORY);
}

/* The buttons the screens have besides the 2600's (main.c, read_controls): any button ends the story
   (and nothing else, even held: the title comes next); X opens and closes the help on the title. While
   the story shows, the game hears nothing. Out: 1 if the game is to hear nothing this frame. */
u8 screen_buttons(u16 pad, u16 pressed)
{
    if (story_state == STORY_OVER) {
        if ((pressed & KEY_X) && (screen_shown == SCREEN_TITLE || screen_shown == SCREEN_HELP)) {
            help_open ^= 1;
        }
        return 0;
    }
    if (story_state == 0 && pressed) {
        story_state = STORY_ENDING;
    } else if (story_state == STORY_ENDING && pad == 0) {
        story_state = STORY_OVER;
    }
    return 1;
}

/* Each frame, once the game's frame is worked out: the screen for the moment, its words and sprites. */
void screens_frame(void)
{
    u8 wanted = screen_wanted();
    if (wanted != screen_shown) {
        start_screen(wanted);
    } else {
        screen_frames++;
    }
    if (screen_shown == SCREEN_PLAY) {
        return;
    }
    timed_words();
    screen_sprites();
    title_lightning();
}

/* In the vertical blank: the words to the third layer's map, if they've changed (the whole map, 1792
   bytes: about 10 lines of the blank). */
void send_screen_words(void)
{
    if (screen_words_changed == 0) {
        return;
    }
    send_words_map((u8 *)text_map, VRAM_TEXT_MAP, sizeof text_map);
    screen_words_changed = 0;
}
