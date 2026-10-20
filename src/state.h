/* The game's state: the 2600's 128 bytes of RAM, kept here with the same meanings at the same offsets, so
   the checks can compare it byte for byte with the remaster's model (docs/plan.md, "How the engine is
   checked"). RAM(address) is a byte by its 2600 address, $80-$FF; the names are the spec's. */
#ifndef STATE_H
#define STATE_H
#include <snes.h>

extern u8 game_ram[128];
#define RAM(address) (game_ram[(address) - 0x80])

/* --- the bytes, by their 2600 addresses --- */
#define DEATH_TIMER 0x80      /* $FF when caught, counting down while the eyes roll */
#define DROP_TRIES 0x81       /* 5 when an item is dropped, counting down the spots tried */
#define MATCHES_USED 0x82     /* BCD: the score */
#define MONSTERS_HERE 0x83    /* monsters in the player's room, counted every frame */
#define COLOUR_CYCLE 0x84     /* bit 4: attract mode (the colours drift) */
#define MONSTER_SHOWN 0x85    /* the monster drawn this frame, in turn; past the last one: the stairs */
#define ITEM_SHOWN 0x86       /* the item drawn this frame, in turn */
#define SECOND_COUNTER 0x87   /* 60 frames to a second of the match */
#define DOORWAY 0x88          /* bit 7: in a doorway; low bits: its direction */
#define CLOCK 0x89            /* +1 every frame */
#define FLAGS 0x8A            /* bit 7 monster turn, bit 6 match lit, bit 0 won */
#define ROOM_TOP 0x8B         /* the room's y limits (0: the floor's edge instead) */
#define ROOM_BOTTOM 0x8C
#define FLOOR 0x8D
#define JOYSTICK 0x8E         /* bit 7 right, 6 left, 5 down, 4 up (read last frame) */
#define THUNDER 0x8F          /* dying: frames left of this rumble */
#define SOUND_TIME 0x90       /* frames left of the effect */
#define BLOCKED 0x91          /* bits 6/7 stop movement across / up and down (a locked door) */
#define MOOD_DIRECTION 0x92
#define SOUND 0x93            /* the effect playing, 2-11; 0 none */
#define FOLLOWING 0x94        /* a bit per monster sent after the player */
#define ARRIVED 0x95          /* a bit per monster at its waypoint */
#define LIVES 0x96
#define ROOM_BEYOND 0x97      /* through the doorway the player stands in; $FF otherwise */
#define MOOD_PITCH 0x98       /* the monster-near noise; $7F silent */
#define GAME_STATE 0x99       /* $00 playing, $01 dying, $02 just reset, $40 select/game over, $44 won */
#define CARRIED 0x9A          /* an item, or $FF for nothing */
#define STAIRS 0x9B           /* $0F none; else the edge + 4 if up; bit 7 at the edge, bit 6 just used */
#define ROOM 0x9C
#define URN_SHAPES 0x9D       /* +0..2: the shapes of items 2, 3, 4 */
#define ITEM_FLOOR 0xA0       /* + item 0-4 */
#define MONSTER_FLOOR 0xA5    /* + monster 0-4 */
#define POS_X 0xAA
#define ITEM_X 0xAB
#define MONSTER_X 0xB0
#define POS_Y 0xB5
#define ITEM_Y 0xB6
#define MONSTER_Y 0xBB
#define MONSTER_ROUTE 0xC0    /* a monster's plan: direction << 6 | kind << 4 | target */
#define MONSTER_ROOM 0xC5
#define KILLED_BY 0xCA
#define EYES_LINE 0xCB        /* the screen line the eyes are drawn on */
#define GAME_NUMBER 0xCC      /* 0-8 for games 1-9 */
#define MASK_X 0xCF           /* the two blocks in the middle wall's gap (kept for the check) */
#define SPRITE_X 0xDC         /* this frame's sprite, as the drawing reads it... */
#define MASK_X_2 0xDE
#define MATCH_TIME 0xDF       /* seconds left on the match */
#define SPRITE_POINTER 0xE1   /* ...its picture (low byte: the shapes page; high byte $FE) */
#define SELECT_DELAY 0xE5
#define BUTTON_HISTORY 0xE6   /* a bit per frame, 0 pressed; $7F is a press */
#define STEP_X 0xE7           /* the step the player tried this frame */
#define STEP_Y 0xE8
#define DROPPED 0xE9          /* the item the drop search is placing */
#define LAST_MONSTER 0xEA     /* 2 in games 1-4, 4 in games 5-9 */
#define RANDOM_LOW 0xEB       /* the 16-bit shift register */
#define RANDOM_HIGH 0xEC
#define SPRITE_HEIGHT 0xED
#define SPRITE_LINE 0xEF      /* the line of the sprite's bottom row */

/* --- the values the game gives its bytes --- */
#define PLAYING 0x00
#define DYING 0x01
#define JUST_RESET 0x02
#define SELECTING 0x40
#define WON 0x44
#define NO_PLAY 0x43          /* GAME_STATE bits that stop the player moving */
#define NO_LOGIC 0x40         /* the bit that stops everything after the picture */
#define WON_BIT 0x04
#define MATCH_LIT 0x40        /* FLAGS */
#define MONSTER_TURN 0x80
#define WON_FLAG 0x01
#define KEEP_ON_MATCH_OUT 0x07
#define NO_STAIRS 0x0F        /* STAIRS */
#define AT_EDGE 0x80
#define JUST_USED_STAIRS 0x40
#define GOES_UP 0x04
#define IN_DOORWAY 0x80
#define NOTHING 0xFF
#define KEY 0
#define SCEPTER 1
#define URN 2                 /* items 2-4 are the urn's pieces */
#define WHOLE_URN 8
#define JOINED 0xFF
#define GHOST 0
#define BAT 1
#define STICK_RIGHT 0x80      /* the stick, as JOYSTICK holds it */
#define STICK_LEFT 0x40
#define STICK_DOWN 0x20
#define STICK_UP 0x10
#define ATTRACT 0x10          /* COLOUR_CYCLE: the colours drift */
#define MOOD_SILENT 0x7F

#endif
