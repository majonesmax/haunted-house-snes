"""The full screens' pictures and words (docs/plan.md, step 4), as the remaster's SNES look lays them out
(its looks/snes/look.py, over its NES look's layout): the title (game select, game over, and behind the
help) - the mansion on its hill under the moon - and the ending - the mansion at dawn, the sun coming up
behind it. The remaster draws 240 lines; the SNES shows 224, so 8 come off the top (sky) and 8 off the
bottom (hill).

A screen is a picture set like a floor's (tools/make_pictures.py loads it the same way): its first layer
the mansion, the moon or the sun, the stars and the hill, with the sky left out; its second the glow round
the moon or the sun, which colour math adds to the sky. The sky itself is the backdrop colour, set line
by line by HDMA from a table made here - smooth, as the remaster's gradient is. The title's lightning is
the same table brightened, a table for each of its 14 fading frames: a flash costs no time at all.

Used by tools/make_pictures.py (screen_arts, sky tables) and for the words, screens_header_text.
"""

import os
import sys
from collections.abc import Callable
from typing import NamedTuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
sys.path.insert(0, REMASTER)
from game import guide  # noqa: E402
from looks.nes import look as nes_look  # noqa: E402
from looks.snes import look as snes_look  # noqa: E402

Picture = np.ndarray
Colour = tuple[int, int, int]
REMASTER_HEIGHT, SCREEN_HEIGHT, SCREEN_WIDTH = 240, 224, 256
TOP_CUT = 8                        # remaster lines off the top: a remaster y less this is the SNES's
KEY: Colour = (1, 2, 3)            # what the sky is drawn as here, to find it again (no art uses it)
LINES_PER_ENTRY = 112              # an HDMA entry covers at most 127 lines: the screen's 224 in two
GLOW_LEVELS = 15                   # a glow is one tint at this many strengths: one palette of 15
FLASH_LEVELS = snes_look.FLASH_FRAMES


class ScreenScene(NamedTuple):
    picture: Picture            # the first layer: 224 x 256 RGB
    drawn: np.ndarray           # where it has anything (elsewhere the sky shows)
    glow: Picture               # the second layer: what's added to the sky, RGB
    glowing: np.ndarray         # where that's anything
    sky: list[Colour]           # the sky's colour on each of the 224 lines


def blank() -> Picture:
    screen = np.zeros((REMASTER_HEIGHT, SCREEN_WIDTH, 3), np.uint8)
    screen[:] = KEY
    return screen


def cropped(picture: Picture) -> Picture:
    return picture[TOP_CUT:TOP_CUT + SCREEN_HEIGHT]


# --- the title -----------------------------------------------------------------------------------------
def title_sky_rows(flash: float) -> list[Colour]:
    """The title's sky on each of the remaster's 240 lines: the SNES look's gradient down to the hill's
    top (brightened by a flash, 0-1), the NES look's night below it, where it shows beside the mansion."""
    gradient = snes_look.sky_gradient(nes_look.MANSION_AT[1] + 40)[:, 0, :]
    gradient = gradient + (255 - gradient) * flash
    night = np.array(nes_look.SKY, float)
    rows = [tuple(int(value) for value in row) for row in gradient]
    rows += [tuple(int(value) for value in night)] * (REMASTER_HEIGHT - len(rows))
    return [(row[0], row[1], row[2]) for row in rows]


def tinted(strength: np.ndarray, tint: np.ndarray) -> Picture:
    """A glow as one tint at GLOW_LEVELS strengths (strength 0-1 a pixel): what colour math adds to the
    sky. One tint, so one palette serves every tile of it."""
    levels = np.round(strength * GLOW_LEVELS) / GLOW_LEVELS
    return np.clip(levels[..., None] * tint, 0, 255).astype(np.uint8)


