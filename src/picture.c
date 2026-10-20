/* The picture (docs/plan.md, step 2): the floor on two scrolling layers - the walls on one, the floor on
   the other, in 16-colour tiles the remaster's SNES look drew (tools/make_pictures.py) - with the view where the
   game's own camera puts it. Everything here only reads the state; nothing here changes the game. */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "art.h"

/* Video memory, in words (the SNES counts it so): the two layers' maps, the status band's tiles and
   map (status.c), the floors' tiles, the sprites'. */
#define VRAM_WALLS_MAP 0x0000    /* 32 x 64 tiles: 4K */
#define VRAM_FLOOR_MAP 0x0800
#define VRAM_STATUS 0x1000       /* the band's tiles and map: 2K */
#define VRAM_TILES 0x2000        /* the floors' tiles: up to 32K */
#define VRAM_SPRITES 0x6000      /* 16K */
#define WALLS_LAYER 0            /* BG1: above the floor */
#define FLOOR_LAYER 1            /* BG2 */
#define STATUS_LAYER 2           /* BG3: in front of both, where it has anything to show */
#define FLOOR_PALETTES_AT 16     /* colours: BG palette 1; the band has palette 0 */
#define FLOOR_PALETTES_SIZE (7 * 16 * 2)
#define MAP_SIZE (32 * 64 * 2)
/* The screen (the remaster's looks/layout.py, on the SNES's 224 lines): the status band, then the view -
   the original's 160 units across and 80 lines up, 1.5 pixels a unit across and 2 down, 240 x 160 - then
   the band below. */
#define VIEW_X 8
#define VIEW_Y 32
#define VIEW_LINES 80
#define UNIT_Y 2
#define FLOOR_LINES 256
#define NO_FLOOR 0xFF

#define LOAD_CHUNK 4096          /* bytes copied to video memory in one vertical blank: there's time for
                                    about 6K, less the sprites' own copy */

static u8 shown_floor = NO_FLOOR;   /* the floor whose pictures are in video memory... */
static u8 loading_floor = NO_FLOOR; /* ...and the one on its way there, a piece a frame, screen off */
static u8 loading_step;             /* which piece: the tiles, the walls' map, the floor's map, the palettes */
static u16 loaded;                  /* bytes of the piece copied so far */
static FloorPictures loading;
u16 draw_end_line;                  /* the scanline the picture's drawing ended on (the blank is 225-261) */

void set_up_picture(void)
{
    setMode(BG_MODE1, BG3_MODE1_PRIORITY_HIGH);
    bgSetGfxPtr(WALLS_LAYER, VRAM_TILES);
    bgSetGfxPtr(FLOOR_LAYER, VRAM_TILES);
    bgSetMapPtr(WALLS_LAYER, VRAM_WALLS_MAP, SC_32x64);
    bgSetMapPtr(FLOOR_LAYER, VRAM_FLOOR_MAP, SC_32x64);
    set_up_status();
    REG_BG1HOFS = (u8)(0 - VIEW_X);    /* the layers start VIEW_X in, for good: a 10-bit scroll */
    REG_BG1HOFS = (u8)((0 - VIEW_X) >> 8) & 0x03;
    REG_BG2HOFS = (u8)(0 - VIEW_X);
    REG_BG2HOFS = (u8)((0 - VIEW_X) >> 8) & 0x03;
    oamInitGfxSet((u8 *)&cast_tiles, (u16)(&cast_tiles_end - &cast_tiles), (u8 *)&cast_palettes,
                  (u16)(&cast_palettes_end - &cast_palettes), 0, VRAM_SPRITES, OBJ_SIZE16_L32);
    set_up_cast();
    set_up_light();
    setPaletteColor(0, 0);   /* the backdrop: black, the dark beyond the light */
    shown_floor = NO_FLOOR;
    loading_floor = NO_FLOOR;
}

/* Start bringing a floor's pictures into video memory. The SNES takes them only in the vertical blank,
   and not all at once, so they come a piece a frame with the floor's layers hidden, and the game goes on
   meanwhile. */
static void start_loading(u8 floor)
{
    floor_art(floor, &loading);
    loading_floor = floor;
    loading_step = 0;
    loaded = 0;
    show_view_layers(0);         /* (not the screen off: that changes the frame's timing underfoot) */
}

/* One piece of a loading floor, in this vertical blank: at most LOAD_CHUNK bytes of the tiles, then the
   walls' map, the floor's map and the palettes; the layers show again when all is there. */
static void load_some(void)
{
    u8 *source;
    u16 size;
    u16 at;
    switch (loading_step) {
    case 0: source = loading.tiles; size = loading.tiles_size; at = VRAM_TILES; break;
    case 1: source = loading.walls_map; size = MAP_SIZE; at = VRAM_WALLS_MAP; break;
    case 2: source = loading.floor_map; size = MAP_SIZE; at = VRAM_FLOOR_MAP; break;
    default: source = loading.palettes; size = FLOOR_PALETTES_SIZE; at = FLOOR_PALETTES_AT; break;
    }
    if (loaded < size) {
        u16 piece = size - loaded;
        if (piece > LOAD_CHUNK) {
            piece = LOAD_CHUNK;
        }
        if (loading_step == 3) {
            dmaCopyCGram(source + loaded, at + loaded, piece);
        } else {
            dmaCopyVram(source + loaded, at + loaded / 2, piece);   /* (video memory is counted in words) */
        }
        loaded += piece;
    }
    if (loaded >= size) {
        loading_step++;
        loaded = 0;
        if (loading_step > 3) {
            shown_floor = loading_floor;
            loading_floor = NO_FLOOR;
            show_view_layers(1);
            status_floor_shown(shown_floor);
        }
    }
}

/* The picture's row at the top of the view: the view's top line is the eyes' line plus what's above it
   (the remaster's looks/layout.py, view_top_row). */
static u16 view_top_row(void)
{
    u8 view_bottom = (u8)(RAM(POS_Y) - RAM(EYES_LINE));
    u16 top_line = view_bottom + VIEW_LINES - 1;
    return (u16)(FLOOR_LINES - 1 - top_line) * UNIT_Y;
}

/* Each frame, in the vertical blank: the layers scrolled to the view, and the rest of the picture. */
void draw_frame(void)
{
    u16 scroll_y;
    if (loading_floor != NO_FLOOR) {
        load_some();
    } else if (RAM(FLOOR) != shown_floor && RAM(FLOOR) < ART_FLOORS) {
        start_loading(RAM(FLOOR));
    }
    send_status();            /* (video memory takes writes only in the blank: those come first) */
    scroll_y = view_top_row() - VIEW_Y;
    REG_BG1VOFS = (u8)scroll_y;        /* (each scroll register takes its low byte, then its high) */
    REG_BG1VOFS = (u8)(scroll_y >> 8);
    REG_BG2VOFS = (u8)scroll_y;
    REG_BG2VOFS = (u8)(scroll_y >> 8);
    draw_light();             /* (its HDMA table is read from the top of the picture: before the cast, */
    draw_cast();              /* whose sprite table goes to the console in the next blank) */
    draw_end_line = scanline_now();
}
