/* The engine: one frame of the game, from the spec (docs/plan.md, step 1). What the modules share. */
#ifndef ENGINE_H
#define ENGINE_H
#include <snes.h>

typedef struct {
    u8 stick;      /* pushed directions, as JOYSTICK holds them: STICK_RIGHT | STICK_LEFT | ... */
    u8 button;     /* the joystick's button: lights a match, drops */
    u8 reset;      /* the console's RESET switch: a new game */
    u8 select;     /* the console's SELECT switch: the next game number */
} Controls;

/* What's drawn in a frame besides the eyes and the walls: one item, monster or the stairs. */
typedef struct {
    u8 x;          /* its column */
    u8 line;       /* the line of its bottom row */
    u8 picture;    /* where its picture is in the shapes page, bottom row first */
    u8 height;     /* its rows; 0 means no sprite at all */
    u8 wide;       /* drawn at double width (the stairs) */
} Sprite;

/* What this frame's sprite overlapped in the picture: the 2600's collision latches. */
typedef struct {
    u8 eyes;
    u8 walls;
} Touches;

#define SPRITE_HEIGHT_ITEM 8
#define SPRITE_HEIGHT_MONSTER 10
#define SPRITE_HEIGHT_STAIRS 17
#define ITEM_SHAPES 0x08      /* where each kind of picture starts in the shapes page */
#define MONSTER_SHAPES 0x50
#define STAIRS_SHAPES 0x8C
#define MIDDLE_SCREEN_LINE 0x26
#define VIEW_LINES 0x50       /* the view is 80 lines; a sprite starting below it may still show... */
#define LAST_LINE_BELOW 0xF9  /* ...if it starts no lower than this */
#define TOP_LINE 79

/* main.c */
u16 scanline_now(void);   /* the scanline the picture is on: how far into the frame the work has got */

/* main.c */
extern u16 frame_count;   /* frames since the program started: the pictures animate by it */
extern u8 lights_on;      /* the player's cheat: the whole floor lit, everything on it shown (not the game's) */

/* picture.c */
void set_up_picture(void);
void draw_frame(void);
extern u16 draw_end_line;   /* the scanline the last frame's drawing ended on: it must stay in the blank */

/* cast.c */
void set_up_cast(void);
void draw_cast(void);

/* light.c */
void set_up_light(void);
void draw_light(void);

/* status.c */
void set_up_status(void);
void compose_status(void);
void send_status(void);
void status_floor_shown(u8 floor);
void show_view_layers(u8 shown);

/* HDMA, shared by light.c (the windows, channel 3) and status.c (the layers and the backdrop, 4 and 5);
   channel 7 is the library's. The enable register can't be read, so whoever writes it enables all. */
#define HDMA_CHANNELS ((1 << 3) | (1 << 4) | (1 << 5))
#define HDMA_REPEAT 0x80         /* a table entry's count with this bit: a line's own bytes each line */

/* player.c */
void game_frame(const Controls *controls);
void new_game(void);
void select_mode(void);
void match_out(void);
void flip_turn(void);
void start_drop(void);
void room_changed(void);

/* sprites.c */
void choose_sprite(Sprite *sprite);
u8 line_of(u8 y);
u8 on_screen(u8 line);

/* touching.c */
void set_up_columns(void);
void draw(const Sprite *sprite, u8 stick, Touches *touches);

/* doors.c */
void doorways(void);
u8 door_locked(u8 floor, u8 door);
u8 stairs_here(void);
u8 room_bound(u8 direction);

/* monsters.c */
u8 bit(u8 number);
u8 next_random(void);
u8 floor_index(u8 floor);
void move_monsters(void);
void scatter(void);
void follow_through_door(u8 room, u8 direction);
void follow_up_stairs(u8 room, u8 stairs_byte);

/* sounds.c */
void start_effect(u8 effect);
void sound_frame(void);
#define EFFECT_BLOCKED 2
#define EFFECT_BUMP 3
#define EFFECT_DOORWAY 4
#define EFFECT_DROP 5
#define EFFECT_PICK_UP 6
#define EFFECT_JOIN 7
#define EFFECT_NEW_ROOM 8
#define EFFECT_STAIRS_UP 9
#define EFFECT_STAIRS_DOWN 10
#define EFFECT_URN_WHOLE 11

#endif
