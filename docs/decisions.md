# Decisions

The choices made in building the SNES game, newest first, each with what else was considered. The NES
game's log is the model for this one.

## The hard parts

- **The compiler is wrong about some conditions.** 816-tcc compiles `a || !b || c`, `!a || b` and
  `!a && !b` wrongly (the jumps between the terms land in the wrong places; the engine's check caught the
  first in touching, where a dying player was caught again every frame). `tests/test_compiler.py` builds a
  small ROM of such conditions and compares the compiler's answers with the truth, so the shapes that are
  safe to write are known, and CLAUDE.md says which to avoid.
- **A frame is about 59,000 cycles, and this compiler's code spends them fast**: roughly a scanline of
  the 262 for every five statements, a few hundred cycles a call, a loop for every shift by a variable
  amount. The touching pass (src/touching.c) first walked every scanline with several calls each and took
  three frames; then every row of the sprite, which for the stairs' 17 rows was half a frame. It now tests
  only the rows the eyes' three lines meet (at most six) and, on the drop search's frames, gathers the
  rows by the plan's 16-unit rows with one lookup a row, so the wall under the sprite is worked out at
  most three times. Measured with `end_line` (main.c: the scanline the frame's work ended on; the work
  starts about 30 lines before line 0 and must end before 225): an ordinary frame ends by line 80, one
  with a sprite near the eyes by 150, the worst seen - dying by matchlight with the stairs showing and a
  drop search running - at 197. The engine's check fails on any late frame, so the picture code (step 2)
  must stay cheap; if it can't, the row loops go to assembly. FastROM (the CPU at 3.58 MHz for ROM reads)
  is on.

## 2026-10-20: C with PVSnesLib; the Terrific Audio Driver for sound; snes9x for the checks

**Chose:** the game written in C with PVSnesLib (4.6.0, July 2026: 816-tcc, WLA-DX, 64-bit macOS, Linux and
Windows builds, a test suite); the sound chip run by the Terrific Audio Driver (0.4.2, July 2026: songs and
effects as text, instruments as samples, a PVSnesLib API); the checks playing the ROM in snes9x's libretro
core, as the NES game's checks play theirs in FCEUmm's.

**Why:** the owner of this code reads C. The NES game's engine is 8,600 lines of assembly that only its
checks can vouch for; written again in C from the spec, with the same frame-exact check, the SNES game's
engine is one its owner can read. PVSnesLib carries the hardware (video memory, sprites, DMA, HDMA, input)
that assembly would have to; the driver carries the sound chip, which is a second processor with its own
program, and keeps the songs as text (the project's rule: art is text). The compiler is the weak point,
and the check is the answer to it.

**What else:** (1) 65816 assembly with ca65, porting the NES engine - the least new work and the same
assembler, but another engine its owner can't read, and the sound driver still to find. (2) Calypsi's C
compiler - a real optimising compiler with an SNES target since 5.12 (September 2025), but closed, and
licensed for private use only: not something a public, buildable repository can depend on. (3) WDC's own
compiler - old, and its availability has come and gone. (4) An LLVM backend for the 65816 - none exists in
a usable state as of October 2026; the one effort stalled in 2019.

**Cost:** two toolchains in the house (ca65 for the NES, WLA-DX here); the driver's compiler is built from
source on macOS (Rust), with no prebuilt binary but Windows.
