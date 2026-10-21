"""The picture's tiles, made from the remaster's SNES look: each floor drawn by the remaster's own scenery
code (its looks/scenery.py, through its SNES look and the nocturne pack's pictures), then cut into the
SNES's 16-colour tiles on two layers - the walls (their tops, faces and decorations) on one, the floor on
the other - so the light can treat them apart.

Makes, in build/<kind>/art/:
  floorN_tiles.bin      the floor's tiles, 4 bits a pixel (both layers share them)
  floorN_walls.bin      the walls layer's map, 32 x 64 tiles (the floor is 240 x 512 pixels)
  floorN_floor.bin      the floor layer's map
  floorN_palette.bin    its palettes: 7 of 16 colours (BG palettes 1-7; 0 is the status band's)
  cast_tiles.bin        the cast's sprite sheet (16 x 16 blocks), and cast_palettes.bin its 8 palettes
  status_tiles.bin      the status band's 4-colour tiles, and status_palette.bin its 4 palettes
  src/art_data.asm      binds them all into the ROM
  art.h                 declares them, and floor_art() gives the engine a floor's; cast.h, each sprite's
                        place; status.h, the band's tile numbers, font, panel shades and the floors' names

Usage: python tools/make_pictures.py [--faithful]      (tools/build.py runs it)
"""

import os
import sys
from typing import NamedTuple

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NES = os.path.join(os.path.dirname(ROOT), "haunted-house-nes")
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
sys.path.insert(0, REMASTER)
sys.path.insert(0, os.path.join(NES, "tools"))
import mansion as M  # noqa: E402
import rom_image as I  # noqa: E402
import make_pack  # noqa: E402
import make_screens  # noqa: E402

import content  # noqa: E402
import looks  # noqa: E402
from looks.nes import look as nes_look  # noqa: E402
from looks.snes import look as snes_look  # noqa: E402
from shared import hud  # noqa: E402
from game import rom as R  # noqa: E402

TILE = 8
MAP_COLUMNS, MAP_ROWS = 32, 64      # the map: the floor's 240 x 512 picture, in a 256 x 512 map
PALETTES = 7                        # BG palettes 1-7 are the floor's; 0 is the status band's
FIRST_PALETTE = 1
COLOURS_PER_PALETTE = 15            # and colour 0, see-through
BLANK = np.zeros((TILE, TILE), np.uint8)
Picture = np.ndarray
Indices = np.ndarray


class FloorArt(NamedTuple):
    tiles: bytes          # 4bpp, 32 bytes each
    walls_map: bytes      # 32 x 64 entries of 2 bytes
    floor_map: bytes
    palettes: bytes       # 7 x 16 colours of 2 bytes (15-bit BGR)


