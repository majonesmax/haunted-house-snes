# The plan

A native Super Nintendo version of Atari 2600 *Haunted House*: the same game, rule for rule, drawn and
scored the way the [remaster](https://github.com/majonesmax/haunted-house-remastered)'s SNES look does it,
in the mansion of the [NES game](https://github.com/majonesmax/haunted-house-nes) - the Cellar, the Foyer,
the Gallery, the Bedrooms and the Attic.

## What it's built from

- **The rules**: the remaster's [docs/spec.md](../../haunted-house/docs/spec.md), and the same rules as code
  in its `game/player.py`, `game/monsters.py` and `game/sounds.py`. Those models predict the real game's
  every byte, every frame, so they are the reference this port is checked against - as they were for the
  NES game.
- **The mansion**: the NES game's `mansion/floors.txt` and the tools that turn it into tables
  (`tools/mansion.py`), read from the sibling repository; and, for the faithful build, the original's
  mansion from your own 2600 ROM (the NES game's `tools/extract.py`).
- **The look**: the remaster's SNES look (`looks/snes`): 15-bit colour, the match's light as a smooth warm
  gradient by colour math, moonlit walls and shafts of moonlight in game 1, see-through ghosts, lightning
  that washes the screen, and the *nocturne* pack drawn in 16-bit colour ramps.
- **The sound**: the remaster's orchestra (`music/orchestra.py`: organ, harpsichord, strings, harp, bell,
  brass, timpani) as sampled instruments on the SNES's sound chip, playing the same songs; and its twenty
  remastered effects.
- **Not the original's code.** The engine is written from the spec and the models, never translated from the
  disassembly - and not from the NES game's assembly either: it's written again, in C, so its owner can
  read it.

## The tools (docs/decisions.md says why)

- **C, with PVSnesLib** (816-tcc and WLA-DX): the game and its picture code in C; assembly only where a
  measurement says it's needed.
- **Terrific Audio Driver** for the sound chip: songs and effects as text (MML), instruments as samples.
- **snes9x's libretro core** to play the ROM in the checks (`tools/snes.py`, as the NES game's `tools/nes.py`);
  Mesen2 by hand, for its debugger.

Neither PVSnesLib nor the driver nor the core is committed: `tools/get_tools.py` fetches pinned versions.

## Two builds, one engine

| | Mansion | Art | Can be shared |
|---|---|---|---|
| **Faithful** | the original's, read from your own 2600 ROM when you build | our own | no - build it yourself |
| **Shareable** | the NES game's mansion, on the same rules | our own | yes |

The faithful build is how the engine is proved; the shareable build runs the same engine on the mansion
as data. Nothing from the 2600 ROM is ever committed, and neither is a faithful ROM.

## How the engine is checked

The game's state lives in one 128-byte block of work RAM with the 2600's layout: the same bytes, with the
same meanings, at the same offsets as the 2600's `$80`-`$FF`. The check plays the faithful build in the
emulator and runs `game/player.py` beside it with the same controls; after every frame it compares the
block. The crash and touching are handled as the NES game's check handles them (its `docs/plan.md`).

The controller: the D-pad is the joystick, B the button (A too), Start is RESET, Select is SELECT; the
lightning switch is a setting on the title, Y the hint, Y + Select the lights-on cheat.

## The steps

0. **Tools and a boot** - done: PVSnesLib and the driver fetched by `tools/get_tools.py`; a ROM that boots
   to a colour; `tools/snes.py` and `tests/test_boot.py`; the code checks (ruff, pyright, readability for
   the Python) and `.github/workflows/checks.yml`.
1. **The engine** - done: in C from the spec, the mansion as data; `tests/verify_engine.py` exact on both
   builds, 36,000 frames each, no frame late.
2. **The picture** - the SNES look: the floors in 16-colour tiles from the nocturne pack (the remaster's
   scenery code draws them, cut by a tool like the NES game's `make_art.py`); the status band; the match's
   light as colour math in a window round the eyes, its gradient by HDMA; the moonlight; sprites with soft
   outlines; the ghost on a translucent layer.
3. **The sound** - the driver in; the orchestra's instruments rendered short and encoded as samples; the
   songs from the pack's `music.json` written out as MML; the twenty effects.
4. **The screens** - the story, the title with its rain and fading lightning, the help, game over, the
   ending at dawn; the hints and notes in play.
5. **Release** - README with pictures, `build.yml` (a tag makes the release), the browser page with
   EmulatorJS's snes9x core, v1.0.0.

## The hard parts, as expected

- **The compiler.** 816-tcc is a small compiler with a history of wrong code in odd corners. The frame-exact
  check will catch any such case in the engine; the picture code needs looking at.
- **Video memory per frame.** The SNES copies about 6K to video RAM in a vertical blank at 60 Hz: the view's
  scrolling has to stream a row of tiles at a time, as the NES game does.
- **Sound memory.** The sound chip has 64K for the driver, the samples and the song: the orchestra's
  instruments must be short loops, chosen to fit.
- **The light.** One colour-math window per layer, so the gradient is the fixed colour changing by scanline
  (HDMA), not a true circle: close to the look, not the same picture.
