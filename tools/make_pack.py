"""The pack the SNES look draws our mansion with: build/shareable/pack, made from the remaster's nocturne
pack (the SNES look's own, drawn for 16 bits). Nocturne has the original's four floors; our mansion has a
cellar and four floors, so each of ours borrows one of nocturne's styles (STYLES) - its floor, walls and
decorations - under our floor's number. The cast, the front door and the title's pictures are nocturne's.
(The faithful build draws the original's floors with nocturne itself.)

Usage: python tools/make_pack.py      (tools/make_pictures.py runs it)
"""

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NES = os.path.join(os.path.dirname(ROOT), "haunted-house-nes")
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
sys.path.insert(0, os.path.join(NES, "tools"))
import mansion as M  # noqa: E402

NOCTURNE = os.path.join(REMASTER, "packs", "nocturne")
OUTPUT = os.path.join(ROOT, "build", "shareable", "pack")
MANSION_TEXT = os.path.join(NES, "mansion", "floors.txt")
# our floors, by a word of their names, and the nocturne floor (1-4) whose style each borrows:
# 1 the foyer, 2 the dining hall, 3 the conservatory, 4 the attic
STYLES = {"cellar": 4, "foyer": 1, "gallery": 2, "bedrooms": 3, "attic": 4}
DEFAULT_STYLE = 1
SHARED = ("front_door.png", "title_mansion.png", "title_moon.png")


def floor_names() -> list[str]:
    with open(MANSION_TEXT) as mansion_file:
        return [floor.name.title() for floor in M.parse(mansion_file.read())]


def style_of(name: str) -> int:
    for word, style in STYLES.items():
        if word in name.lower():
            return style
    return DEFAULT_STYLE


def copy_floor_pictures(world: str, number: int, style: int) -> None:
    """Nocturne's pictures of floor `style`, as our floor `number`'s: floorN, wallN_*, decorN_*; and the
    flat wallN the scenery asks for before the top and face (its top will do: it's never drawn)."""
    for file in os.listdir(os.path.join(NOCTURNE, "world")):
        match = re.fullmatch(r"(floor|wall|decor)(\d)(.*)\.png", file)
        if match and int(match.group(2)) == style:
            ours = f"{match.group(1)}{number}{match.group(3)}.png"
            shutil.copy(os.path.join(NOCTURNE, "world", file), os.path.join(world, ours))
    shutil.copy(os.path.join(NOCTURNE, "world", f"wall{style}_top.png"), os.path.join(world, f"wall{number}.png"))


def main() -> None:
    names = floor_names()
    shutil.rmtree(OUTPUT, ignore_errors=True)
    world = os.path.join(OUTPUT, "world")
    os.makedirs(world)
    shutil.copytree(os.path.join(NOCTURNE, "cast"), os.path.join(OUTPUT, "cast"))
    for number, name in enumerate(names, start=1):
        copy_floor_pictures(world, number, style_of(name))
    for file in SHARED:
        shutil.copy(os.path.join(NOCTURNE, "world", file), os.path.join(world, file))
    shutil.copy(os.path.join(NOCTURNE, "music.json"), os.path.join(OUTPUT, "music.json"))
    with open(os.path.join(NOCTURNE, "pack.json")) as about:
        info = json.load(about)
    info["title"], info["floors"] = "Haunted House: By Matchlight", names
    info["description"] = "Our own mansion, a cellar and four floors, in nocturne's styles."
    with open(os.path.join(OUTPUT, "pack.json"), "w") as about:
        json.dump(info, about, indent=2)
    print(OUTPUT)


if __name__ == "__main__":
    main()
