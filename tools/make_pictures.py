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
  src/art_data.asm      binds them all into the ROM
  art.h                 declares them, and floor_art() gives the engine a floor's; cast.h, each sprite's place

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

import content  # noqa: E402
import looks  # noqa: E402
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
    palette_bytes = bytearray()
    for palette in palettes + [[]] * (PALETTES - len(palettes)):
        colours = [0] + [snes_colour(colour) for colour in palette]
        colours += [0] * (16 - len(colours))
        palette_bytes += b"".join(colour.to_bytes(2, "little") for colour in colours)
    return FloorArt(b"".join(tiles.tiles), walls_map, floor_map, bytes(palette_bytes))


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
    """(name, frame, the picture in blocks) for every cast picture kept."""
    pictures = []
    for name, frames in CAST:
        for frame in frames:
            pictures.append((name, frame, in_blocks(look.adapt(look.pack.cast.must(name)[frame]))))
    return pictures


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


def cast_sheet(look: "looks.FloorLook") -> tuple[bytes, bytes, list[CastPicture]]:
    """The sheet of sprite tiles, the palettes, and where each picture is."""
    pictures = cast_pictures(look)
    palettes, chosen = cast_palettes(pictures)
    tiles = [tile_bytes(BLANK)] * (SHEET_BLOCKS_ACROSS * SHEET_BLOCK_ROWS * 4)
    placed = []
    block = 0
    for (name, frame, picture), palette in zip(pictures, chosen):
        wide, high = blocks_of(picture)
        for block_y in range(high):
            for block_x in range(wide):
                part = picture[block_y * BLOCK:(block_y + 1) * BLOCK, block_x * BLOCK:(block_x + 1) * BLOCK]
                sheet_block(tiles, block + block_y * wide + block_x, part, palettes[palette])
        placed.append(CastPicture(name, frame, wide, high, palette, block))
        block += wide * high
    if block > SHEET_BLOCKS_ACROSS * SHEET_BLOCK_ROWS:
        raise ValueError(f"the cast needs {block} blocks of 16 x 16; the sheet holds 128")
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
              "   would cost a multiply on every lookup.) */"]
    for name, values in (("cast_tile", [str(block_tile(picture.first_block)) for picture in placed]),
                         ("cast_wide", [str(picture.blocks_wide) for picture in placed]),
                         ("cast_high", [str(picture.blocks_high) for picture in placed]),
                         ("cast_palette", [str(picture.palette) for picture in placed])):
        kind = "u16" if name == "cast_tile" else "u8"
        lines.append(f"static const {kind} {name}[CAST_PICTURES] = {{")
        for start in range(0, len(values), 16):
            lines.append("    " + ", ".join(values[start:start + 16]) + ",")
        lines.append("};")
    lines += ["", "#endif", ""]
    return "\n".join(lines)


# --- the files ---------------------------------------------------------------------------------------
def write_floor(folder: str, number: int, art: FloorArt) -> None:
    for name, data in (("tiles", art.tiles), ("walls", art.walls_map), ("floor", art.floor_map),
                       ("palette", art.palettes)):
        with open(os.path.join(folder, f"floor{number}_{name}.bin"), "wb") as out:
            out.write(data)


def asm_text(folder: str, count: int) -> str:
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
    lines += [".ends", ""]
    return "\n".join(lines)


def header_text(count: int) -> str:
    lines = ["/* The picture's data: tools/make_pictures.py. Don't edit. */", "#ifndef ART_H",
             "#define ART_H", "#include <snes.h>", "", f"#define ART_FLOORS {count}", ""]
    for number in range(1, count + 1):
        for name in ("tiles", "walls", "floor", "palette"):
            lines.append(f"extern char floor{number}_{name}, floor{number}_{name}_end;")
    lines.append("extern char cast_tiles, cast_tiles_end, cast_palettes, cast_palettes_end;")
    lines += ["", "typedef struct {", "    u8 *tiles;", "    u16 tiles_size;", "    u8 *walls_map;",
              "    u8 *floor_map;", "    u8 *palettes;", "} FloorPictures;", "",
              "/* A floor's pictures, by its number 0-4. */",
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


def write(kind_folder: str, shareable: bool) -> None:
    folder = os.path.join(kind_folder, "art")
    os.makedirs(folder, exist_ok=True)
    floor_set, names = floor_looks(shareable)
    for number, (look, name) in enumerate(zip(floor_set, names), start=1):
        art = floor_art(look, number - 1)
        write_floor(folder, number, art)
        print(f"  floor {number} {name}: {len(art.tiles) // 32} tiles")
    sheet, palettes, placed = cast_sheet(floor_set[0])
    with open(os.path.join(folder, "cast_tiles.bin"), "wb") as out:
        out.write(sheet)
    with open(os.path.join(folder, "cast_palettes.bin"), "wb") as out:
        out.write(palettes)
    print(f"  the cast: {sum(picture.blocks_wide * picture.blocks_high for picture in placed)} blocks of 128")
    with open(os.path.join(kind_folder, "cast.h"), "w") as header:
        header.write(cast_header_text(placed))
    with open(os.path.join(kind_folder, "art.h"), "w") as header:
        header.write(header_text(len(names)))
    with open(os.path.join(ROOT, "src", "art_data.asm"), "w") as asm:
        asm.write(asm_text(folder, len(names)))


def main() -> None:
    shareable = "--faithful" not in sys.argv
    write(os.path.join(ROOT, "build", "shareable" if shareable else "faithful"), shareable)


if __name__ == "__main__":
    main()