# --- the floors, drawn by the look -------------------------------------------------------------------
def floor_looks(shareable: bool) -> tuple[list["looks.FloorLook"], list[str]]:
    """The look that draws each floor, and the floors' names (as the NES game's tools/make_pictures.py)."""
    if not shareable:
        look = looks.make("snes", R.load())
        return [look] * R.FLOOR_COUNT, list(look.pack.info["floors"])
    make_pack.main()
    with open(make_pack.MANSION_TEXT) as mansion_file:
        mansion_text = mansion_file.read()
    floors = M.parse(mansion_text)
    ground_floor = M.front_door_floor(mansion_text)
    per_floor = [M.floor_tables(floor) for floor in floors]
    tables = {label: b"".join(made[label] for made in per_floor) for label in per_floor[0]}
    pack = content.Pack(make_pack.OUTPUT, bytes(I.IMAGE_SIZE))
    images = [I.floor_image(tables, number, [], bytes(I.RANDOM_BYTES // 8)) for number in range(len(floors))]
    stand_ins = [R.Floors([image], {}, ground_floor) for image in images]
    return [looks.LOOKS["snes"](pack, stand_in) for stand_in in stand_ins], [floor.name for floor in floors]


# --- colours into palettes ---------------------------------------------------------------------------
# The SNES gives the floor seven palettes of 15 colours, and each tile picks one. A floor's picture has
# some 50 colours, mixed across its tiles in too many ways for every tile to find all its colours in one
# palette; so each tile takes the palette that costs it least, where a colour the palette has no room for
# becomes the palette's nearest, and palettes grow from the tiles that chose them.
FEWER_COLOURS = 48          # a floor's picture is first brought down to this many (PIL's median cut)
SCREEN_PICTURE_COLOURS = 48   # a screen's picture is brought down to this many
NEW_PALETTE_COST = 24       # a tile whose best palette costs more than this a pixel starts a new one
Colour = tuple[int, int, int]
TileColours = dict[Colour, int]    # a tile's colours, with how many pixels of each


def snes_colour(rgb: Colour) -> int:
    """15-bit BGR: 5 bits each, blue highest."""
    red, green, blue = (int(channel) >> 3 for channel in rgb)
    return blue << 10 | green << 5 | red


def quantized(picture: Picture, count: int) -> Picture:
    image = Image.fromarray(picture[..., :3].astype(np.uint8), "RGB")
    fewer = image.quantize(colors=count, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    return np.asarray(fewer.convert("RGB"))


def as_colour(values: np.ndarray) -> Colour:
    red, green, blue = (int(channel) for channel in values)
    return red, green, blue


def distance(colour: Colour, other: Colour) -> float:
    return sum((mine - theirs) ** 2 for mine, theirs in zip(colour, other)) ** 0.5


def nearest(colour: Colour, among: list[Colour]) -> Colour:
    return min(among, key=lambda other: distance(colour, other))


def fit_tiles(picture: Picture, drawn: np.ndarray) -> Picture:
    """The picture with no tile of more than 15 colours: in a tile with more, its rarest colours become
    the nearest of the rest (a palette holds 15, and a tile takes one palette)."""
    out = picture.copy()
    for row in range(MAP_ROWS):
        for column in range(MAP_COLUMNS):
            top, left = row * TILE, column * TILE
            block = out[top:top + TILE, left:left + TILE]
            mask = drawn[top:top + TILE, left:left + TILE]
            colours, counts = np.unique(block[mask].reshape(-1, 3), axis=0, return_counts=True)
            if len(colours) <= COLOURS_PER_PALETTE:
                continue
            order = np.argsort(-counts)
            kept = [as_colour(colours[index]) for index in order[:COLOURS_PER_PALETTE]]
            for index in order[COLOURS_PER_PALETTE:]:
                rare = as_colour(colours[index])
                where = mask & (block == rare).all(axis=2)
                block[where] = nearest(rare, kept)
    return out


def tile_colours(picture: Picture, drawn: np.ndarray) -> list[TileColours]:
    """Each 8 x 8 tile's colours (where drawn) and their pixel counts, the tiles row by row."""
    counted = []
    for row in range(MAP_ROWS):
        for column in range(MAP_COLUMNS):
            top, left = row * TILE, column * TILE
            block = picture[top:top + TILE, left:left + TILE]
            mask = drawn[top:top + TILE, left:left + TILE]
            colours, counts = np.unique(block[mask].reshape(-1, 3), axis=0, return_counts=True)
            counted.append({as_colour(colour): int(count) for colour, count in zip(colours, counts)})
    return counted


def wanted_first(tile: TileColours, palette: list[Colour]) -> list[Colour]:
    """The tile's colours the palette lacks, the ones it most needs first: the farthest from any it has,
    or with nothing there yet, the ones with the most pixels."""
    missing = [colour for colour in tile if colour not in palette]
    if palette:
        return sorted(missing, key=lambda colour: -distance(colour, nearest(colour, palette)))
    return sorted(missing, key=lambda colour: -tile[colour])


def cost_of(tile: TileColours, palette: list[Colour]) -> float:
    """What a tile loses a pixel taking this palette: its colours the palette has no room for become the
    palette's nearest, and this is how far they move, over all the tile's pixels."""
    room = COLOURS_PER_PALETTE - len(palette)
    pixels = sum(tile.values())
    lost = sum(tile[colour] * distance(colour, nearest(colour, palette))
               for colour in wanted_first(tile, palette)[room:])
    return lost / pixels if pixels else 0.0


def take_in(tile: TileColours, palette: list[Colour]) -> None:
    """Add the tile's colours the palette has room for, the ones it most needs first."""
    for colour in wanted_first(tile, palette)[:COLOURS_PER_PALETTE - len(palette)]:
        palette.append(colour)


def choose_palettes(tiles: list[TileColours]) -> tuple[list[list[Colour]], list[int]]:
    """The palettes, and each tile's: the tiles with the most pixels of most colours first."""
    palettes: list[list[Colour]] = []
    chosen = [0] * len(tiles)
    order = sorted(range(len(tiles)), key=lambda index: (-len(tiles[index]), -sum(tiles[index].values())))
    for index in order:
        tile = tiles[index]
        if not tile:
            continue
        costs = [cost_of(tile, palette) for palette in palettes]
        best = min(range(len(palettes)), key=lambda which: costs[which]) if palettes else None
        if best is None or (costs[best] > NEW_PALETTE_COST and len(palettes) < PALETTES):
            palettes.append([])
            best = len(palettes) - 1
        take_in(tile, palettes[best])
        chosen[index] = best
    return palettes, chosen


# --- tiles -------------------------------------------------------------------------------------------
def tile_bytes(indices: Indices) -> bytes:
    """An 8 x 8 tile of colour indices 0-15 as the SNES keeps it: bitplanes 0 and 1 row by row, then 2
    and 3."""
    out = bytearray()
    for planes in ((0, 1), (2, 3)):
        for row in range(TILE):
            for plane in planes:
                bits = 0
                for column in range(TILE):
                    bits |= ((int(indices[row, column]) >> plane) & 1) << (7 - column)
                out.append(bits)
    return bytes(out)


class TileSet:
    """The tiles so far, found again by their pixels in any flip."""

    def __init__(self) -> None:
        self.tiles: list[bytes] = [tile_bytes(BLANK)]
        self.found: dict[bytes, tuple[int, int, int]] = {tile_bytes(BLANK): (0, 0, 0)}

    def place(self, indices: Indices) -> tuple[int, int, int]:
        """(tile number, flipped across, flipped down) for a tile of indices, adding it if it's new."""
        key = tile_bytes(indices)
        if key in self.found:
            return self.found[key]
        number = len(self.tiles)
        self.tiles.append(key)
        for across in (0, 1):
            for down in (0, 1):
                flipped = indices[::-1] if down else indices
                flipped = flipped[:, ::-1] if across else flipped
                self.found.setdefault(tile_bytes(flipped), (number, across, down))
        return number, 0, 0


def map_entry(tile: int, palette: int, across: int, down: int, priority: int) -> int:
    return tile | palette << 10 | priority << 13 | across << 14 | down << 15


def tile_indices(block: Picture, mask: np.ndarray, palette: list[Colour]) -> Indices:
    """A tile's pixels as indices in its palette: each its nearest colour, 0 where not drawn."""
    index_of = {colour: number + 1 for number, colour in enumerate(palette)}
    indices = np.zeros((TILE, TILE), np.uint8)
    for y in range(TILE):
        for x in range(TILE):
            if mask[y, x]:
                indices[y, x] = index_of[nearest(as_colour(block[y, x]), palette)]
    return indices


def layer_map(picture: Picture, drawn: np.ndarray, palettes: list[list[Colour]], chosen: list[int],
              tiles: TileSet, priority: int) -> bytes:
    """A layer's map: each tile's pixels as indices in its palette, placed in the tile set."""
    entries = []
    for row in range(MAP_ROWS):
        for column in range(MAP_COLUMNS):
            top, left = row * TILE, column * TILE
            block = picture[top:top + TILE, left:left + TILE]
            mask = drawn[top:top + TILE, left:left + TILE]
            if not mask.any():
                entries.append(map_entry(0, 0, 0, 0, priority))
                continue
            palette = chosen[row * MAP_COLUMNS + column]
            number, across, down = tiles.place(tile_indices(block, mask, palettes[palette]))
            entries.append(map_entry(number, FIRST_PALETTE + palette, across, down, priority))
    return b"".join(entry.to_bytes(2, "little") for entry in entries)


def padded(picture: Picture) -> Picture:
    """The floor's 240-wide picture in the map's 256 columns."""
    height, width = picture.shape[:2]
    out = np.zeros((MAP_ROWS * TILE, MAP_COLUMNS * TILE) + picture.shape[2:], picture.dtype)
    out[:height, :width] = picture
    return out


def floor_art(look: "looks.FloorLook", floor: int) -> FloorArt:
    scene = look.scene(floor)
    walls = padded(scene.walls)
    drawn = np.zeros(walls.shape, bool)
    drawn[:scene.full.shape[0], :scene.full.shape[1]] = True
    picture = fit_tiles(quantized(padded(scene.full), FEWER_COLOURS), drawn)
    walls_drawn, floor_drawn = drawn & walls, drawn & ~walls
    walls_tiles, floor_tiles = tile_colours(picture, walls_drawn), tile_colours(picture, floor_drawn)
    palettes, chosen = choose_palettes(walls_tiles + floor_tiles)
    tiles = TileSet()
    walls_map = layer_map(picture, walls_drawn, palettes, chosen[:len(walls_tiles)], tiles, priority=1)
    floor_map = layer_map(picture, floor_drawn, palettes, chosen[len(walls_tiles):], tiles, priority=0)
    return FloorArt(b"".join(tiles.tiles), walls_map, floor_map, palette_bytes(palettes))


def palette_bytes(palettes: list[list[Colour]]) -> bytes:
    """The BG palettes 1-7, each colour 0 see-through then up to 15 colours, as 15-bit BGR."""
    out = bytearray()
    for palette in palettes + [[]] * (PALETTES - len(palettes)):
        colours = [0] + [snes_colour(colour) for colour in palette]
        colours += [0] * (16 - len(colours))
        out += b"".join(colour.to_bytes(2, "little") for colour in colours)
    return bytes(out)


def screen_art(scene: "make_screens.ScreenScene") -> FloorArt:
    """A full screen's picture set (tools/make_screens.py): its picture on the first layer, the glow it
    adds to the sky on the second; one tile set, one set of palettes, as a floor's."""
    top_drawn, glow_drawn = padded(scene.drawn), padded(scene.glowing)
    top = padded(np.where(scene.drawn[..., None], scene.picture, 0).astype(np.uint8))
    glow = padded(np.where(scene.glowing[..., None], scene.glow, 0).astype(np.uint8))
    top = fit_tiles(quantized(top, SCREEN_PICTURE_COLOURS), top_drawn)   # (the glow has its 15 shades
    glow = fit_tiles(glow, glow_drawn)                                   # already: one palette's worth)
    top_tiles, glow_tiles = tile_colours(top, top_drawn), tile_colours(glow, glow_drawn)
    palettes, chosen = choose_palettes(top_tiles + glow_tiles)
    tiles = TileSet()
    top_map = layer_map(top, top_drawn, palettes, chosen[:len(top_tiles)], tiles, priority=1)
    glow_map = layer_map(glow, glow_drawn, palettes, chosen[len(top_tiles):], tiles, priority=0)
    return FloorArt(b"".join(tiles.tiles), top_map, glow_map, palette_bytes(palettes))


# --- the cast: sprites -------------------------------------------------------------------------------
# Each picture through the look's adapt() (15-bit colour, soft outlines, at most 15 colours), cut into
# 16 x 16 blocks (the one sprite size used) on a sheet of 8 blocks a row; the pictures share 8 palettes,
# the ghost's its own, so colour math can make it see-through. (cast name, frames to keep): a creature's
# left-facing pictures serve for the right, mirrored, as the look does.
CAST = [("eyes_centre", [0]), ("eyes_left", [0]), ("eyes_right", [0]), ("eyes_up", [0]), ("eyes_down", [0]),
        ("eyes_blink", [0]), ("hood_right", [0]), ("match_hand_right", [0, 1]),
        ("ghost_down", [0, 1]), ("ghost_left", [0, 1]), ("ghost_up", [0, 1]),
        ("bat_down", [0, 1, 2, 3]), ("bat_left", [0, 1, 2, 3]), ("bat_up", [0, 1, 2, 3])]
CAST += [(f"tarantula{kind}_{way}", [0, 1]) for kind in (2, 3, 4) for way in ("down", "left", "up", "right")]
CAST += [("key", [0]), ("scepter", [0])] + [(f"urn{shape}", [0, 3, 6, 9]) for shape in range(2, 9)]
CAST += [("stairs_up", [0]), ("stairs_down", [0])]
BLOCK = 16
SHEET_BLOCKS_ACROSS = 8          # a row of the sheet: 8 blocks, 128 pixels, 2 rows of 16 tiles
SHEET_BLOCK_ROWS = 16            # 128 blocks: the sprites' 16K of video memory
CAST_PALETTES = 8
GHOST_PALETTE = 7                # colour math is for sprites with palettes 4-7: the ghost's, alone


class CastPicture(NamedTuple):
    name: str
    frame: int
    blocks_wide: int
    blocks_high: int
    palette: int
    first_block: int


def blocks_of(picture: Picture) -> tuple[int, int]:
    height, width = picture.shape[:2]
    return (width + BLOCK - 1) // BLOCK, (height + BLOCK - 1) // BLOCK


def in_blocks(picture: Picture) -> Picture:
    """The picture (RGBA) centred in a whole number of 16 x 16 blocks."""
    wide, high = blocks_of(picture)
    out = np.zeros((high * BLOCK, wide * BLOCK, 4), np.uint8)
    top, left = (high * BLOCK - picture.shape[0]) // 2, (wide * BLOCK - picture.shape[1]) // 2
    out[top:top + picture.shape[0], left:left + picture.shape[1]] = picture
    return out


def picture_colours(picture: Picture) -> TileColours:
    solid = picture[..., 3] > 0
    colours, counts = np.unique(picture[solid][:, :3].reshape(-1, 3), axis=0, return_counts=True)
    return {as_colour(colour): int(count) for colour, count in zip(colours, counts)}


def cast_pictures(look: "looks.FloorLook") -> list[tuple[str, int, Picture]]:
    """(name, frame, the picture in blocks) for every cast picture kept, and the screens' own."""
    pictures = []
    for name, frames in CAST:
        for frame in frames:
            pictures.append((name, frame, in_blocks(look.adapt(look.pack.cast.must(name)[frame]))))
    return pictures + [(name, 0, in_blocks(picture)) for name, picture in screen_sprites(look)]


RAIN = (110, 120, 170)           # the SNES look's rain: a streak of 4 pixels slanting a pixel left
RAIN_STREAK = [(0, 1), (1, 1), (2, 0), (3, 0)]   # (down, across) of each
ROOM_MARGIN = 1                  # the dark room round the eyes in the tower window
NEAR_BLACK = (8, 8, 8)           # (a sprite pixel of pure black, 0, came out bright blue: not understood -
                                 # docs/decisions.md - so the window's dark is one step above it)


def solid(height: int, width: int, colour: Colour) -> Picture:
    picture = np.zeros((height, width, 4), np.uint8)
    picture[..., :3] = colour
    picture[..., 3] = 255
    return picture


def screen_sprites(look: "looks.FloorLook") -> list[tuple[str, Picture]]:
    """The screens' sprites: a raindrop; the dark room behind the eyes in the tower window (the remaster
    clears it black round them); the window with its light out, for game over."""
    drop = np.zeros((4, 2, 4), np.uint8)
    for down, across in RAIN_STREAK:
        drop[down, across, :3] = RAIN
        drop[down, across, 3] = 255
    eyes = look.adapt(look.pack.cast.must("eyes_centre")[0])
    room = solid(eyes.shape[0] + 2 * ROOM_MARGIN, eyes.shape[1] + 2 * ROOM_MARGIN, NEAR_BLACK)
    window = look.pack.info.get("title_window", [0, 0, 6, 4])
    scale = make_screens.nes_look.MANSION_SCALE
    dark = solid(window[3] * scale, window[2] * scale, NEAR_BLACK)
    return [("rain", drop), ("window_room", room), ("dark_window", dark)]


def cast_palettes(pictures: list[tuple[str, int, Picture]]) -> tuple[list[list[Colour]], list[int]]:
    """The palettes: the ghost's its own (the last), the rest chosen as the floors' tiles are."""
    others = [index for index, (name, _frame, _picture) in enumerate(pictures)
              if not name.startswith("ghost")]
    ghosts = [index for index in range(len(pictures)) if index not in others]
    palettes, chosen_others = choose_palettes([picture_colours(pictures[index][2]) for index in others])
    palettes += [[]] * (GHOST_PALETTE - len(palettes))
    ghost_palette: list[Colour] = []
    for index in ghosts:
        take_in(picture_colours(pictures[index][2]), ghost_palette)
    palettes.append(ghost_palette)
    chosen = [0] * len(pictures)
    for index, palette in zip(others, chosen_others):
        chosen[index] = palette
    for index in ghosts:
        chosen[index] = GHOST_PALETTE
    return palettes, chosen


def sheet_tile(tiles: list[bytes], block: int, sub_x: int, sub_y: int, indices: Indices) -> None:
    """A 16 x 16 block's quarter into the sheet's tiles, where the SNES looks for it: a block's four tiles
    are two side by side on one row of 16 and two below them."""
    row, column = divmod(block, SHEET_BLOCKS_ACROSS)
    tile = row * 32 + sub_y * 16 + column * 2 + sub_x
    tiles[tile] = tile_bytes(indices)


def sheet_block(tiles: list[bytes], block: int, part: Picture, palette: list[Colour]) -> None:
    """A 16 x 16 block of a picture (RGBA) into the sheet, as four tiles of palette indices."""
    for sub_y in range(2):
        for sub_x in range(2):
            piece = part[sub_y * TILE:(sub_y + 1) * TILE, sub_x * TILE:(sub_x + 1) * TILE]
            sheet_tile(tiles, block, sub_x, sub_y, tile_indices(piece[..., :3], piece[..., 3] > 0, palette))


def free_place(taken: set[int], wide: int, high: int) -> int:
    """The first block of the sheet, in reading order, with room for a picture this many blocks across
    and down. The picture keeps its shape on the sheet - its lower blocks below its upper ones - as the
    SNES finds them: a block down is 32 tiles on (src/fast.asm, cast_put)."""
    for row in range(SHEET_BLOCK_ROWS - high + 1):
        for column in range(SHEET_BLOCKS_ACROSS - wide + 1):
            first = row * SHEET_BLOCKS_ACROSS + column
            blocks = {first + block_y * SHEET_BLOCKS_ACROSS + block_x
                      for block_y in range(high) for block_x in range(wide)}
            if not blocks & taken:
                return first
    raise ValueError("the cast's pictures don't fit the sprite sheet's 128 blocks of 16 x 16")


def cast_sheet(look: "looks.FloorLook") -> tuple[bytes, bytes, list[CastPicture]]:
    """The sheet of sprite tiles, the palettes, and where each picture is."""
    pictures = cast_pictures(look)
    palettes, chosen = cast_palettes(pictures)
    tiles = [tile_bytes(BLANK)] * (SHEET_BLOCKS_ACROSS * SHEET_BLOCK_ROWS * 4)
    placed = []
    taken: set[int] = set()
    for (name, frame, picture), palette in zip(pictures, chosen):
        wide, high = blocks_of(picture)
        first = free_place(taken, wide, high)
        for block_y in range(high):
            for block_x in range(wide):
                part = picture[block_y * BLOCK:(block_y + 1) * BLOCK, block_x * BLOCK:(block_x + 1) * BLOCK]
                block = first + block_y * SHEET_BLOCKS_ACROSS + block_x
                sheet_block(tiles, block, part, palettes[palette])
                taken.add(block)
        placed.append(CastPicture(name, frame, wide, high, palette, first))
    palette_bytes = bytearray()
    for palette in palettes:
        colours = [0] + [snes_colour(colour) for colour in palette]
        colours += [0] * (16 - len(colours))
        palette_bytes += b"".join(colour.to_bytes(2, "little") for colour in colours)
    return b"".join(tiles), bytes(palette_bytes), placed


def block_tile(block: int) -> int:
    """The tile number the SNES wants for a 16 x 16 sprite at this block of the sheet."""
    row, column = divmod(block, SHEET_BLOCKS_ACROSS)
    return row * 32 + column * 2


def cast_header_text(placed: list[CastPicture]) -> str:
    """cast.h: each picture's place on the sheet, and a name for each cast entry's first picture and its
    frames (CAST_BAT_LEFT, CAST_BAT_LEFT_FRAMES)."""
    lines = ["/* The cast's pictures on the sprite sheet: tools/make_pictures.py. Don't edit. */",
             "#ifndef CAST_H", "#define CAST_H", "#include <snes.h>", ""]
    for index, picture in enumerate(placed):
        if index and placed[index - 1].name == picture.name:
            continue   # a later frame of the same picture
        frames = sum(1 for other in placed if other.name == picture.name)
        lines.append(f"#define CAST_{picture.name.upper()} {index}")
        lines.append(f"#define CAST_{picture.name.upper()}_FRAMES {frames}")
    lines += ["", f"#define CAST_PICTURES {len(placed)}",
              "/* Each picture: its first block's tile number; its 16 x 16 blocks across and down (left to",
              "   right, top to bottom); its palette. (Four tables, not one of records: a record's size",
              "   would cost a multiply on every lookup. Include this header in one C file only.) */"]
    for name, values in (("cast_tile", [str(block_tile(picture.first_block)) for picture in placed]),
                         ("cast_wide", [str(picture.blocks_wide) for picture in placed]),
                         ("cast_high", [str(picture.blocks_high) for picture in placed]),
                         ("cast_palette", [str(picture.palette) for picture in placed])):
        kind = "u16" if name == "cast_tile" else "u8"
        lines.append(f"const {kind} {name}[CAST_PICTURES] = {{")   # (not static: the assembly reads them)
        for start in range(0, len(values), 16):
            lines.append("    " + ", ".join(values[start:start + 16]) + ",")
        lines.append("};")
    lines += ["", "#endif", ""]
    return "\n".join(lines)


# --- the match's light -------------------------------------------------------------------------------
# The SNES look's light: fully lit within LIGHT_FULL of the light's reach (the 2600 glow: 16 units
# across, 14 lines up, from the eyes' middle), fading to nothing at LIGHT_GONE. On the SNES, two windows
# round the eyes - the lit disc and the dim ring round it - as half-widths a row of two scanlines (the
# floor's own step: 2 lines a unit), in pixels: 1.5 a unit across.
LIGHT_FULL, LIGHT_GONE = 0.55, 1.3              # (looks/snes/look.py)
LIGHT_HALF_WIDTH, LIGHT_HALF_HEIGHT = 16, 14    # (game/visibility.py)
CLOSED = 0xFF                                   # a row with no window
ROW_LINES = 2                                   # scanlines a row of the light's table


def light_shapes() -> tuple[list[int], list[int]]:
    """(inner, outer): each row's half-width in pixels, over the outer disc's rows, top to bottom, the
    row measured at its middle line."""
    outer_x, outer_y = LIGHT_HALF_WIDTH * 1.5 * LIGHT_GONE, LIGHT_HALF_HEIGHT * 2 * LIGHT_GONE
    inner_x, inner_y = LIGHT_HALF_WIDTH * 1.5 * LIGHT_FULL, LIGHT_HALF_HEIGHT * 2 * LIGHT_FULL
    lines = int(outer_y)
    inner, outer = [], []
    for line in range(1 - lines, lines, ROW_LINES):
        middle = line + 0.5
        outer.append(max(1, int(outer_x * (1 - (middle / outer_y) ** 2) ** 0.5)))   # (never 0: a pair's
        inside = abs(middle) < inner_y                                                 # bytes need a width)
        inner.append(int(inner_x * (1 - (middle / inner_y) ** 2) ** 0.5) if inside else CLOSED)
    return inner, outer


CENTRES = 256                  # every place the eyes' middle can be across the screen
HALF_CENTRES = 128             # the rows for centres 0-127 in one bank, 128-255 in the next


def window_edges(centre: int, half: int) -> tuple[int, int]:
    """A window's left and right edges round a centre, held on the screen (255, 0: no window)."""
    if half == CLOSED:
        return 255, 0
    return max(0, centre - half), min(255, centre + half)


def light_row_bytes(first_centre: int) -> bytes:
    """The light's rows for HALF_CENTRES centres from first_centre, as the HDMA table wants each: its two
    lines, then the lit disc's edges (window 1) and the dim ring's (window 2). src/fast.asm copies a
    frame's from here."""
    inner, outer = light_shapes()
    out = bytearray()
    for centre in range(first_centre, first_centre + HALF_CENTRES):
        for row in range(len(outer)):
            out += bytes([ROW_LINES, *window_edges(centre, inner[row]), *window_edges(centre, outer[row])])
    return bytes(out)


def light_text() -> str:
    """light.h: the two shapes, and the rows they span."""
    inner, outer = light_shapes()
    lines = ["/* The match's light: the lit disc and the dim ring, a half-width a row of two scanlines",
             "   (0xFF: none): tools/make_pictures.py. Don't edit. */", "#ifndef LIGHT_H", "#define LIGHT_H",
             "#include <snes.h>", "", f"#define LIGHT_ROWS {len(outer)}",
             f"#define LIGHT_ROW_LINES {ROW_LINES}   /* scanlines a row */",
             f"#define LIGHT_MIDDLE_ROW {len(outer) // 2}   /* the row through the eyes' middle */", ""]
    for name, values in (("light_inner_shape", inner), ("light_outer_shape", outer)):
        lines.append(f"const u8 {name}[LIGHT_ROWS] = {{")
        for start in range(0, len(values), 16):
            lines.append("    " + ", ".join(str(value) for value in values[start:start + 16]) + ",")
        lines.append("};")
    lines += [f"#define LIGHT_ROW_BYTES {1 + 4}   /* a row in the table: its lines, four edges */"]
    lines += ["", "/* The same as pairs for one 16-bit add each (src/fast.asm, light_rows' quick loop): the",
              "   low byte 256 - w, the high byte w - 1, so adding the centre to both bytes at once gives",
              "   centre - w and centre + w (the low byte's carry makes up the 1). 0xFF00: no window. */",
              "#define LIGHT_NO_WINDOW_PAIR 0xFF00"]
    for name, values in (("light_inner_pairs", inner), ("light_outer_pairs", outer)):
        pairs = [0xFF00 if value == CLOSED else ((value - 1) << 8) | (256 - value) for value in values]
        lines.append(f"const u16 {name}[LIGHT_ROWS] = {{")
        for start in range(0, len(pairs), 12):
            lines.append("    " + ", ".join(f"0x{value:04X}" for value in pairs[start:start + 12]) + ",")
        lines.append("};")
    lines += ["", "#endif", ""]
    return "\n".join(lines)


# --- the status band ---------------------------------------------------------------------------------
# The band above the view and the one below it, in the remaster's NES look's layout (looks/nes/look.py):
# the font, the item slots, the burning match and the lives' eyes as 4-colour tiles on the SNES's third
# layer, over the gradient panel the remaster's SNES look drew (looks/snes/look.py) - here painted on the
# backdrop line by line (src/status.c). Four palettes of three inks: the pieces' (white, grey, gold),
# then a word's ink with its shadow: white, grey, dim grey.
FONT_ORDER = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!.,-:'?<>/"
FONT_FIRST_LETTER = " "             # font_tiles[] runs from this character...
FONT_LETTERS = 64                   # ...for this many
PIECES_INKS = [nes_look.WHITE, nes_look.GREY, nes_look.EMBER]
WORD_INKS = [nes_look.WHITE, nes_look.GREY, nes_look.DIM_GREY]
SHADOW = (0, 0, 0)
INK, SHADOW_INK = 1, 2              # a word's palette: the letters, their drop shadow
WHITE_INK, GREY_INK, GOLD_INK = 1, 2, 3
GLYPH_WIDE, GLYPH_HIGH = 5, 7       # the font's glyphs, drawn a pixel in from the tile's left
SLOT = 16                           # an item slot: 2 x 2 tiles with a grey frame
FLAME = 3                           # the burning match: a flame this wide at the ember's end
EMBER_ROWS, FLAME_ROWS = (3, 4), (1, 2, 3, 4, 5, 6)
SLOT_ITEMS = ["key", "scepter"] + [f"urn{shape}" for shape in range(2, 9)]
STATUS_TILES = 256                  # the layer's tiles: 2K words of video memory
LOGO_LETTERS = "HAUNTEDOSGMVRYCP!"   # every letter of HAUNTED HOUSE, GAME OVER, YOU ESCAPED!
BLOOD_INK = 3                       # a word's palette's third colour: the logo's red shadow
BIG = 2                             # the logo's letters: the font at twice its size
BAND_LINES = 32                     # each band's height: the gradient's steps


def tile_bytes_4_colours(indices: Indices) -> bytes:
    """An 8 x 8 tile of colour indices 0-3 as the SNES keeps 4-colour tiles: bitplanes 0 and 1 row by
    row (the first half of a 16-colour tile's bytes)."""
    return tile_bytes(indices)[:16]


def font_tile(letter: str) -> bytes:
    """The remaster's 5 x 7 font: the glyph in ink 1 with its drop shadow (a pixel down and right) in 2."""
    glyph = hud.GLYPHS[letter]
    tile = np.zeros((TILE, TILE), np.uint8)
    for row in range(GLYPH_HIGH):
        for column in range(GLYPH_WIDE):
            if glyph[row * GLYPH_WIDE + column] == "#":
                tile[row + 1, column + 2] = SHADOW_INK
    for row in range(GLYPH_HIGH):
        for column in range(GLYPH_WIDE):
            if glyph[row * GLYPH_WIDE + column] == "#":
                tile[row, column + 1] = INK
    return tile_bytes_4_colours(tile)


def picture_tiles(picture: Indices) -> list[bytes]:
    """A picture's 8 x 8 tiles, row by row."""
    return [tile_bytes_4_colours(picture[top:top + TILE, left:left + TILE])
            for top in range(0, picture.shape[0], TILE) for left in range(0, picture.shape[1], TILE)]


def status_ink(picture: Picture) -> Indices:
    """A cast picture in the pieces' inks: see-through and black are 0, the rest the nearest ink."""
    choices = np.array(PIECES_INKS)
    pixels = picture[..., :3].reshape(-1, 3).astype(int)
    nearest = ((pixels[:, None] - choices[None]) ** 2).sum(axis=2).argmin(axis=1) + 1
    solid = (picture[..., 3].reshape(-1) > 0) & (pixels.sum(axis=1) > 0)
    return np.where(solid, nearest, 0).reshape(picture.shape[:2]).astype(np.uint8)


def slot(picture: Picture | None) -> Indices:
    """A 16 x 16 slot: a grey frame with cut corners, and the picture (if any) centred in it."""
    tile = np.zeros((SLOT, SLOT), np.uint8)
    if picture is not None:
        inked = status_ink(picture)[:SLOT, :SLOT]
        top, left = (SLOT - inked.shape[0]) // 2, (SLOT - inked.shape[1]) // 2
        area = tile[top:top + inked.shape[0], left:left + inked.shape[1]]
        np.copyto(area, inked, where=inked > 0)
    tile[0, 1:-1] = tile[-1, 1:-1] = tile[1:-1, 0] = tile[1:-1, -1] = GREY_INK
    return tile


def bar_tile(ember: int, flame_from: int, flame_to: int) -> bytes:
    """One tile of the burning match: ember in its first `ember` columns, flame in [flame_from, flame_to)."""
    tile = np.zeros((TILE, TILE), np.uint8)
    for row in EMBER_ROWS:
        tile[row, :ember] = GOLD_INK
    for row in FLAME_ROWS:
        tile[row, flame_from:flame_to] = WHITE_INK
    return tile_bytes_4_colours(tile)


def cast_picture(look: "looks.FloorLook", name: str) -> Picture:
    return look.adapt(look.pack.cast.must(name)[0])


def status_tiles(look: "looks.FloorLook") -> tuple[bytes, list[str]]:
    """The font, then the band's pieces; and their tile numbers for the code (status.h)."""
    tiles = [font_tile(letter) for letter in FONT_ORDER]
    names = [f"#define FONT_DIGITS {FONT_ORDER.index('0')}   /* the digits' tiles, 0 to 9 */"]
    names.append(f"#define SLOT_EMPTY {len(tiles)}")
    tiles += picture_tiles(slot(None))
    names.append(f"#define SLOT_ITEMS {len(tiles)}   /* 4 tiles each: key, scepter, urn shapes 2-8 */")
    for entry in SLOT_ITEMS:
        tiles += picture_tiles(slot(cast_picture(look, entry)))
    names.append(f"#define BAR_EMBER {len(tiles)}   /* the burning match: a tile of ember... */")
    tiles.append(bar_tile(TILE, 0, 0))
    names.append(f"#define BAR_END {len(tiles)}   /* ...+ the column the ember ends at, the flame after */")
    tiles += [bar_tile(end, end, min(end + FLAME, TILE)) for end in range(TILE)]
    names.append(f"#define BAR_FLAME {len(tiles) - 1}   /* ...+ how many columns of flame spill over */")
    tiles += [bar_tile(0, 0, spill) for spill in (1, 2)]
    names.append(f"#define LIVES_EYES {len(tiles)}   /* 2 tiles */")
    eyes = np.zeros((TILE, SLOT), np.uint8)
    inked = status_ink(cast_picture(look, "eyes_centre"))
    eyes[1:1 + inked.shape[0], 1:1 + inked.shape[1]] = inked
    tiles += picture_tiles(eyes)
    names.append(f"#define BIG_LETTERS {len(tiles)}   /* the logo's letters, 4 tiles each */")
    for letter in LOGO_LETTERS:
        tiles += picture_tiles(big_letter(letter))
    if len(tiles) > STATUS_TILES:
        raise ValueError(f"the status band needs {len(tiles)} tiles; there's room for {STATUS_TILES}")
    tiles += [bytes(16)] * (STATUS_TILES - len(tiles))
    return b"".join(tiles), names


def big_letter(letter: str) -> Indices:
    """A letter of the logo, 16 x 16, as the remaster's NES look draws its logo (draw_logo): the font at
    twice its size in white, its black shadow two pixels down and right, and a red one under all a pixel
    right and two down."""
    glyph = hud.GLYPHS[letter]
    cell = np.zeros((TILE * BIG, TILE * BIG), np.uint8)
    for ink, (across, down) in ((BLOOD_INK, (1, 2)), (SHADOW_INK, (2, 2)), (INK, (0, 0))):
        for row in range(GLYPH_HIGH):
            for column in range(GLYPH_WIDE):
                if glyph[row * GLYPH_WIDE + column] == "#":
                    top, left = row * BIG + down, (column + 1) * BIG + across
                    cell[top:top + BIG, left:left + BIG] = ink
    return cell


def status_palettes() -> bytes:
    """Four palettes of four colours (the first of each see-through, and colour 0 the backdrop, black):
    the pieces', then the words' - the ink, its shadow, and the logo's red."""
    palettes = [[SHADOW] + PIECES_INKS] + [[SHADOW, ink, SHADOW, nes_look.BLOOD] for ink in WORD_INKS]
    colours = [snes_colour(colour) for palette in palettes for colour in palette]
    return b"".join(colour.to_bytes(2, "little") for colour in colours)


def band_shades() -> list[int]:
    """The panel's gradient, a colour a line, with the bevel's light first line and dark last."""
    steps = np.linspace(0, 1, BAND_LINES)[:, None]
    gradient = np.array(snes_look.STATUS_TOP) * (1 - steps) + np.array(snes_look.STATUS_BOTTOM) * steps
    shades = [snes_colour(as_colour(colour)) for colour in gradient]
    shades[0] = snes_colour(snes_look.BEVEL_LIGHT)
    shades[-1] = snes_colour(snes_look.BEVEL_DARK)
    return shades


def status_header_text(names: list[str], floor_names: list[str]) -> str:
    """status.h: the tile numbers, the font's tile for each letter, the panel's shades, the floors' names."""
    letters = [chr(ord(FONT_FIRST_LETTER) + index) for index in range(FONT_LETTERS)]
    font = [FONT_ORDER.index(letter) if letter in FONT_ORDER else 0 for letter in letters]
    longest = max(len(name) for name in floor_names)
    lines = ["/* The status band's tiles, colours and words: tools/make_pictures.py. Don't edit. */",
             "#ifndef STATUS_H", "#define STATUS_H", "#include <snes.h>", ""] + names
    lines += ["", f"#define FONT_FIRST_LETTER '{FONT_FIRST_LETTER}'",
              "/* The font's tile for each letter from FONT_FIRST_LETTER on (0, a space, for letters it",
              "   hasn't). */", f"static const u8 font_tiles[{FONT_LETTERS}] = {{"]
    for start in range(0, FONT_LETTERS, 16):
        lines.append("    " + ", ".join(str(tile) for tile in font[start:start + 16]) + ",")
    big = [LOGO_LETTERS.index(letter) * 4 + 1 if letter in LOGO_LETTERS else 0 for letter in letters]
    lines += ["};", "/* The logo's big letters: each's first tile, less BIG_LETTERS, plus 1 (0: none). */",
              f"static const u8 big_letter_tiles[{FONT_LETTERS}] = {{"]
    for start in range(0, FONT_LETTERS, 16):
        lines.append("    " + ", ".join(str(tile) for tile in big[start:start + 16]) + ",")
    lines += ["};", "", f"#define BAND_LINES {BAND_LINES}",
              "/* The panel's colour on each of a band's lines, top to bottom (15-bit BGR). */",
              f"static const u16 band_shades[BAND_LINES] = {{"]
    shades = band_shades()
    for start in range(0, BAND_LINES, 8):
        lines.append("    " + ", ".join(f"0x{shade:04X}" for shade in shades[start:start + 8]) + ",")
    lines += ["};", "", f"#define NAME_LETTERS {longest + 1}   /* the longest floor's name, and its end */",
              f"static const char floor_names[{len(floor_names)}][NAME_LETTERS] = {{"]
    lines += [f'    "{name.upper()}",' for name in floor_names]
    lines += ["};", "", "#endif", ""]
    return "\n".join(lines)


# --- the files ---------------------------------------------------------------------------------------
def write_floor(folder: str, number: int, art: FloorArt) -> None:
    for name, data in (("tiles", art.tiles), ("walls", art.walls_map), ("floor", art.floor_map),
                       ("palette", art.palettes)):
        with open(os.path.join(folder, f"floor{number}_{name}.bin"), "wb") as out:
            out.write(data)


def asm_text(folder: str, count: int) -> str:
    """The floors' and screens' picture sets (count in all), the cast's, the band's, the skies."""
    lines = ["; The picture's data, bound into the ROM: tools/make_pictures.py. Don't edit.",
             '.include "hdr.asm"', ""]
    for number in range(1, count + 1):
        lines.append(f'.section ".floor{number}_art" superfree')
        for name in ("tiles", "walls", "floor", "palette"):
            path = os.path.join(folder, f"floor{number}_{name}.bin")
            lines += [f"floor{number}_{name}:", f'.incbin "{path}"', f"floor{number}_{name}_end:"]
        lines += [".ends", ""]
    lines.append('.section ".cast_art" superfree')
    for name in ("tiles", "palettes"):
        path = os.path.join(folder, f"cast_{name}.bin")
        lines += [f"cast_{name}:", f'.incbin "{path}"', f"cast_{name}_end:"]
    lines += [".ends", "", '.section ".status_art" superfree']
    for name in ("tiles", "palette"):
        path = os.path.join(folder, f"status_{name}.bin")
        lines += [f"status_{name}:", f'.incbin "{path}"', f"status_{name}_end:"]
    lines += [".ends", ""]
    for name in ("light_rows_low", "light_rows_high"):
        lines += [f'.section ".{name}" superfree', f"{name}:",
                  f'.incbin "{os.path.join(folder, name + ".bin")}"', ".ends", ""]
    lines += ['.section ".sky_tables" superfree']
    for name in ("title_skies", "ending_sky"):
        lines += [f"{name}:", f'.incbin "{os.path.join(folder, name + ".bin")}"']
    lines += [".ends", ""]
    return "\n".join(lines)


def header_text(count: int, floors: int) -> str:
    """art.h: the picture sets (the floors', then the screens'), and picture_set() to find one."""
    lines = ["/* The picture's data: tools/make_pictures.py. Don't edit. */", "#ifndef ART_H",
             "#define ART_H", "#include <snes.h>", "", f"#define ART_FLOORS {floors}",
             f"#define ART_TITLE {floors}   /* the screens' sets, after the floors' */",
             f"#define ART_ENDING {floors + 1}", f"#define ART_SETS {count}", ""]
    for number in range(1, count + 1):
        for name in ("tiles", "walls", "floor", "palette"):
            lines.append(f"extern char floor{number}_{name}, floor{number}_{name}_end;")
    lines.append("extern char cast_tiles, cast_tiles_end, cast_palettes, cast_palettes_end;")
    lines.append("extern char status_tiles, status_tiles_end, status_palette, status_palette_end;")
    lines += ["", "typedef struct {", "    u8 *tiles;", "    u16 tiles_size;", "    u8 *walls_map;",
              "    u8 *floor_map;", "    u8 *palettes;", "} FloorPictures;", "",
              "/* A picture set's pictures: a floor's by its number, or ART_TITLE, ART_ENDING. */",
              "static void floor_art(u8 floor, FloorPictures *art)", "{", "    switch (floor) {"]
    for number in range(1, count + 1):
        lines += [f"    case {number - 1}:", f"        art->tiles = (u8 *)&floor{number}_tiles;",
                  f"        art->tiles_size = (u16)(&floor{number}_tiles_end"
                  f" - &floor{number}_tiles);",
                  f"        art->walls_map = (u8 *)&floor{number}_walls;",
                  f"        art->floor_map = (u8 *)&floor{number}_floor;",
                  f"        art->palettes = (u8 *)&floor{number}_palette;", "        break;"]
    lines += ["    default:", "        break;", "    }", "}", "", "#endif", ""]
    return "\n".join(lines)


def write_screens(folder: str, kind_folder: str, floor_look: "looks.FloorLook", floors: int) -> int:
    """The screens' picture sets after the floors', their skies, and screens.h; returns how many sets."""
    look = floor_look
    if not isinstance(look, make_screens.nes_look.NesLook):
        raise TypeError("the screens are drawn by the SNES look, an NES look's kin")
    for number, (name, make) in enumerate(make_screens.SCENES, start=floors + 1):
        art = screen_art(make(look))
        write_floor(folder, number, art)
        print(f"  the {name}: {len(art.tiles) // 32} tiles")
    skies = (("title_skies", make_screens.title_skies()), ("ending_sky", make_screens.ending_sky()))
    for name, data in skies:
        with open(os.path.join(folder, f"{name}.bin"), "wb") as out:
            out.write(data)
    with open(os.path.join(kind_folder, "screens.h"), "w") as header:
        header.write(make_screens.screens_header_text(look))
    return len(make_screens.SCENES)


def write(kind_folder: str, shareable: bool) -> None:
    folder = os.path.join(kind_folder, "art")
    os.makedirs(folder, exist_ok=True)
    floor_set, names = floor_looks(shareable)
    for number, (look, name) in enumerate(zip(floor_set, names), start=1):
        art = floor_art(look, number - 1)
        write_floor(folder, number, art)
        scene = look.scene(number - 1).full[..., :3].astype(np.uint8)   # (as drawn: to compare builds)
        Image.fromarray(scene, "RGB").save(os.path.join(folder, f"floor{number}_scene.png"))
        print(f"  floor {number} {name}: {len(art.tiles) // 32} tiles")
    sheet, palettes, placed = cast_sheet(floor_set[0])
    with open(os.path.join(folder, "cast_tiles.bin"), "wb") as out:
        out.write(sheet)
    with open(os.path.join(folder, "cast_palettes.bin"), "wb") as out:
        out.write(palettes)
    print(f"  the cast: {sum(picture.blocks_wide * picture.blocks_high for picture in placed)} blocks of 128")
    with open(os.path.join(kind_folder, "cast.h"), "w") as header:
        header.write(cast_header_text(placed))
    band_tiles, band_names = status_tiles(floor_set[0])
    with open(os.path.join(folder, "status_tiles.bin"), "wb") as out:
        out.write(band_tiles)
    with open(os.path.join(folder, "status_palette.bin"), "wb") as out:
        out.write(status_palettes())
    with open(os.path.join(kind_folder, "status.h"), "w") as header:
        header.write(status_header_text(band_names, names))
    sets = len(names) + write_screens(folder, kind_folder, floor_set[0], len(names))
    with open(os.path.join(kind_folder, "art.h"), "w") as header:
        header.write(header_text(sets, len(names)))
    with open(os.path.join(kind_folder, "light.h"), "w") as header:
        header.write(light_text())
    for name, first in (("light_rows_low", 0), ("light_rows_high", HALF_CENTRES)):
        with open(os.path.join(folder, f"{name}.bin"), "wb") as out:
            out.write(light_row_bytes(first))
    with open(os.path.join(ROOT, "src", "art_data.asm"), "w") as asm:
        asm.write(asm_text(folder, sets))


def main() -> None:
    shareable = "--faithful" not in sys.argv
    write(os.path.join(ROOT, "build", "shareable" if shareable else "faithful"), shareable)


if __name__ == "__main__":
    main()
