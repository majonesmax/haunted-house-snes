"""Play the ROM in the emulator for a while and save what's on screen - to look at the picture.

Usage: python tools/screenshot.py NAME [steps...] [--faithful]
  a step is FRAMES or FRAMES:BUTTONS, buttons from: up down left right a b x y l r start select
  e.g.   python tools/screenshot.py start 60 10:start 30 40:b 120:left
Saves shots/NAME.png (at 3x).
"""

import os
import sys

import numpy as np
from PIL import Image

from build import build, shareable_wanted
import snes as S

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "shots")
SCALE = 3
BUTTONS = {"up": S.BUTTON_UP, "down": S.BUTTON_DOWN, "left": S.BUTTON_LEFT, "right": S.BUTTON_RIGHT,
           "a": S.BUTTON_A, "b": S.BUTTON_B, "x": S.BUTTON_X, "y": S.BUTTON_Y, "l": S.BUTTON_L,
           "r": S.BUTTON_R, "start": S.BUTTON_START, "select": S.BUTTON_SELECT}


def play(machine: S.Snes, steps: list[str]) -> None:
    for step in steps:
        frames, _, buttons = step.partition(":")
        held = {BUTTONS[name] for name in buttons.split("+") if name}
        machine.run(int(frames), held)


def main() -> None:
    arguments = [argument for argument in sys.argv[1:] if not argument.startswith("--")]
    name, steps = arguments[0], arguments[1:]
    machine = S.Snes(build(shareable=shareable_wanted(sys.argv)))
    play(machine, steps)
    if machine.picture is None:
        sys.exit("no picture yet")
    os.makedirs(SHOTS, exist_ok=True)
    picture = Image.fromarray(np.ascontiguousarray(machine.picture))
    picture.resize((picture.width * SCALE, picture.height * SCALE), Image.Resampling.NEAREST).save(
        os.path.join(SHOTS, f"{name}.png"))
    print(os.path.join(SHOTS, f"{name}.png"), picture.size)


if __name__ == "__main__":
    main()
