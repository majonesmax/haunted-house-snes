# Decisions

The choices made in building the SNES game, newest first, each with what else was considered. The NES
game's log is the model for this one.

## 2026-10-20: the status band on the third layer; the panels, the lightning, dying and the cheat as colour math

- **The status band is BG3**, the SNES's 4-colour layer, with its priority bit set so it sits in front of
  the floor's layers; its tiles (the remaster's 5x7 font with its drop shadow, the item slots, the burning
  match, the lives' eyes) are made by `tools/make_pictures.py` from the same pictures the NES game's band
  uses, and its layout is the NES game's. The letters are drawn once and coloured by the map entry's
  palette (white, grey, dim grey), so one font serves all three. The band is worked out again only when
  something it shows has changed - the check for that is in assembly (`status_key_changed`,
  src/fast.asm), because in C the looking alone cost a tenth of the frame - and sent by DMA in the next
  blank. Considered: sprites for the numbers (the sprite table is the cast's); the band drawn into the
  floor's layers (they scroll).
- **The panels are the backdrop colour, changed line by line by HDMA** (the remaster's SNES look's
  gradient with its bevel), and a second HDMA channel turns the floor's layers off on the band's lines
  (the layers scroll under the band; BG3's tiles are see-through where they're not ink). The windows
  couldn't do it: in game 1 the walls aren't masked at all. Three HDMA channels (the light's, these two)
  cost about four scanlines of CPU time a frame.
- **The lightning, dying and the lights-on cheat reuse the light's colour math.** A flash (the spec's
  rule, as the NES game's `lightning_now`) unmasks the walls and adds a pale blue fixed colour to them
  outside the light; dying adds a pulsing red to the view's layers everywhere (the bands' backdrop and
  the band itself left alone); the cheat masks nothing and does no math. The registers are written only
  when the rules change. The cheat is the NES game's: the button held, Select toggles it, and the game
  doesn't hear that Select. In game 1 the walls stay moonlit through a flash, as the SNES look has it.

## The hard parts

- **The compiler is wrong about some conditions.** 816-tcc compiles `a || !b || c`, `!a || b` and
  `!a && !b` wrongly (the jumps between the terms land in the wrong places; the engine's check caught the
  first in touching, where a dying player was caught again every frame). `tests/test_compiler.py` builds a
  small ROM of such conditions and compares the compiler's answers with the truth, so the shapes that are
  safe to write are known, and CLAUDE.md says which to avoid.
- **The library's DMA takes the bank from the pointer, and a pointer to work RAM doesn't carry one.**
  `dmaCopyVram` copies from ROM fine; from a C array in work RAM it copies nothing (the array is above
  the 8K mirrored into bank 0). Anything in work RAM going to video memory by DMA sets the channel's
  registers itself with bank $7E (src/status.c `send_band`, as the HDMA tables do).
- **The blank is short, and the drawing isn't.** The vertical blank is lines 225-261 and the drawing
  starts about line 231 after the library's own work, so the drawing runs on into the picture. That's
  harmless for the sprite table (the library copies it in the next blank) and the HDMA tables (read line
  by line), but video memory takes writes only in the blank: the band's DMA, and a floor's pieces, go
  first. The light goes before the cast, since its table is read from the top of the picture.
  `draw_end_line` (picture.c) says where the drawing ended. Measured with probes on the scanline counter:
  a scanline is only about 230 CPU cycles, so each sprite costs about 4 lines even in assembly
  (`cast_place` works out its place, `cast_put` writes its entries), the light's 36 rows 14 lines, the
  colour rules 3, the band's check 1; the drawing takes about 33 lines with no match lit and 56 with one.
  Still to try if the budget gets tight: the light's rows for every centre precomputed in ROM (46K, split
  across two banks) and moved in with MVN, about 5 lines instead of 14.
