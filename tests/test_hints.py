"""The hints point the right way: the SNES's hint (src/hints.c) against the remaster's own rules (its
game/hints.py) for the same state.

The engine check's bot plays (tests/verify_engine.py); every so often in play a hint is asked for (as X
would), and the words the band below then shows are read back from its map and compared with what the
remaster's hint() says for that state - its keyboard's SPACE being the pad's B.

Usage: python tests/test_hints.py [--faithful] [frames per game]   (exit code 1 on any disagreement)
"""

import os
import sys
from collections.abc import Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify_engine as E  # noqa: E402
import make_pictures  # noqa: E402

from game import hints  # noqa: E402
from game import palette as game_palette  # noqa: E402
from game.state import GameState  # noqa: E402

FRAMES_PER_GAME = 600
ASK_EVERY = 97                 # frames between hints asked for (odd, so they fall on all kinds of moment)
MAP_COLUMNS = 32
LINES = 3
PLAYING = 0x00
GAME_STATE = 0x99               # the state's mode byte (src/state.h)
SHOWN_DISAGREEMENTS = 10


def letter_of_tiles() -> dict[int, str]:
    """The font's tile numbers as letters (make_pictures.py's FONT_ORDER is the tiles' order)."""
    return {tile: letter for tile, letter in enumerate(make_pictures.FONT_ORDER)}


class Asking(E.SnesLab):
    """The engine check's lab, asking for a hint now and then and reading it off the band below."""

    rom = b""
    palette = game_palette.load()

    def __init__(self, rom_path: str, shareable_build: bool) -> None:
        super().__init__(rom_path, shareable_build)
        where = E.symbols(shareable_build)
        self.asked_at = where["tccs_src/hints.asm_hint_asked"] - E.WORK_RAM_BANK
        self.band_at = where["tccs_src/status.asm_band_below"] - E.WORK_RAM_BANK
        self.letters = letter_of_tiles()
        self.checked = 0
        self.disagreements: list[tuple[list[str], list[str]]] = []

    def run(self, frames: int = 1, held: Iterable[int] = ()) -> None:
        for _frame in range(frames):
            if self.frames % ASK_EVERY == 0 and self.peek(GAME_STATE) == PLAYING:
                self.ask(held)
            else:
                super().run(1, held)

    def ask(self, held: Iterable[int]) -> None:
        """Ask, run the frame, and compare: the SNES works its hint out after the frame's game step, so
        the rules are asked about the state after it too."""
        self.snes.ram[self.asked_at] = 1
        super().run(1, held)
        state = GameState(self.snapshot(), self.rom, self.palette)
        if state.mode != "playing":
            return
        wanted = [line.replace("SPACE", "B") for line in hints.hint(state, self.rom)]
        shown = self.band_lines()
        self.checked += 1
        if shown != wanted + [""] * (LINES - len(wanted)):
            self.disagreements.append((wanted, shown))

    def band_lines(self) -> list[str]:
        """The band below's first three rows, as text."""
        lines = []
        for row in range(LINES):
            letters = []
            for column in range(MAP_COLUMNS):
                place = self.band_at + (row * MAP_COLUMNS + column) * 2
                entry = int(self.snes.ram[place]) | int(self.snes.ram[place + 1]) << 8
                letters.append(self.letters.get(entry & 0x3FF, " ") if entry else " ")
            lines.append("".join(letters).strip())
        return lines


def main() -> None:
    shareable_build = "--faithful" not in sys.argv
    numbers = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    frames = int(numbers[0]) if numbers else FRAMES_PER_GAME
    Asking.rom = E.shareable.floors_rom() if shareable_build else E.R.load()
    lab = Asking(E.build(shareable=shareable_build), shareable_build)
    tally = E.V.Tally()
    for game in E.V.GAMES:
        E.V.check_game(lab, Asking.rom, game, frames, 0, tally)  # type: ignore[arg-type]
    agreed = lab.checked - len(lab.disagreements)
    print(f"{agreed}/{lab.checked} hints: the SNES said what the remaster's rules say")
    for wanted, shown in lab.disagreements[:SHOWN_DISAGREEMENTS]:
        print(f"  the rules: {' / '.join(wanted)}\n  the SNES:  {' / '.join(shown)}")
    sys.exit(1 if lab.disagreements else 0)


if __name__ == "__main__":
    main()
