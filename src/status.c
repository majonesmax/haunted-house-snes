/* The status band (docs/plan.md, step 2): above the view, the matches used and the one burning, what's
   held, the urn so far and the lives; below it, the floor's name, the game and the floor number - the
   remaster's NES look's layout, in 4-colour tiles on the SNES's third layer, over the gradient panel the
   remaster's SNES look drew: here the backdrop colour, changed line by line by HDMA, with the floor's
   layers switched off on the band's lines the same way. The band is worked out again only when something
   it shows has changed, and sent to video memory in the next vertical blank. Everything here only reads
   the state. */
#include <snes.h>
#include "state.h"
#include "engine.h"
#include "mansion.h"
#include "art.h"
#include "status.h"

#define STATUS_LAYER 2
#define VRAM_STATUS_TILES 0x1000     /* words: 4-colour tiles, 8 words each; 256 tiles (the font, the
                                        band's pieces, the logo's big letters) */
#define VRAM_STATUS_MAP 0x1800       /* 32 x 32 tiles: 1K words (the screens' words too: screens.c) */
#define MAP_COLUMNS 32
#define MAP_ROWS 32
#define BAND_ROWS 4                  /* each band: 4 rows of tiles, 32 lines */
#define BAND_BELOW_ROW 24            /* the band below the view starts at this row of the map */
#define LAYER_DOWN 4                 /* the layer is scrolled down this far: a margin above the words */
#define VIEW_LINES 160               /* between the bands */
#define SCREEN_LINES 224
#define PRIORITY 0x2000              /* a map entry's bit: the tile in front of the floor's layers */
#define PALETTE_SHIFT 10             /* a map entry's palette number is here */
#define PIECES 0                     /* the palettes: the pieces' inks, and the words' */
#define WHITE 1
#define GREY 2
#define DIM 3
/* The band above the view: its rows and columns of tiles (the NES game's view.s). */
#define LABELS_ROW 0
#define VALUES_ROW 1
#define MATCHES_COLUMN 1             /* "MATCHES", and two digits under it... */
#define BAR_COLUMN 3                 /* ...then the burning match, three tiles */
#define BAR_TILES 3
#define FLAME 3                      /* the flame's width in pixels (tools/make_pictures.py) */
#define HOLD_LABEL_COLUMN 10
#define HOLD_SLOT_COLUMN 11
#define URN_LABEL_COLUMN 16
#define URN_SLOTS_COLUMN 15          /* three slots, two tiles each */
#define URN_PIECES 3
#define LIVES_LABEL_COLUMN 25
#define LIVES_EYES_COLUMN 25
#define LIVES_X_COLUMN 27
#define LIVES_DIGIT_COLUMN 28
/* The band below: the floor's name centred on its first row, the numbers two rows down. */
#define NAME_ROW 0
#define NUMBERS_ROW 2
#define GAME_LABEL_COLUMN 1
#define GAME_DIGIT_COLUMN 6
#define FLOOR_LABEL_COLUMN 24
#define FLOOR_DIGIT_COLUMN 30
#define BELOW_GROUND 'B'             /* a floor below the front door's is lettered, not numbered */
#define NO_MATCH 0xFF                /* the key's match time with no match lit */
#define KEY_BYTES 8

/* The HDMA tables (bank $7E, as the light's): the layers shown on each line - the floor's only between
   the bands - and the backdrop's colour, the panel's shade on each band line and black between. */
#define LAYERS_CHANNEL 4
#define SHADE_CHANNEL 5
#define HDMA_ONE_REGISTER 0          /* the transfer mode: a byte to one register */
#define HDMA_TWO_REGISTERS_TWICE 3   /* four bytes: two to one register, two to the next */
#define LAYERS_REGISTER 0x2C         /* TM: the main screen's layers */
#define COLOUR_REGISTER 0x21         /* CGADD, then CGDATA: a colour's number, then its two bytes */
#define BANK_WORK_RAM 0x7E
#define VIEW_LAYERS 0x17             /* BG1, BG2, BG3 and the sprites */
#define BAND_LAYERS 0x04             /* BG3 alone: a sprite at the view's edge stops there */
#define LOADING_LAYERS 0x14          /* while a floor's pictures arrive: BG3 and the sprites, BG1 and BG2 hidden */
#define MOST_LINES 127               /* an entry covers at most this many lines */
#define BACKDROP 0                   /* the backdrop's colour number */
#define SHADE_ENTRY 4                /* bytes: the colour number twice, then the colour's two bytes */
#define LAYERS_ENTRY 2               /* bytes: a count and the layers */
#define VIEW_LAYERS_FIRST (LAYERS_ENTRY + 1)   /* where the view's two entries keep the layers byte */
#define VIEW_LAYERS_SECOND (2 * LAYERS_ENTRY + 1)
static u8 layers_table[4 * LAYERS_ENTRY + 1];
/* The full screens' (screens.c): one layer setting for all the lines, and a black sky for the story and
   the help (the title's and the ending's skies are in the ROM: aim_sky, src/fast.asm). */
