"""The mansion's tables as C, for the engine to read: the sibling repositories' tools make the bytes (the NES
game's tools/extract.py from your 2600 ROM for the faithful build, its tools/shareable.py from its
mansion/floors.txt for the shareable one), and this writes them out as constant arrays.

Writes, in build/<kind>/:
  mansion_tables.h   the constants (#define) and the tables' declarations
  mansion_data.inc   the tables' bytes, included by src/mansion.c

Usage: python tools/make_mansion.py [--faithful]      (tools/build.py runs it)
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NES = os.path.join(os.path.dirname(ROOT), "haunted-house-nes")
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
sys.path.insert(0, os.path.join(NES, "tools"))
sys.path.insert(0, REMASTER)
import extract as E  # noqa: E402
import shareable as S  # noqa: E402

from game import rom as R  # noqa: E402

BYTES_PER_LINE = 16
# the labels the engine has functions named after, as the tables are named in C
C_NAMES = {"new_game": "new_game_bytes", "stairs_here": "rooms_with_stairs"}
Tables = dict[str, bytes]
Constants = list[tuple[str, int]]


def faithful(rom: bytes) -> tuple[Constants, Tables, Constants, bytes]:
    """The original's tables, each per-floor one repeated for the four floors (tools/extract.py's way)."""
    tables = {}
    for label, address, length, _what in E.TABLES:
        start = address - R.ROM_START
        data = rom[start:start + length]
        tables[label] = data * E.FLOOR_COUNT if label in E.PER_FLOOR else data
    eyes = [(label, R.byte_at(rom, address)) for label, address in E.EYES]
    constants = E.CONSTANTS + [("GHOST_START_FLOOR", E.FLOOR_COUNT - 1), ("FLOOR_COUNT", E.FLOOR_COUNT)]
    return constants, tables, eyes, E.random_bits(rom)


def shareable() -> tuple[Constants, Tables, Constants, bytes]:
    floors, look = S.read_floors(), S.cast_look()
    tables = {label: data for label, (data, _what) in S.all_tables(floors, look).items()}
    return S.constants(floors), tables, S.eyes_bytes(look), S.random_bits()


def c_name(label: str) -> str:
    return C_NAMES.get(label, label)


def byte_lines(data: bytes) -> list[str]:
    lines = []
    for start in range(0, len(data), BYTES_PER_LINE):
        chunk = data[start:start + BYTES_PER_LINE]
        lines.append("    " + ", ".join(f"0x{value:02X}" for value in chunk) + ",")
    return lines


def header_text(constants: Constants, tables: Tables, eyes: Constants) -> str:
    lines = ["/* The mansion's constants and tables: tools/make_mansion.py. Don't edit. */",
             "#ifndef MANSION_TABLES_H", "#define MANSION_TABLES_H", "#include <snes.h>", ""]
    lines += [f"#define {name} 0x{value:02X}" for name, value in constants]
    lines += [f"#define {label.upper()}_SIZE {length}   /* per floor */"
              for label, _address, length, _what in E.TABLES if label in E.PER_FLOOR]
    lines += [f"#define {label.upper()} 0x{value:02X}" for label, value in eyes]
    lines += [""] + [f"extern const u8 {c_name(label)}[];" for label in tables]
    lines += ["extern const u8 random_bits[];"]
    return "\n".join(lines + ["", "#endif", ""])


def data_text(tables: Tables, bits: bytes) -> str:
    lines = ["/* The mansion's tables' bytes: tools/make_mansion.py. Don't edit. */", ""]
    for label, _address, _length, what in E.TABLES:
        lines += [f"/* {what} */" if what else "", f"const u8 {c_name(label)}[] = {{"]
        lines += byte_lines(tables[label])
        lines += ["};", ""]
    lines += ["/* the mood sound's random bits, eight to a byte */", "const u8 random_bits[] = {"]
    lines += byte_lines(bits) + ["};", ""]
    return "\n".join(line for line in lines if line is not None)


def write(folder: str, shareable_build: bool) -> None:
    if shareable_build:
        constants, tables, eyes, bits = shareable()
    else:
        constants, tables, eyes, bits = faithful(E.checked_rom(E.DEFAULT_ROM))
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "mansion_tables.h"), "w") as header:
        header.write(header_text(constants, tables, eyes))
    with open(os.path.join(folder, "mansion_data.inc"), "w") as data:
        data.write(data_text(tables, bits))


def main() -> None:
    shareable_build = "--faithful" not in sys.argv
    folder = os.path.join(ROOT, "build", "shareable" if shareable_build else "faithful")
    write(folder, shareable_build)
    print(os.path.join(folder, "mansion_tables.h"))


if __name__ == "__main__":
    main()
