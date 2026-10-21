"""The sound effects fire on the right events: the SNES's choice each frame (audio_events, src/fast.asm)
against the remaster's own rules (its music/events.py) fed the same state.

The engine check's bot plays (tests/verify_engine.py: the same games and scenes); each frame the SNES's
128-byte state becomes the remaster's GameState, its EventWatcher says which effects that frame asks
for, and the one the SNES wants must be the first of those in the driver's numbering (it plays one a
frame, the lowest-numbered: tools/make_sound.py). The lightning is the SNES's own (the remaster reads it
from a 2600 drawing byte the engine doesn't keep), so the watcher is given the SNES's.

Usage: python tests/test_events.py [--faithful] [frames per game]   (exit code 1 on any disagreement)
"""

import collections
import os
import sys
from collections.abc import Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import verify_engine as E  # noqa: E402
import make_sound  # noqa: E402

from game.state import GameState  # noqa: E402
from music.events import EventWatcher  # noqa: E402
from game import palette as game_palette  # noqa: E402

NO_EFFECT = 0xFF
FRAMES_PER_GAME = 1500
SHOWN_DISAGREEMENTS = 10


class Listening(E.SnesLab):
    """The engine check's lab, hearing each frame's effect and asking the remaster which it should be."""

    order = make_sound.effect_order()
    rom = b""
    palette = game_palette.load()

    def __init__(self, rom_path: str, shareable_build: bool) -> None:
        super().__init__(rom_path, shareable_build)
        where = E.symbols(shareable_build)
        self.effect_at = where["audio_effect"] - E.WORK_RAM_BANK
        self.flash_at = where["lightning_flashing"] - E.WORK_RAM_BANK
        self.watcher = EventWatcher()
        self.heard: collections.Counter[str] = collections.Counter()
        self.disagreements: list[tuple[int, str, str]] = []

    def run(self, frames: int = 1, held: Iterable[int] = ()) -> None:
        for _frame in range(frames):
            super().run(1, held)
            self.listen()

    def wanted(self) -> str:
        """The effect the remaster's rules ask for this frame, first in the driver's numbering; or ''."""
        state = GameState(self.snapshot(), self.rom, self.palette)
        state.lightning = bool(self.snes.ram[self.flash_at])
        asked = self.watcher.update(state)
        found = [name for name in self.order if name in asked]
        return found[0] if found else ""

    def listen(self) -> None:
        number = int(self.snes.ram[self.effect_at])
        played = self.order[number] if number != NO_EFFECT else ""
        wanted = self.wanted()
        self.heard[played or "(none)"] += 1
        if played != wanted:
            self.disagreements.append((self.frames, wanted or "(none)", played or "(none)"))


def main() -> None:
    shareable_build = "--faithful" not in sys.argv
    numbers = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    frames = int(numbers[0]) if numbers else FRAMES_PER_GAME
    Listening.rom = E.shareable.floors_rom() if shareable_build else E.R.load()
    lab = Listening(E.build(shareable=shareable_build), shareable_build)
    tally = E.V.Tally()
    for game in E.V.GAMES:
        E.V.check_game(lab, Listening.rom, game, frames, 0, tally)  # type: ignore[arg-type]
    for name, count in sorted(lab.heard.items()):
        print(f"  {count:6d}  {name}")
    agreed = lab.frames - len(lab.disagreements)
    print(f"{agreed}/{lab.frames} frames: the SNES chose the effect the remaster's rules ask for")
    for frame, wanted, played in lab.disagreements[:SHOWN_DISAGREEMENTS]:
        print(f"  frame {frame}: the rules ask for {wanted}, the SNES chose {played}")
    sys.exit(1 if lab.disagreements else 0)


if __name__ == "__main__":
    main()
