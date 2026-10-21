"""A match lit again where the last one went out gives light: the light's table holds the circle's rows.

(The bug it guards: a table closed when a match went out kept a note of the rows it had held, though the
table's end now lay on them; a match lit again on the spot found the note, skipped writing the rows, and
the table ended before the circle - no light, until a step aside forced the rows to be written.)

Usage: python tests/test_light.py [--faithful]      (exit code 1 on failure)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from build import build, shareable_wanted, symbols  # noqa: E402
from snes import BUTTON_B, BUTTON_START, BUTTON_X, Snes  # noqa: E402

WORK_RAM_BANK = 0x7E0000
GAME_RAM_START = 0x80          # the 2600's RAM addresses start here
FLAGS = 0x8A
MATCH_LIT = 0x40
ENTRY = 5                      # src/light.c: a table entry is a count and four edges...
ROWS_AT = 2 * ENTRY            # ...and the circle's rows start after two entries
LIGHT_ROWS = 36
TABLE_SIZE = ROWS_AT + LIGHT_ROWS * ENTRY + 2 * ENTRY + 1
BOOT_FRAMES = 100              # past the set-up and into the story
PRESS_FRAMES = 10
SETTLE_FRAMES = 120            # after the title, before play
WAIT_FRAMES = 200              # after a match goes out, before the next press
MOST_BURN_FRAMES = 5000
MATCHES = 4                    # presses tried (some come too soon after the last match and don't light)


class Game:
    """The SNES game in the emulator, with its game RAM and the light's tables to hand."""

    def __init__(self, shareable: bool) -> None:
        self.snes = Snes(build(shareable=shareable))
        where = symbols(shareable)
        self.game_ram = where["game_ram"] - WORK_RAM_BANK
        self.tables = where["light_table"] - WORK_RAM_BANK
        self.built_offset = where["light_table_offset"] - WORK_RAM_BANK

    def match_lit(self) -> bool:
        return bool(self.snes.ram[self.game_ram + FLAGS - GAME_RAM_START] & MATCH_LIT)

    def shown_first_row_count(self) -> int:
        """The first circle row's line count in the table being sent (0 would end the table there)."""
        built = int(self.snes.ram[self.built_offset]) | int(self.snes.ram[self.built_offset + 1]) << 8
        shown = TABLE_SIZE - built
        return int(self.snes.ram[self.tables + shown + ROWS_AT])

    def start(self) -> None:
        self.snes.run(BOOT_FRAMES)
        self.snes.run(PRESS_FRAMES, {BUTTON_X})        # past the story
        self.snes.run(SETTLE_FRAMES)
        self.snes.run(PRESS_FRAMES, {BUTTON_START})
        self.snes.run(SETTLE_FRAMES)

    def burn_out(self) -> None:
        frames = 0
        while self.match_lit() and frames < MOST_BURN_FRAMES:
            self.snes.run(1)
            frames += 1
        self.snes.run(WAIT_FRAMES)


def main() -> None:
    game = Game(shareable_wanted(sys.argv))
    game.start()
    lit = 0
    for _match in range(MATCHES):
        game.snes.run(PRESS_FRAMES, {BUTTON_B})
        if game.match_lit():
            lit += 1
            count = game.shown_first_row_count()
            if count == 0:
                sys.exit(f"FAIL: match {lit} is lit but its light's table ends before the circle")
        game.burn_out()
    if lit < 2:
        sys.exit(f"FAIL: only {lit} match lit, standing still - the test needs two")
    print(f"{lit} matches lit on the same spot, each with its circle: OK")


if __name__ == "__main__":
    main()
