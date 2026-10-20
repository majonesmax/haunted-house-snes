# Decisions

The choices made in building the SNES game, newest first, each with what else was considered. The NES
game's log is the model for this one.

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