- **The sprite table must reach the console in the blank, and the drawing isn't in it.** The library's
  `oamUpdate` copies the table at once; called at the end of the drawing, past the blank, the copy landed
  mid-picture and scrambled entries - a second ghost under the ghost, part of it turning into a bat. The
  library's blank interrupt already copies the table at the start of every blank (on frames that weren't
  late), so the call went; and since that copy is of the table drawn in the frame before, the layers'
  scroll and the light's HDMA table now wait a frame too (two light tables, built in turn), so the eyes
  and their light keep step with the floor.
- **A tall picture's lower half must sit below its upper half on the sprite sheet.** The sheet tool
  numbered a picture's blocks one after another along a row, so the ghost's lower half (and the stairs')
  sat beside its upper half; the SNES, and cast_put, look a block row down, and drew whatever was there -
  another ghost frame, or a bat. `free_place` (tools/make_pictures.py) now gives each picture a
  rectangle of its own shape.
- **A floor's pictures arrive only in the blank, a small piece at a time.** A floor came in 4K pieces,
  one a frame from wherever the drawing started; the last could run past the blank, and video memory
  drops what arrives then. So a few of the old floor's tiles stayed (the Foyer's blue wall edge at the
  foot of the Gallery's stairs), and the band's new floor name, sent after, was lost. Now the band goes
  first, and the floor comes in 1K pieces while the scanline counter says there's blank left.
- **The band's colours are sent every frame.** Once, in the first picture after start-up, a stray write
  landed on colour 1 (the band's white turned blue). The backdrop's HDMA leaves the colour address at 1
  after every line, so any stray write to the colour port lands there. Switching channels off in turn
  pinned it to that channel's presence, and skipping parts of the first frame's work moved it about,
  but the write itself wasn't found. 32 bytes a frame put the colours right whatever happens.
- **The engine check's late count depends on where the frame's work ends against the emulator's frame.**
  A wait for the blank before the first frame shifted that phase for good, and the count went from 0.5%
  to 2.1% with no more work done. It was taken out; numbers from the check are compared like for like.
- **The library borrows HDMA channel 3.** Its own copies (a floor's pieces to video memory, the palettes)
  leave the channel's registers pointing at what they copied; the light's HDMA then wrote palette data
  into the colour memory every line (the eyes went black, the band's gold turned purple) and took CPU
  time doing it. The light points its channel at its table every frame (`send_table`); the band's
  channels 4 and 5, set once, were left alone.
- **A `jsr` to a local subroutine inside `cast_place` stopped the ROM dead** (the first frame never
  finished), with the index registers 16 bits wide; the same instruction serves `light_rows` and
  `status_key_changed` with them 8 bits wide. Not understood; the two uses were inlined.
- **A frame is about 59,000 cycles, and this compiler's code spends them fast**: roughly a scanline of
  the 262 for every five statements, a few hundred cycles a call, a loop for every shift by a variable
  amount. The touching pass (src/touching.c) first walked every scanline with several calls each and took
  three frames; then every row of the sprite, which for the stairs' 17 rows was half a frame. It now tests
  only the rows the eyes' three lines meet (at most six) and, on the drop search's frames, gathers the
  rows by the plan's 16-unit rows with one lookup a row, so the wall under the sprite is worked out at
  most three times. Measured with `end_line` (main.c: the scanline the frame's work ended on; the work
  starts about 30 lines before line 0 and must end before 225): an ordinary frame ends by line 80, one
  with a sprite near the eyes by 150, the worst seen - dying by matchlight with the stairs showing and a
  drop search running - at 197. The picture (step 2) adds its own: the sprites, and the light's window
  rows, are put together in assembly (src/fast.asm) after the C took half a frame for them; the items and
  the stairs are only looked at every fourth frame; the light's rows are kept while the eyes only move
  up or down. Even so a frame now and then runs over - a few in a thousand, walking by matchlight - which
  in play is a frame the picture holds, nothing a player sees. So the engine's check waits a late frame
  out and counts it, and fails only if more than 2% of frames run late (it was zero for the engine
  alone). FastROM (the CPU at 3.58 MHz for ROM reads) is on.

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