#define SCREEN_LAYERS_FIRST 1
#define SCREEN_LAYERS_SECOND 3
#define PICTURE_LAYERS 0x15          /* BG1, BG3 and the sprites (BG2, the glow, is on the sub-screen) */
#define WORDS_LAYERS 0x14            /* BG3 and the sprites: the story, the help, a picture on its way */
static u8 screen_layers_table[2 * LAYERS_ENTRY + 1];
static u8 black_sky_table[2 * (1 + SHADE_ENTRY) + 1];
u8 sky_which;                        /* what aim_sky aims at: 0 the title's sky, 1 the ending's... */
u16 sky_offset;                      /* ...and how far into the title's (a lightning frame's table) */
void aim_sky(void);
static u8 shade_table[2 * (1 + BAND_LINES * SHADE_ENTRY) + 2 * (1 + SHADE_ENTRY) + 1];

static u16 band_above[BAND_ROWS * MAP_COLUMNS];   /* the bands' map entries, as video memory wants them */
static u16 band_below[BAND_ROWS * MAP_COLUMNS];
static u8 band_changed;                           /* ...and whether they're yet to be sent */
u8 status_shown_key[KEY_BYTES];                   /* what the band above was last worked out from... */
u8 status_changed;                                /* ...and whether that differs now (src/fast.asm) */
void status_key_changed(void);
static u8 pieces_of_shape[9] = {0, 0, 1, 2, 4, 3, 5, 6, 7};   /* an urn shape's pieces, a bit each */
static u8 pieces_counted[8] = {0, 1, 1, 2, 1, 2, 2, 3};       /* how many bits */

/* --- writing the bands' entries ------------------------------------------------------------------- */
static void put_tile(u16 *band, u8 row, u8 column, u16 tile, u8 palette)
{
    band[(row << 5) + column] = tile | ((u16)palette << PALETTE_SHIFT) | PRIORITY;
}

static void put_text(u16 *band, u8 row, u8 column, const char *text, u8 palette)
{
    while (*text) {
        put_tile(band, row, column, font_tiles[*text - FONT_FIRST_LETTER], palette);
        column++;
        text++;
    }
}

static void put_digit(u16 *band, u8 row, u8 column, u8 value, u8 palette)
{
    put_tile(band, row, column, FONT_DIGITS + value, palette);
}

/* A slot's four tiles, at the values' rows. */
static void put_slot(u8 column, u16 first_tile)
{
    put_tile(band_above, VALUES_ROW, column, first_tile, PIECES);
    put_tile(band_above, VALUES_ROW, column + 1, first_tile + 1, PIECES);
    put_tile(band_above, VALUES_ROW + 1, column, first_tile + 2, PIECES);
    put_tile(band_above, VALUES_ROW + 1, column + 1, first_tile + 3, PIECES);
}

/* --- the band above ------------------------------------------------------------------------------- */
/* The match: its ember as long as the seconds left, the flame after it (the NES game's want_match_bar).
   The tile at this pixel: all ember; or the ember's end, with the flame starting; or the flame's spill. */
static u16 bar_tile(u8 pixel, u8 length)
{
    u8 spill;
    if (pixel + 7 < length) {
        return BAR_EMBER;
    }
    if (length >= pixel) {
        return BAR_END + (length - pixel);
    }
    spill = pixel - length;
    if (spill >= FLAME) {
        return 0;
    }
    return BAR_FLAME + (FLAME - spill);
}