def moon_glow(sky_rows: list[Colour]) -> Picture:
    """What the SNES look's halo adds to the sky: it moves each sky pixel towards MOON_HALO by up to 60%,
    fading from the moon's edge; here as the move at the moon's own height, by strength."""
    centre_x, centre_y = nes_look.MOON_AT[0] + 20, nes_look.MOON_AT[1] + 20
    rows, columns = np.mgrid[:REMASTER_HEIGHT, :SCREEN_WIDTH]
    strength = np.clip(1 - (np.hypot(columns - centre_x, rows - centre_y) - 20) / 40, 0, 1)
    strength[nes_look.MANSION_AT[1] + 40:] = 0
    tint = np.clip((snes_look.MOON_HALO - np.array(sky_rows[centre_y], float)) * 0.6, 0, 255)
    return tinted(strength, tint)


def title_scene(look: "nes_look.NesLook") -> ScreenScene:
    screen = blank()
    for x, y in nes_look.STARS:
        screen[y, x] = nes_look.WHITE
    look.draw_world_picture(screen, "title_moon", nes_look.MOON_AT, nes_look.MOON_SCALE)
    look.draw_world_picture(screen, "title_mansion", nes_look.MANSION_AT, nes_look.MANSION_SCALE)
    sky = title_sky_rows(0.0)
    glow = moon_glow(sky)
    picture = cropped(snes_rgb(screen))
    drawn = (cropped(screen) != KEY).any(axis=2)
    glow = cropped(snes_rgb(glow))
    glowing = glow.any(axis=2) & ~drawn
    return ScreenScene(picture, drawn, glow, glowing, sky[TOP_CUT:TOP_CUT + SCREEN_HEIGHT])


# --- the ending ----------------------------------------------------------------------------------------
def dawn_rows() -> list[Colour]:
    rows = np.linspace(0, 1, REMASTER_HEIGHT)
    stops, colours = zip(*snes_look.DAWN)
    sky = np.stack([np.interp(rows, stops, [colour[channel] for colour in colours]) for channel in range(3)],
                   axis=1)
    return [(int(row[0]), int(row[1]), int(row[2])) for row in sky]


def sun_glow(sky_rows: list[Colour]) -> Picture:
    """What the SNES look's glow round the sun adds to the dawn: it moves the sky 70% of its glow towards
    SUN_GLOW."""
    sun_size = 20 * nes_look.SUN_SCALE
    centre_x, centre_y = nes_look.SUN_AT[0] + sun_size / 2, nes_look.SUN_AT[1] + sun_size / 2
    rows, columns = np.mgrid[:REMASTER_HEIGHT, :SCREEN_WIDTH]
    strength = np.clip(1 - np.hypot(columns - centre_x, rows - centre_y) / snes_look.SUN_GLOW_REACH, 0, 1)
    tint = np.clip((snes_look.SUN_GLOW - np.array(sky_rows[int(centre_y)], float)) * 0.7, 0, 255)
    return tinted(strength, tint)


def ending_scene(look: "nes_look.NesLook") -> ScreenScene:
    screen = blank()
    look.draw_sun(screen)
    look.draw_world_picture(screen, "title_mansion", nes_look.MANSION_AT, nes_look.MANSION_SCALE)
    look.darken_window(screen)
    sky = dawn_rows()
    glow = sun_glow(sky)
    picture = cropped(snes_rgb(screen))
    drawn = (cropped(screen) != KEY).any(axis=2)
    glow = cropped(snes_rgb(glow))
    glowing = glow.any(axis=2) & ~drawn
    return ScreenScene(picture, drawn, glow, glowing, sky[TOP_CUT:TOP_CUT + SCREEN_HEIGHT])


def snes_rgb(picture: Picture) -> Picture:
    """15-bit colour (the remaster's shared/pixelart.py snes_rgb), the key colour kept as it is."""
    five_bits = np.asarray(picture, np.uint8) >> 3
    snapped = ((five_bits << 3) | (five_bits >> 2)).astype(np.uint8)
    keep = (picture == KEY).all(axis=2)
    snapped[keep] = KEY
    return snapped


SCENES: list[tuple[str, Callable[["nes_look.NesLook"], ScreenScene]]] = [("title", title_scene),
                                                                             ("ending", ending_scene)]


