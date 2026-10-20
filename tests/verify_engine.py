"""Run the faithful SNES build beside the remaster's model of the original game, and check the SNES keeps
the game's whole state exactly as the model says, every frame.

This is the NES game's check (its tests/verify_engine.py) with the SNES in its place, and that was the
remaster's own check, tools/verify_player.py, with the 2600 replaced: the same bot, the same scenes, the
same comparison of $80-$CC and the other state bytes. It works because the engine keeps the state in a
128-byte block at the 2600's offsets (src/state.h). Where the model says the original crashes, the frame
isn't compared (the SNES doesn't crash) and the bot presses RESET, as it does for the original. It also
fails if the SNES ever took longer than a frame to work a frame out.

Needs the remaster beside this repository (../haunted-house) with your ROM in it, the NES game beside it
too (../haunted-house-nes: its mansion), and the snes9x core in cores/.

With --shareable it checks the shareable build the same way: the model runs the NES game's mansion (an
R.Floors, from its tools/shareable.py), floor by floor.

Usage: python tests/verify_engine.py [--shareable] [frames per game] [seed]   (exit code 1 on any mismatch)
"""

import faulthandler
import os
import sys
from typing import Iterable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
NES = os.path.join(os.path.dirname(ROOT), "haunted-house-nes")
sys.path.insert(0, REMASTER)
sys.path.insert(0, os.path.join(REMASTER, "tools"))
sys.path.insert(0, os.path.join(NES, "tools"))
sys.path.insert(0, os.path.join(ROOT, "tools"))   # first: this repository's build.py, not the NES's
from build import build, symbols  # noqa: E402
import shareable  # noqa: E402
from snes import BUTTON_B, BUTTON_SELECT, BUTTON_START, Snes  # noqa: E402
from snes import BUTTON_DOWN, BUTTON_LEFT, BUTTON_RIGHT, BUTTON_UP  # noqa: E402
import verify_player as V  # noqa: E402
from lab import BUTTON, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_UP, RESET, SELECT  # noqa: E402

from game import rom as R  # noqa: E402

STATE_SIZE = 128
STATE_START = 0x80
WORK_RAM_BANK = 0x7E0000    # the symbols are 65816 addresses; the core hands out work RAM from 0
WATCHDOG_SECONDS = 1500     # far past a whole run's time: from then on, every Python thread's stack, often
RESET_HELD, AFTER_RESET = 5, 5
READY = 0x42                # src/main.c's ready_flag once the console is set up
BOOT_FRAMES = 120           # the most frames the ROM may take to get there
# the remaster's lab ids for the 2600's controls: the SNES pad's buttons that stand for them
ON_THE_PAD = {BUTTON: BUTTON_B, RESET: BUTTON_START, SELECT: BUTTON_SELECT, JOY_UP: BUTTON_UP,
              JOY_DOWN: BUTTON_DOWN, JOY_LEFT: BUTTON_LEFT, JOY_RIGHT: BUTTON_RIGHT}


class SnesLab:
    """The SNES, looking to the remaster's check like its 2600 lab: the same control ids, the same
    addresses, read from the state block."""

    def __init__(self, rom: str, shareable_build: bool):
        self.snes = Snes(rom)
        where = symbols(shareable_build)
        self.state_at = where["game_ram"] - WORK_RAM_BANK
        self.late_at = where["late_frames"] - WORK_RAM_BANK
        self.ready_at = where["ready_flag"] - WORK_RAM_BANK
        self.late_seen = 0
        self.late_scenes: list[tuple[bytes, list[int]]] = []   # (the state before, the controls held)
        self.boot()

    def boot(self) -> None:
        """Run until the ROM says it's set up (it takes a while: the console, then the engine's tables)."""
        for _frame in range(BOOT_FRAMES):
            if self.snes.ram[self.ready_at] == READY:
                return
            self.snes.run(1)
        raise RuntimeError("the ROM never got ready")

    def run(self, frames: int = 1, held: Iterable[int] = ()) -> None:
        before = self.snapshot()
        self.snes.run(frames, {ON_THE_PAD[control] for control in held})
        if self.late_frames() > self.late_seen:   # a frame ran late: keep its scene, to measure it
            self.late_seen = self.late_frames()
            self.late_scenes.append((before, sorted(held)))

    def hold(self, *held: int, frames: int = 1) -> None:
        self.run(frames, held)

    def reset(self) -> None:
        self.hold(RESET, frames=RESET_HELD)
        self.run(AFTER_RESET)

    def peek(self, address: int) -> int:
        return int(self.snes.ram[self.state_at + address - STATE_START])

    def poke(self, address: int, value: int) -> None:
        self.snes.ram[self.state_at + address - STATE_START] = value & 0xFF

    def snapshot(self) -> bytes:
        return bytes(self.snes.ram[self.state_at:self.state_at + STATE_SIZE])

    def late_frames(self) -> int:
        return int(self.snes.ram[self.late_at])


def main() -> None:
    faulthandler.dump_traceback_later(WATCHDOG_SECONDS, repeat=True)   # a run that never ends says where
    our_mansion = "--shareable" in sys.argv
    numbers = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    frames = int(numbers[0]) if numbers else V.FRAMES_PER_GAME
    seed = int(numbers[1]) if len(numbers) > 1 else 0
    lab = SnesLab(build(shareable=our_mansion), our_mansion)
    rom = shareable.floors_rom() if our_mansion else R.load()
    tally = V.Tally()
    for game in V.GAMES:
        V.check_game(lab, rom, game, frames, seed, tally)  # type: ignore[arg-type]
    V.report(tally)
    late = lab.late_frames()
    print(f"frames the SNES finished late: {late}")
    for number, (before, held) in enumerate(lab.late_scenes):
        path = os.path.join(ROOT, "build", f"late_scene_{number}.bin")
        with open(path, "wb") as scene:
            scene.write(before)
        print(f"  the state before late frame {number}, with {held} held, is in {path}")
    sys.exit(1 if tally.mismatches or late else 0)


if __name__ == "__main__":
    main()
