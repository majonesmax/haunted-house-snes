"""Build the ROM: make, with PVSnesLib's rules, then the ROM and its symbols copied into build/.

Usage: python tools/build.py [--faithful]      -> build/shareable/haunted_house.sfc (or build/faithful/)
As a module: build(shareable=True) -> the ROM's path, and symbols(shareable) -> {label: address}.
"""

import os
import shutil
import subprocess
import sys

import make_mansion
import make_pictures
import make_sound

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PVSNESLIB_HOME = os.path.join(ROOT, "tools", "pvsneslib", "pvsneslib")
ROM_NAME = "haunted_house"


def output_folder(shareable: bool) -> str:
    return os.path.join(ROOT, "build", "shareable" if shareable else "faithful")


def build(shareable: bool = True) -> str:
    """Make the ROM and copy it, with its symbol file, into build/; returns the ROM's path."""
    if not os.path.exists(os.path.join(PVSNESLIB_HOME, "devkitsnes")):
        sys.exit("PVSnesLib is not fetched: python tools/get_tools.py")
    folder = output_folder(shareable)
    os.makedirs(folder, exist_ok=True)
    make_mansion.write(folder, shareable)
    make_pictures.write(folder, shareable)
    make_sound.write(folder)
    environment = {**os.environ, "PVSNESLIB_HOME": PVSNESLIB_HOME, "MANSION_DIR": folder}
    # always from scratch: the two builds share the sources but not the mansion
    subprocess.run(["make", "--no-print-directory", "--always-make"], cwd=ROOT, env=environment,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for ending in (".sfc", ".sym"):
        shutil.copy(os.path.join(ROOT, ROM_NAME + ending), os.path.join(folder, ROM_NAME + ending))
    return os.path.join(folder, ROM_NAME + ".sfc")


def symbols(shareable: bool = True) -> dict[str, int]:
    """The linker's symbols: label -> address (bank in the high byte: $7E0100 for work RAM, say)."""
    found = {}
    with open(os.path.join(output_folder(shareable), ROM_NAME + ".sym")) as symbol_file:
        for line in symbol_file:
            parts = line.split()
            if len(parts) == 2 and all(char in "0123456789abcdefABCDEF" for char in parts[0]):
                found[parts[1]] = int(parts[0], 16)
    return found


def rom_path(shareable: bool = True) -> str:
    return os.path.join(output_folder(shareable), ROM_NAME + ".sfc")


def shareable_wanted(arguments: list[str]) -> bool:
    return "--faithful" not in arguments


def main() -> None:
    print(build(shareable=shareable_wanted(sys.argv)))


if __name__ == "__main__":
    main()
