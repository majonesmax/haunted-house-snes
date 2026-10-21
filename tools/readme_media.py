"""The README's pictures: the shareable ROM played in the emulator, and a few moments of it saved into
docs/media/ at twice size - the title, the Foyer by matchlight, three floors with the lights on, and the
ending. All of it is our own art (the NES game's mansion, the remaster's nocturne pack), so the pictures may
be committed.

To set the moments up quickly it writes the game's RAM between frames (where the eyes stand, what they hold),
as the tests do; the game itself is never changed.

Usage: python tools/readme_media.py
"""

import os
import sys

import numpy as np
from PIL import Image

import snes as S
from build import build, symbols
import make_mansion   # (after build: it puts the NES game's tools on the path, for its mansion module)
import mansion as M  # noqa: E402  (the NES game's)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(ROOT, "docs", "media")
NES_MANSION = os.path.join(os.path.dirname(ROOT), "haunted-house-nes", "mansion", "floors.txt")
SCALE = 2
WORK_RAM_BANK = 0x7E0000
GAME_RAM_START = 0x80        # the 2600's RAM addresses start here
FLOOR, ROOM, PLAYER_X, PLAYER_Y, CARRIED, URN_SHAPES = 0x8D, 0x9C, 0xAA, 0xB5, 0x9A, 0x9D
MONSTER_FLOORS = 0xA5
MONSTERS = 5
OFF_EVERY_FLOOR = 7          # a monster's floor no floor has: out of the picture
WHOLE_URN, JOINED, URN = 8, 0xFF, 2
SHOWN_ROOM = 2
NOTE_GONE = 400              # frames for the cheat's note to have gone from the band
FLOORS_SHOWN = {"gallery": 2, "bedrooms": 3, "cellar": 0}   # name -> floor (0 the cellar)
SETTLE = 25                  # frames for a floor to be drawn after the eyes are put there
BOOT_FRAMES = 100            # past the set-up, into the story
TITLE_FRAMES = 150           # the title, settled, its rain falling
ESCAPE_FRAMES = 60           # walking out of the front door
ENDING_FRAMES = 700          # the light at the door, then the dawn, the walk and the verdict


class Game:
    """The shareable ROM in the emulator, with the 2600's RAM to hand by its own addresses."""

    def __init__(self, rom: str) -> None:
        self.machine = S.Snes(rom)
        self.game_ram = symbols(True)["game_ram"] - WORK_RAM_BANK
        self.machine.run(BOOT_FRAMES)
        self.machine.run(6, {S.BUTTON_X})        # past the story
        self.machine.run(TITLE_FRAMES)

    def poke(self, address: int, value: int) -> None:
        self.machine.ram[self.game_ram + address - GAME_RAM_START] = value

    def start(self) -> None:
        self.machine.run(6, {S.BUTTON_START})
        self.machine.run(60)

    def save(self, name: str) -> None:
        picture = Image.fromarray(np.ascontiguousarray(self.machine.picture)[..., :3])
        picture = picture.resize((picture.width * SCALE, picture.height * SCALE), Image.Resampling.NEAREST)
        picture.save(os.path.join(OUTPUT, f"{name}.png"))
        print(name)

    def put_eyes(self, floor: int, x: int, y: int) -> None:
        """The eyes in room 2 of a floor, the monsters elsewhere; held there while the floor is drawn."""
        for _frame in range(SETTLE):
            self.poke(FLOOR, floor)
            self.poke(ROOM, SHOWN_ROOM)
            self.poke(PLAYER_X, x)
            self.poke(PLAYER_Y, y)
            for monster in range(MONSTERS):
                self.poke(MONSTER_FLOORS + monster, OFF_EVERY_FLOOR)
            self.machine.run(1)


def room_2_middle(floor: int) -> tuple[int, int]:
    with open(NES_MANSION) as mansion_file:
        tables = M.floor_tables(M.parse(mansion_file.read())[floor])
    return tables["waypoint_x"][SHOWN_ROOM], tables["waypoint_y"][SHOWN_ROOM]


def by_matchlight(rom: str) -> None:
    game = Game(rom)
    game.start()
    game.machine.run(5, {S.BUTTON_B})         # a match
    game.machine.run(20)
    game.machine.run(24, {S.BUTTON_LEFT})
    game.save("foyer_by_matchlight")


def lights_on(rom: str) -> None:
    game = Game(rom)
    game.start()
    game.machine.run(4, {S.BUTTON_B})
    game.machine.run(3, {S.BUTTON_B, S.BUTTON_SELECT})   # the lights-on cheat
    game.machine.run(4, {S.BUTTON_B})
    game.machine.run(NOTE_GONE)
    for name, floor in FLOORS_SHOWN.items():
        game.put_eyes(floor, *room_2_middle(floor))
        game.machine.run(SETTLE)
        game.save(name)


def ending(rom: str) -> None:
    game = Game(rom)
    game.start()
    game.poke(URN_SHAPES, WHOLE_URN)          # the whole urn in hand
    game.poke(URN_SHAPES + 1, JOINED)
    game.poke(URN_SHAPES + 2, JOINED)
    game.poke(CARRIED, URN)
    game.machine.run(ESCAPE_FRAMES, {S.BUTTON_RIGHT})
    game.machine.run(ENDING_FRAMES)
    game.save("ending")


def main() -> None:
    rom = build(shareable=True)
    os.makedirs(OUTPUT, exist_ok=True)
    Game(rom).save("title")
    by_matchlight(rom)
    lights_on(rom)
    ending(rom)


if __name__ == "__main__":
    sys.exit(main())