static void want_matches(void)
{
    u8 used = RAM(MATCHES_USED);                     /* (two decimal digits in one byte) */
    u8 tile;
    u8 pixel = 0;
    put_digit(band_above, VALUES_ROW, MATCHES_COLUMN, used >> 4, WHITE);
    put_digit(band_above, VALUES_ROW, MATCHES_COLUMN + 1, used & 0x0F, WHITE);
    for (tile = 0; tile < BAR_TILES; tile++) {
        u16 wanted = 0;
        if (RAM(FLAGS) & MATCH_LIT) {
            wanted = bar_tile(pixel, RAM(MATCH_TIME));
        }
        put_tile(band_above, VALUES_ROW, BAR_COLUMN + tile, wanted, PIECES);
        pixel += 8;
    }
}

/* An urn piece's shape, for an item 2-4; 0 for anything else. */
static u8 shape_of(u8 item)
{
    if (item >= URN && item < URN + URN_PIECES) {
        return RAM(URN_SHAPES + item - URN);
    }
    return 0;
}

static u8 pieces_of(u8 shape)
{
    if (shape < 9) {
        return pieces_of_shape[shape];
    }
    return 0;
}

static void want_held(void)
{
    u8 carried = RAM(CARRIED);
    if (carried == NOTHING) {
        put_slot(HOLD_SLOT_COLUMN, SLOT_EMPTY);
    } else if (carried < URN) {
        put_slot(HOLD_SLOT_COLUMN, SLOT_ITEMS + (carried << 2));
    } else {
        put_slot(HOLD_SLOT_COLUMN, SLOT_ITEMS + (shape_of(carried) << 2));
    }
}

/* The urn so far (the remaster's rule): the pieces held, or else the biggest group of pieces joined
   together - a lone piece on the floor doesn't count. A slot for each piece, filled if it's in. */
static void want_urn(void)
{
    u8 best = 0;
    u8 piece;
    u8 carried = RAM(CARRIED);
    if (carried != NOTHING && carried >= URN) {
        best = pieces_of(shape_of(carried));
    } else {
        u8 item;
        for (item = URN; item < URN + URN_PIECES; item++) {
            u8 pieces = pieces_of(shape_of(item));
            if (pieces_counted[pieces] > pieces_counted[best]) {
                best = pieces;
            }
        }
        if (pieces_counted[best] < 2) {
            best = 0;
        }
    }
    for (piece = 0; piece < URN_PIECES; piece++) {
        u8 column = URN_SLOTS_COLUMN + (piece << 1);
        if (best & (1 << piece)) {
            put_slot(column, SLOT_ITEMS + ((piece + 2) << 2));   /* the piece alone: shape 2, 3 or 4 */
        } else {
            put_slot(column, SLOT_EMPTY);
        }
    }
}

static void want_lives(void)
{
    put_digit(band_above, VALUES_ROW, LIVES_DIGIT_COLUMN, RAM(LIVES), WHITE);
}

/* Each frame, once the game's frame is worked out: the band above, if anything it shows has changed
   (status_key_changed, src/fast.asm, looks: in C the looking alone cost a tenth of the frame). */
void compose_status(void)
{
    status_key_changed();
    if (status_changed == 0) {
        return;
    }
    want_matches();
    want_held();
    want_urn();
    want_lives();
    put_digit(band_below, NUMBERS_ROW, GAME_DIGIT_COLUMN, RAM(GAME_NUMBER) + 1, DIM);
    band_changed = 1;
}

/* --- the band below ------------------------------------------------------------------------------- */
/* The floor whose pictures are on the screen: its name, centred, and its number - 1 for the front
   door's floor and up from there, B for one below it. */
void status_floor_shown(u8 floor)
{
    const char *name = floor_names[floor];
    u8 length = 0;
    u8 column;
    for (column = 0; column < MAP_COLUMNS; column++) {
        band_below[(NAME_ROW << 5) + column] = 0;
    }
    while (name[length]) {
        length++;
    }
    put_text(band_below, NAME_ROW, (MAP_COLUMNS - length) >> 1, name, WHITE);
    if (floor >= FRONT_DOOR_FLOOR) {
        put_digit(band_below, NUMBERS_ROW, FLOOR_DIGIT_COLUMN, floor - FRONT_DOOR_FLOOR + 1, DIM);
    } else {
        put_tile(band_below, NUMBERS_ROW, FLOOR_DIGIT_COLUMN, font_tiles[BELOW_GROUND - FONT_FIRST_LETTER],
                 DIM);
    }
    band_changed = 1;
}

