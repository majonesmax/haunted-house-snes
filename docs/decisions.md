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

## 2026-10-20: the sound effects as notes on sampled instruments, not recordings

- **The effects are played, not stored.** The remaster's orchestral effects add up to 17 seconds of sound,
  about 300K as SNES samples; sound memory is 64K, the driver's included. So tools/make_sound.py makes the
  orchestra's instruments into samples - the steady ones (organ, strings, brass) as one looped cycle of 64
  samples, the struck ones (harp, bell, harpsichord, timpani, a knock on wood, the door's creak) as short
  one-shots at 8-16 kHz - and writes each effect as the driver's MML: the remaster's own notes, on those
  instruments. Twelve instruments and twenty effects take about 20K. The scrapes, the breath and the
  thunder are the sound chip's noise generator.
- **An effect plays on one channel**, so where the remaster layers sounds at once the SNES plays them one
  after another, or keeps the telling part (the stairs' harp, not its footfalls under it). The three
  chords an effect needs - the ghost's organ, the whole urn's strings, the stab of being caught - are each
  one looped waveform with every note in (whole numbers of cycles in a 512- or 2048-sample loop), so they
  still sound as chords and can be played at any pitch.
- **What's heard is the remaster's music/events.py**, as the NES game's audio.s has it, in assembly
  (src/fast.asm, audio_events): in C it took 14 scanlines a frame, and the late frames went from 0.5% to
  1.6%. `tests/test_events.py` runs the engine check's bot and has the remaster's own EventWatcher, given
  each frame's state, say which effect it asks for; the SNES must choose the same, and does on every frame.
  It caught two differences from the remaster: the frame after RESET (everything changes, nothing happens)
  was heard, and a monster coming in while the player was dying wasn't.
- **The driver is started before the library's console set-up** (it wants interrupts off), with the
  silent song loaded so that effects play: the driver plays nothing until a song is in. The start-up
  takes about 36 frames now, most of it loading the sound.
- **A name clash cost an hour.** The new sound code's `sound_frame` had the name of the engine's own
  (sounds.c, the 2600's sound state); the linker kept one without complaint, so the main loop ran the
  engine's sound step twice and the new code not at all. The SNES's sound is audio.c, `audio_frame`.
- **The ROM is 512K now**: the code and pictures fill the first 256K, the sound data starts at bank 8.
- **The music is the soundtrack's notation turned into MML**, not recordings (tools/make_songs.py): the
  melody on channel A, the style's accompaniment on B-D, the bass on E, the drums on F (timpani, and the
  sound chip's noise for snare and hat), the echo for the hall; G and H are left to the effects. Twelve
  songs take about 6K. The driver holds one song at a time, and loading another stops all sound for a few
  frames, so a new song waits until the last effect has finished (each effect's length is worked out from
  its notes): the monster's arrival is heard whole, then the tension music comes in. The driver's
  tad_isSfxPlaying() turned out to mean "effects aren't paused", not "an effect is sounding".
- **Loading a song costs frame time** (256 bytes a frame to the sound chip), and the late frames went from
  0.85% to 1.3% in the engine check, whose bot changes floors and meets monsters far more than a player
  does. Under the 2% allowed, but the margin is getting smaller.
- **The play window let the sound set its pace.** pygame's clock counts whole milliseconds and ran the
  window at 52 frames a second, not 60: the emulator made seven-eighths of the sound the sound card
  played, and the gaps came out as skipping and clicks (the first thing the owner heard). Now the window
  runs a frame whenever fewer than 75 ms of sound are queued, so the game runs at its own speed and the
  sound never runs dry. The drums' snare and hat were also much louder and longer than the remaster's;
  they're at its levels now.
- **The thunder is a timpani roll and a sampled rumble, not the sound chip's noise.** Being caught makes
  the walls flash while you die, and each flash's thunder was raw noise - a burst of hiss, 15% of it above
  3 kHz, that the owner heard as static. Now it's the remaster's: a soft crack, three timpani strokes, and
  a rumble - noise filtered to 30-700 Hz, as music/house.py makes it, in a 2048-sample loop at 4 kHz
  (filtered round the loop, so it loops without a seam; about 1K).
- **Another name clash**: the NES game's tools/make_music.py was found before this repository's on the
  import path (the picture tool puts the NES tools first), so the song tool is make_songs.py.

## 2026-10-21: the full screens

- **The hints and notes are the NES game's, in C** (src/hints.c, from the remaster's game/hints.py): X
  asks, the band below shows three lines for six seconds, then the floor's name again. tests/test_hints.py
  asks during the engine check's play and reads the words back off the band: they must be the remaster's
  hint() for the same state. The win at the door warms the view by the fixed colour, as the SNES look's
  lighten, with YOU ESCAPED! in the logo's letters.
- **Play's frame is full**, so what runs every frame in play is kept cheap: the screens and the notes
  check a few bytes and do nothing unless something's changed; the sprites' and the animation's small
  helpers are macros (a call costs more than a scanline on this compiler); a monster's facing is watched
  only while it shows; the song is chosen every other frame. Late frames: 1.1% (shareable) and 1.4%
  (faithful), from 2.0% and 1.9%. Most of what's left is the drop search's frames, the engine's heaviest;
  its wall test in assembly is the next lever if it's ever needed.

- **A screen is a picture set like a floor's** (tools/make_screens.py, through make_pictures.py's tile
  cutting), loaded by the same loader: the title (game select, game over, and the help behind it) and the
  ending. The remaster's SNES look draws them; the moving parts are left out of the picture and done by
  the SNES: the eyes in the window, the walk at dawn and the rain are sprites, the words are on the third
  layer, the logo's letters are the font at twice its size with their red shadow.
- **The sky is the backdrop, set line by line by HDMA** from tables in the ROM, so it's as smooth as the
  remaster's gradient; the title's lightning is 14 more tables, each frame of the flash's fade already
  brightened, so a flash costs nothing. The glow round the moon (or the sun) is the second layer, on the
  sub-screen, added to the backdrop alone by colour math: it lights only the sky, as the remaster's does.
  A glow is one tint at 15 strengths, one palette: with the glow's shades spread over the picture's
  palettes it came out as blocks.
- **The remaster draws 240 lines; the SNES shows 224**: 8 come off the top (sky) and 8 off the bottom
  (hill), which keeps the logo, the key hints and the walk at dawn on the screen.
- **The story swallows every button** until one is pressed and let go (the NES game's way); the engine
  check presses X, no 2600 control, past it. X opens the help on the title.
- **Three traps on the way**: (1) WLA-DX sizes an instruction by the last REP/SEP it read, not by how the
  code gets there - aim_sky's ending branch, after the title's 16-bit code, had its first load sized for
  16 bits while the CPU arrived in 8, and the misread instructions wrecked the stack (the main loop
  stopped at the ending); every branch label in src/fast.asm was checked for the same. (2) Variables with
  starting values went to the second work-RAM bank and were listed twice in the symbols; the screen's
  number seemed to change by itself, so no variable has a starting value now - they're set in set-up
  code. (3) A sprite pixel of pure black came out bright blue (0x7E00) though colour memory read back
  black; one step above black draws right. Not understood; the window's dark sprites use (8, 8, 8).

## 2026-10-21: late frames are the ROM's own count

- **The engine check now judges late frames by the ROM's count**, not by what it sees from outside. The
  ROM counts a frame late when its work missed the blank (the picture held for a frame): what a player
  would notice. From outside, the check counted a frame late when the game's frame counter hadn't moved
  by the end of one emulator frame, which also depends on where the emulator's frame ends against the
  game's work. The two agreed until step 4 made the work end later in the picture; then the outside
  count ran to nearly twice the ROM's. Both are printed.
- **The match's light's rows are copied from the ROM**, made in advance for every place across the
  screen (36 rows of 5 bytes, 46K in two banks), with the 65816's block move: about 5 scanlines a frame
  where working them out took 15. The screens had added about 8 lines to every play frame, and the
  bot's heaviest frames were already at the limit.

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
