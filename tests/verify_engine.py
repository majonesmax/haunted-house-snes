"""Run the faithful SNES build beside the remaster's model of the original game, and check the SNES keeps
the game's whole state exactly as the model says, every frame.

This is the NES game's check (its tests/verify_engine.py) with the SNES in its place, and that was the
remaster's own check, tools/verify_player.py, with the 2600 replaced: the same bot, the same scenes, the
same comparison of $80-$CC and the other state bytes. It works because the engine keeps the state in a
128-byte block at the 2600's offsets (src/state.h). Where the model says the original crashes, the frame
isn't compared (the SNES doesn't crash) and the bot presses RESET, as it does for the original. A game
frame the SNES takes longer than a frame over is waited for (the picture holds a frame; the game is no
different), counted, and allowed up to a small share of all frames.

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
from snes import BUTTON_DOWN, BUTTON_LEFT, BUTTON_RIGHT, BUTTON_UP, BUTTON_X  # noqa: E402
import verify_player as V  # noqa: E402
from lab import BUTTON, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_UP, RESET, SELECT  # noqa: E402

from game import rom as R  # noqa: E402

STATE_SIZE = 128
STATE_START = 0x80
WORK_RAM_BANK = 0x7E0000    # the symbols are 65816 addresses; the core hands out work RAM from 0
WATCHDOG_SECONDS = 1500     # far past a whole run's time: from then on, every Python thread's stack, often
RESET_HELD, AFTER_RESET = 5, 5
STORY_KEY_FRAMES = 2       # past the story at start-up: X held this long, then let go as long
MOST_LATE_PERCENT = 2.0     # how many frames in a hundred may run late (docs/decisions.md, "The hard parts")
KEPT_LATE_SCENES = 8        # late frames whose scenes are saved, to measure them
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
        self.frames_at = where["frames_done"] - WORK_RAM_BANK
        self.frames = 0                                          # game frames run...
        self.late = 0                                            # ...and the SNES's frames they ran over
        self.late_scenes: list[tuple[bytes, list[int]]] = []   # (the state before, the controls held)
        self.boot()

    def frames_done(self) -> int:
        """The ROM's count of game frames worked out to the end."""
        return int(self.snes.ram[self.frames_at]) | int(self.snes.ram[self.frames_at + 1]) << 8

    def boot(self) -> None:
        """Run until the ROM says it's set up (it takes a while: the console, then the engine's tables);
        then past the story, which the game hears nothing through: X, no 2600 control, ends it, and once
        it's let go the title shows."""
        for _frame in range(BOOT_FRAMES):
            if self.snes.ram[self.ready_at] == READY:
                self.snes.run(STORY_KEY_FRAMES, {BUTTON_X})
                self.snes.run(STORY_KEY_FRAMES)
                return
            self.snes.run(1)
        raise RuntimeError("the ROM never got ready")

    def run(self, frames: int = 1, held: Iterable[int] = ()) -> None:
        """Run game frames: each takes a frame of the SNES's, or more if the game's work ran late (the
        picture then just holds a frame); the controls are held until the frame is done."""
        buttons = {ON_THE_PAD[control] for control in held}
        for _frame in range(frames):
            before = self.snapshot()
            started = self.frames_done()
            self.snes.run(1, buttons)
            while self.frames_done() == started:
                self.snes.run(1, buttons)
                self.late += 1
                if len(self.late_scenes) < KEPT_LATE_SCENES:   # keep its scene, to measure it
                    self.late_scenes.append((before, sorted(held)))
            self.frames += 1

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
        """The ROM's own count of frames that ran late (it agrees with `late`, counted from outside)."""
        return int(self.snes.ram[self.late_at]) | int(self.snes.ram[self.late_at + 1]) << 8


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
    late_rate = 100 * lab.late_frames() / lab.frames   # the ROM's own count: frames that missed their blank
    print(f"frames the SNES finished late: {lab.late_frames()} of {lab.frames} ({late_rate:.2f}%, by the "
          f"ROM's own count; seen from outside, {lab.late}); allowed: up to {MOST_LATE_PERCENT}%")
    for number, (before, held) in enumerate(lab.late_scenes):
        path = os.path.join(ROOT, "build", f"late_scene_{number}.bin")
        with open(path, "wb") as scene:
            scene.write(before)
        print(f"  the state before late frame {number}, with {held} held, is in {path}")
    sys.exit(1 if tally.mismatches or late_rate > MOST_LATE_PERCENT else 0)


if __name__ == "__main__":
    main()