/* --- the layers and the panel --------------------------------------------------------------------- */
/* Whether the floor's layers show between the bands (not while a floor's pictures are arriving). */
void show_view_layers(u8 shown)
{
    u8 layers = LOADING_LAYERS;
    u8 screen_layers = WORDS_LAYERS;
    if (shown) {
        layers = VIEW_LAYERS;
        screen_layers = PICTURE_LAYERS;
    }
    layers_table[VIEW_LAYERS_FIRST] = layers;
    layers_table[VIEW_LAYERS_SECOND] = layers;
    if (screen_shown == SCREEN_STORY || screen_shown == SCREEN_HELP) {
        screen_layers = WORDS_LAYERS;    /* (words over the dark) */
    }
    screen_layers_table[SCREEN_LAYERS_FIRST] = screen_layers;
    screen_layers_table[SCREEN_LAYERS_SECOND] = screen_layers;
}

static u8 *shade_entries(u8 *table)
{
    u8 line;
    *table++ = HDMA_REPEAT | BAND_LINES;
    for (line = 0; line < BAND_LINES; line++) {
        u16 colour = band_shades[line];
        *table++ = BACKDROP;
        *table++ = BACKDROP;
        *table++ = (u8)colour;
        *table++ = (u8)(colour >> 8);
    }
    return table;
}

static u8 *black_entry(u8 *table, u8 lines)
{
    *table++ = lines;
    *table++ = BACKDROP;
    *table++ = BACKDROP;
    *table++ = 0;
    *table++ = 0;
    return table;
}

void aim_band_channels(void);
static void set_up_tables(void)
{
    u8 *table = layers_table;
    *table++ = BAND_LINES;
    *table++ = BAND_LAYERS;
    *table++ = MOST_LINES;
    *table++ = VIEW_LAYERS;
    *table++ = VIEW_LINES - MOST_LINES;
    *table++ = VIEW_LAYERS;
    *table++ = BAND_LINES;
    *table++ = BAND_LAYERS;
    *table = 0;
    table = shade_entries(shade_table);
    table = black_entry(table, MOST_LINES);
    table = black_entry(table, VIEW_LINES - MOST_LINES);
    table = shade_entries(table);
    *table = 0;
    table = screen_layers_table;
    *table++ = MOST_LINES;
    *table++ = WORDS_LAYERS;
    *table++ = SCREEN_LINES - MOST_LINES;
    *table++ = WORDS_LAYERS;
    *table = 0;
    table = black_entry(black_sky_table, MOST_LINES);
    table = black_entry(table, SCREEN_LINES - MOST_LINES);
    *table = 0;
    aim_band_channels();
}

/* The band's two HDMA channels at their tables: each frame, after any copies (the library's leave the
   channels aimed at what they copied). */
void aim_band_channels(void)
{
    REG_DMAP4 = HDMA_ONE_REGISTER;
    REG_BBAD4 = LAYERS_REGISTER;
    REG_A1T4LH = (u16)(screen_shown == SCREEN_PLAY ? layers_table : screen_layers_table);
    REG_A1B4 = BANK_WORK_RAM;
    if (screen_shown == SCREEN_TITLE || screen_shown == SCREEN_GAME_OVER || screen_shown == SCREEN_ENDING) {
        sky_which = screen_shown == SCREEN_ENDING;
        aim_sky();
        return;
    }
    REG_DMAP5 = HDMA_TWO_REGISTERS_TWICE;
    REG_BBAD5 = COLOUR_REGISTER;
    REG_A1T5LH = (u16)(screen_shown == SCREEN_PLAY ? shade_table : black_sky_table);
    REG_A1B5 = BANK_WORK_RAM;
}

/* --- set-up and sending --------------------------------------------------------------------------- */
static void clear_status_map(void)
{
    u16 entry;
    REG_VMAIN = 0x80;                /* the address steps on after each word */
    REG_VMADDLH = VRAM_STATUS_MAP;
    for (entry = 0; entry < MAP_COLUMNS * MAP_ROWS; entry++) {
        REG_VMDATALH = 0;
    }
}