# --- the skies, as HDMA tables -------------------------------------------------------------------------
def sky_table(lines: list[Colour]) -> bytes:
    """HDMA to colour 0, the backdrop, a line at a time (4 bytes a line: the colour's number twice, its two
    bytes), in two entries of 112 lines; 0 to end."""
    out = bytearray()
    for start in range(0, SCREEN_HEIGHT, LINES_PER_ENTRY):
        out.append(0x80 | LINES_PER_ENTRY)
        for red, green, blue in lines[start:start + LINES_PER_ENTRY]:
            colour = (blue >> 3) << 10 | (green >> 3) << 5 | red >> 3
            out += bytes([0, 0, colour & 0xFF, colour >> 8])
    out.append(0)
    return bytes(out)


def title_skies() -> bytes:
    """The title's sky, then the same in each frame of a lightning flash's fade (the SNES look's
    lightning_level: 85% of the way to white at the strike, nothing after FLASH_FRAMES)."""
    tables = sky_table(title_sky_rows(0.0)[TOP_CUT:TOP_CUT + SCREEN_HEIGHT])
    for since in range(FLASH_LEVELS):
        level = max(0.0, 1 - since / FLASH_LEVELS) * 0.85
        tables += sky_table(title_sky_rows(level)[TOP_CUT:TOP_CUT + SCREEN_HEIGHT])
    return tables


def ending_sky() -> bytes:
    return sky_table(dawn_rows()[TOP_CUT:TOP_CUT + SCREEN_HEIGHT])


SKY_TABLE_BYTES = len(sky_table([(0, 0, 0)] * SCREEN_HEIGHT))


# --- the words ------------------------------------------------------------------------------------------
# The remaster's keyboard, as the SNES pad says it (the NES game did the same for its pad).
KEYS_TO_BUTTONS = [("SPACE", "B")]
TITLE_HINT = "SELECT GAME   START   X HELP"
ENDING_HINT = "SELECT GAME  START PLAY"
STORY_HINT = "PRESS ANY BUTTON"
HELP_HINT = "X GOES BACK"


def on_the_pad(line: str) -> str:
    for key, button in KEYS_TO_BUTTONS:
        line = line.replace(key, button)
    return line


def c_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def c_strings(name: str, lines: list[str]) -> list[str]:
    """A C array of strings, one a line."""
    out = [f"static const char *const {name}[{len(lines)}] = {{"]
    out += [f"    {c_string(line)}," for line in lines]
    return out + ["};"]


def rules_lines() -> list[str]:
    """Each game's rules: a table of 9 games' first lines, and the lines themselves ('' ends a game's)."""
    lines: list[str] = []
    starts = []
    for game in range(1, 10):
        starts.append(len(lines))
        lines += guide.game_rules(game) + [""]
    out = c_strings("rules_lines", lines)
    out.append(f"static const u8 rules_start[9] = {{{', '.join(str(start) for start in starts)}}};")
    return out


def verdict_lines() -> list[str]:
    most = [str(limit if limit is not None else 255) for limit, _line in guide.VERDICTS]
    out = c_strings("verdict_lines", [line for _limit, line in guide.VERDICTS])
    out.append(f"static const u8 verdict_most[{len(most)}] = {{{', '.join(most)}}};")
    out.append(f"#define VERDICTS {len(most)}")
    return out


