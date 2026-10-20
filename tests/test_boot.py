"""The ROM builds, boots in the emulator, sets the console up and counts frames.

Usage: python tests/test_boot.py [--faithful]      (exit code 1 on failure)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
from build import build, shareable_wanted, symbols  # noqa: E402
from snes import Snes  # noqa: E402

READY = 0x42              # src/main.c's ready_flag once the console is set up
WORK_RAM_BANK = 0x7E0000  # the symbols' addresses are in the 65816's map; the core hands out work RAM from 0
FRAMES = 60
SLACK = 2                 # frames the counter may be out by (the boot's last frames)


def main() -> None:
    shareable = shareable_wanted(sys.argv)
    snes = Snes(build(shareable=shareable))
    where = symbols(shareable)
    frame_count, ready_flag = where["frame_count"] - WORK_RAM_BANK, where["ready_flag"] - WORK_RAM_BANK
    snes.run(10)
    if snes.ram[ready_flag] != READY:
        found = snes.ram[ready_flag]
        sys.exit(f"FAIL: ready_flag is ${found:02X}, not ${READY:02X}: the console never got set up")
    before = int(snes.ram[frame_count]) | int(snes.ram[frame_count + 1]) << 8
    snes.run(FRAMES)
    after = int(snes.ram[frame_count]) | int(snes.ram[frame_count + 1]) << 8
    counted = after - before
    if abs(counted - FRAMES) > SLACK:
        sys.exit(f"FAIL: {counted} frames counted in {FRAMES}")
    print(f"ready ${READY:02X}, {counted} frames counted in {FRAMES}: OK")


if __name__ == "__main__":
    main()