void set_up_status(void)
{
    u16 entry;
    bgSetGfxPtr(STATUS_LAYER, VRAM_STATUS_TILES);
    bgSetMapPtr(STATUS_LAYER, VRAM_STATUS_MAP, SC_32x32);
    dmaCopyVram((u8 *)&status_tiles, VRAM_STATUS_TILES, (u16)(&status_tiles_end - &status_tiles));
    dmaCopyCGram((u8 *)&status_palette, 0, (u16)(&status_palette_end - &status_palette));
    clear_status_map();
    bgSetScroll(STATUS_LAYER, 0, (u16)(0 - LAYER_DOWN));
    bgSetEnable(STATUS_LAYER);
    for (entry = 0; entry < BAND_ROWS * MAP_COLUMNS; entry++) {
        band_above[entry] = 0;
        band_below[entry] = 0;
    }
    put_text(band_above, LABELS_ROW, MATCHES_COLUMN, "MATCHES", GREY);
    put_text(band_above, LABELS_ROW, HOLD_LABEL_COLUMN, "HOLD", GREY);
    put_text(band_above, LABELS_ROW, URN_LABEL_COLUMN, "URN", GREY);
    put_text(band_above, LABELS_ROW, LIVES_LABEL_COLUMN, "LIVES", GREY);
    put_tile(band_above, VALUES_ROW, LIVES_EYES_COLUMN, LIVES_EYES, PIECES);
    put_tile(band_above, VALUES_ROW, LIVES_EYES_COLUMN + 1, LIVES_EYES + 1, PIECES);
    put_text(band_above, VALUES_ROW, LIVES_X_COLUMN, "X", WHITE);
    put_text(band_below, NUMBERS_ROW, GAME_LABEL_COLUMN, "GAME", DIM);
    put_text(band_below, NUMBERS_ROW, FLOOR_LABEL_COLUMN, "FLOOR", DIM);
    for (entry = 0; entry < KEY_BYTES; entry++) {
        status_shown_key[entry] = NO_MATCH;   /* (lives are never 0xFF: the first frame works it out) */
    }
    set_up_tables();
    show_view_layers(0);
    band_changed = 1;
}

/* The band's four palettes to colours 0-15 by DMA (the source is ROM: the library's copy serves). */
static void send_colours(void)
{
    dmaCopyCGram((u8 *)&status_palette, 0, (u16)(&status_palette_end - &status_palette));
}

/* A band's entries to video memory by DMA (the library's copy takes the bank from a pointer, and a
   pointer to work RAM doesn't carry it). */
#define DMA_TWO_REGISTERS 1          /* the transfer mode: bytes to two registers in turn */
#define VRAM_DATA_REGISTER 0x18      /* VMDATAL, then VMDATAH */
#define VRAM_STEP_AFTER_HIGH 0x80    /* VMAIN: the address steps on after each word */
#define START_CHANNEL_0 1
void send_words_map(u8 *source, u16 address, u16 size)
{
    REG_VMAIN = VRAM_STEP_AFTER_HIGH;
    REG_VMADDLH = address;
    REG_DMAP0 = DMA_TWO_REGISTERS;
    REG_BBAD0 = VRAM_DATA_REGISTER;
    REG_A1T0LH = (u16)source;
    REG_A1B0 = BANK_WORK_RAM;
    REG_DAS0LH = size;
    REG_MDMAEN = START_CHANNEL_0;
}

static void send_band(u16 *band, u16 address)
{
    send_words_map((u8 *)band, address, BAND_ROWS * MAP_COLUMNS * 2);
}

/* Back to play from a screen: the bands sent again (the screen's words were over them). */
void status_show_again(void)
{
    band_changed = 1;
}

/* Each frame, in the vertical blank: the band's colours, and the bands to video memory if they've changed.
   (The colours every frame: the backdrop's HDMA leaves the colour address at colour 1, and once, in the
   first picture after start-up, a stray write we haven't traced landed there. 32 bytes cost a fraction of
   a scanline, and nothing stray can stay.) */
void send_status(void)
{
    send_colours();
    if (band_changed == 0 || screen_shown != SCREEN_PLAY) {
        return;
    }
    send_band(band_above, VRAM_STATUS_MAP);
    send_band(band_below, VRAM_STATUS_MAP + BAND_BELOW_ROW * MAP_COLUMNS);
    band_changed = 0;
}