def place_lines(look: "nes_look.NesLook") -> list[str]:
    """Where the window and the door are on the screen (the pack's title art, scaled and placed)."""
    scale = nes_look.MANSION_SCALE
    left, top = nes_look.MANSION_AT
    window = look.pack.info.get("title_window", [0, 0, 0, 0])
    door = look.pack.info.get("title_door", [0, 0, 0, 0])
    mansion = look.pack.world.get("title_mansion")
    mansion_width = mansion[0].shape[1] * scale if mansion else 0
    door_middle = int(left + (door[0] + door[2] / 2) * scale)
    return [f"#define WINDOW_X {left + window[0] * scale}   /* the tower window's top-left, and size */",
            f"#define WINDOW_Y {top + window[1] * scale - TOP_CUT}",
            f"#define WINDOW_WIDE {window[2] * scale}",
            f"#define WINDOW_HIGH {window[3] * scale}",
            f"#define DOOR_MIDDLE_X {door_middle}   /* the eyes leave here */",
            f"#define HILL_END_X {left + mansion_width}   /* where the grass stops */",
            f"#define GROUND_Y {nes_look.GROUND_Y - TOP_CUT}   /* the eyes' feet, walking on the hill */",
            f"#define STORY_EYES_Y {nes_look.INTRO_EYES_Y - TOP_CUT}"] + size_lines(look)


RAIN_DROPS = snes_look.RAIN_DROPS


def size_lines(look: "nes_look.NesLook") -> list[str]:
    """The eyes' and the whole urn's sizes in pixels (sprites are placed by their middles)."""
    eyes = look.adapt(look.pack.cast.must("eyes_centre")[0])
    urn = look.adapt(look.pack.cast.must("urn8")[0])
    return [f"#define EYES_WIDE {eyes.shape[1]}", f"#define EYES_HIGH {eyes.shape[0]}",
            f"#define URN_WIDE {urn.shape[1]}", f"#define URN_HIGH {urn.shape[0]}"]


def rain_lines() -> list[str]:
    """The SNES look's raindrops (add_rain: the same seed, so the same drops): where each starts, and how
    fast it falls - down `speed` lines a frame and left a third of that."""
    rng = np.random.default_rng(5)
    starts_x = rng.integers(0, SCREEN_WIDTH, RAIN_DROPS)
    starts_y = rng.integers(0, REMASTER_HEIGHT, RAIN_DROPS)
    speeds = rng.integers(5, 9, RAIN_DROPS)
    on_screen = [str(int(y) % SCREEN_HEIGHT) for y in starts_y]
    return [f"#define RAIN_DROPS {RAIN_DROPS}",
            f"static const u8 rain_start_x[RAIN_DROPS] = {{{', '.join(str(int(x)) for x in starts_x)}}};",
            "static const u8 rain_start_y[RAIN_DROPS] = {" + ", ".join(on_screen) + "};",
            f"static const u8 rain_speed[RAIN_DROPS] = {{{', '.join(str(int(speed)) for speed in speeds)}}};"]


def screens_header_text(look: "nes_look.NesLook") -> str:
    """screens.h: the screens' words (the remaster's game/guide.py, on the pad) and the places on the
    title's picture the code needs."""
    help_lines = [on_the_pad(line) for line, _kind in guide.HOW_TO_PLAY]
    headings = [str(1 if kind == "title" else 0) for _line, kind in guide.HOW_TO_PLAY]
    lines = ["/* The screens' words and places: tools/make_screens.py. Don't edit. */", "#ifndef SCREENS_H",
             "#define SCREENS_H", "#include <snes.h>", ""]
    lines += c_strings("story_lines", list(guide.STORY)) + [f"#define STORY_LINES {len(guide.STORY)}", ""]
    lines += c_strings("help_lines", help_lines) + [f"#define HELP_LINES {len(help_lines)}"]
    lines += [f"static const u8 help_heading[HELP_LINES] = {{{', '.join(headings)}}};", ""]
    lines += rules_lines() + [""] + verdict_lines() + [""]
    for name, text in (("TITLE_HINT", TITLE_HINT), ("ENDING_HINT", ENDING_HINT), ("STORY_HINT", STORY_HINT),
                       ("HELP_HINT", HELP_HINT)):
        lines.append(f"#define {name} {c_string(text)}")
    lines += [""] + place_lines(look) + rain_lines() + [f"#define SKY_TABLE_BYTES {SKY_TABLE_BYTES}",
                                         f"#define FLASH_LEVELS {FLASH_LEVELS}", "", "#endif", ""]
    return "\n".join(lines)
