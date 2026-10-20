"""The compiler's weak spots, proved: a small ROM (tests/compiler_check/) evaluates logical conditions of
every shape the engine might use, and this compares its answers with the truth. The shapes known to be
wrong are expected to stay wrong (CLAUDE.md says not to write them); the rest must be right. A change in
either - a fixed compiler, or a new wrong shape - fails the test, so the list stays true.

Usage: python tests/test_compiler.py      (exit code 1 on a surprise)
"""

import os
import subprocess
import sys
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from build import PVSNESLIB_HOME  # noqa: E402
from snes import Snes  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiler_check")
ROM = os.path.join(HERE, "compiler_check.sfc")
SYMBOLS = os.path.join(HERE, "compiler_check.sym")
WORK_RAM_BANK = 0x7E0000
DONE = 0x42
BOOT_FRAMES = 120
VALUES = (0, 1, 0xFE)
Truth = Callable[[int, int, int], object]   # the truth of an expression in a, b and c
# each expression as the ROM writes it, the truth, and whether the compiler is known to get it wrong
EXPRESSIONS: list[tuple[str, Truth, bool]] = [
    ("a || b", lambda first, second, third: first or second, False),
    ("a || b || c", lambda first, second, third: first or second or third, False),
    ("a || !b || c", lambda first, second, third: first or not second or third, True),
    ("!a || b", lambda first, second, third: not first or second, True),
    ("a && b", lambda first, second, third: first and second, False),
    ("a && !b", lambda first, second, third: first and not second, False),
    ("!a && !b", lambda first, second, third: not first and not second, True),
    ("(a && b) || c", lambda first, second, third: (first and second) or third, False),
    ("a || (b && c)", lambda first, second, third: first or (second and third), False),
    ("!(a || b)", lambda first, second, third: not (first or second), False),
    ("a != 0 && b != 0", lambda first, second, third: first != 0 and second != 0, False),
    ("a && !b && c", lambda first, second, third: first and not second and third, False),
    ("!a || !b || !c", lambda first, second, third: not first or not second or not third, True),
    ("(a & 0x40) && !(b & 0x80) && c",
     lambda first, second, third: (first & 0x40) and not (second & 0x80) and third, False),
    ("a == 1 || b == 1 || c == 1",
     lambda first, second, third: first == 1 or second == 1 or third == 1, False),
    ("(a || b) && !c", lambda first, second, third: (first or second) and not third, False),
]


def build() -> None:
    environment = {**os.environ, "PVSNESLIB_HOME": PVSNESLIB_HOME}
    subprocess.run(["make", "--no-print-directory", "--always-make"], cwd=HERE, env=environment, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def symbol(name: str) -> int:
    with open(SYMBOLS) as symbols:
        for line in symbols:
            parts = line.split()
            if len(parts) == 2 and parts[1] == name:
                return int(parts[0], 16) - WORK_RAM_BANK
    raise KeyError(name)


def answers() -> list[list[int]]:
    """The ROM's results: per (a, b, c), a byte per expression."""
    snes = Snes(ROM)
    done, results = symbol("done_flag"), symbol("results")
    for _frame in range(BOOT_FRAMES):
        snes.run(1)
        if snes.ram[done] == DONE:
            break
    else:
        sys.exit("FAIL: the compiler check ROM never finished")
    count = len(VALUES) ** 3
    width = len(EXPRESSIONS)
    return [[int(byte) for byte in snes.ram[results + case * width:results + case * width + width]]
            for case in range(count)]


def wrong_cases(got: list[list[int]], index: int, truth: Truth) -> list[tuple[int, int, int]]:
    """The (a, b, c) for which the ROM's answer to expression `index` differs from the truth."""
    wrong = []
    case = 0
    for first in VALUES:
        for second in VALUES:
            for third in VALUES:
                expected = 1 if truth(first, second, third) else 0
                if got[case][index] != expected:
                    wrong.append((first, second, third))
                case += 1
    return wrong


def main() -> None:
    build()
    got = answers()
    surprises = []
    for index, (text, truth, known_wrong) in enumerate(EXPRESSIONS):
        wrong = wrong_cases(got, index, truth)
        if bool(wrong) != known_wrong:
            how = f"wrong for {wrong[:3]}" if wrong else "right now"
            surprises.append(f"  {text}: {how} (expected it {'wrong' if known_wrong else 'right'})")
    if surprises:
        sys.exit("FAIL: the compiler's answers changed:\n" + "\n".join(surprises))
    known = sum(1 for _text, _truth, known_wrong in EXPRESSIONS if known_wrong)
    print(f"{len(EXPRESSIONS)} condition shapes checked: {known} wrong as known, the rest right: OK")


if __name__ == "__main__":
    main()
