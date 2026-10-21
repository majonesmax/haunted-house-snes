# Working on the SNES game with an AI assistant

Notes for Claude Code (or any coding assistant) working in this repository. People: the same notes are a quick
tour.

*Haunted House: By Matchlight* for the Super Nintendo: Atari 2600 *Haunted House*, rule for rule, as a native
SNES game, in C. It's the third of three sister projects, kept side by side (`../haunted-house` the remaster,
`../haunted-house-nes` the NES game): the remaster's spec and models are the rules, the NES game's mansion is
the house, and this repository reads both at build time. The plan: [docs/plan.md](docs/plan.md); why things
are as they are: [docs/decisions.md](docs/decisions.md).

## Commands

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
python tools/get_tools.py               # PVSnesLib, the audio driver's source and the snes9x core (not committed)
python tools/build.py                   # build/shareable/haunted_house.sfc (the NES game's mansion)
python tools/build.py --faithful        # build/faithful/: the original's mansion, from your 2600 ROM (never shared)
python tools/play.py [--faithful] [--map]   # play it: one window, the picture and the sound (--map: the engine's state beside)
python tools/screenshot.py NAME 60 10:start 30   # play some frames, save shots/NAME.png
python tests/test_boot.py [--faithful]  # the ROM boots and counts frames
python tools/make_sound.py                # the sound's samples, effects, songs (tools/make_songs.py) and driver data
python tests/test_events.py [--faithful] [frames]   # each frame's sound effect is the one the remaster's rules ask for
python tests/test_hints.py [--faithful] [frames]    # each hint says what the remaster's rules say
python tests/test_light.py [--faithful]             # a match lit again where the last went out gives light
python tests/verify_engine.py [--shareable] [frames] [seed]   # the engine against the remaster's model, frame
                                        # by frame (run it after any change to src/, on both builds)
python tests/test_compiler.py           # the compiler's wrong condition shapes are the known ones
python tools/readme_media.py            # the README's pictures, from the shareable ROM (docs/media/)
git tag v1.0.0 && git push origin v1.0.0   # a release: build.yml checks, builds, releases, puts the page up
ruff check --config ruff.toml . && python tools/readability.py && pyright   # the code rules
```

## Rules

- **The engine is written from the spec** (`../haunted-house/docs/spec.md` and `game/player.py`), never from
  the original's code, and not from the NES game's assembly.
- **Prove it.** After any change to `src/`, run `tests/verify_engine.py` on both builds; after any change to
  the sound's events, `tests/test_events.py` too.
- **Never commit** the 2600 ROM, a faithful ROM, the emulator core, PVSnesLib, the audio driver, or
  `private/`.
- **Art and songs are text**, drawn and written in the sibling repositories' sources and built from there.
- **Look at your work.** After changing the picture, take a screenshot and read it before saying it's done.

## Readable code

The person who owns this code reads it rather than writes it, and is a C programmer. Write for them:

- Names say what things are: `monster`, not `m`; `match_lit`, not `ml`. Short names only for loop counters
  and coordinates.
- One idea per line; name the steps instead of nesting calls. Name the numbers: a `#define` or `enum` with a
  comment, never a bare `14`.
- Short functions, about 40 lines at most, with few branches.
- Fixed-width types (`u8`, `u16`) from PVSnesLib; no `int` whose size is a guess.
- **The compiler's weak spots** (816-tcc; `tests/test_compiler.py` proves them, and must keep passing):
  never write `!x` as an operand of `||`, nor as the first operand of `&&` - `a || !b`, `!a || b` and
  `!a && !b` compile wrong. Write `x == 0` instead. A lone `if (!x)` and `a && !b` are fine. Function
  calls and variable-distance shifts are dear: a loop over every scanline or column can't afford them
  (src/touching.c says how it keeps to a few).
- Comments say why. Each file starts with a comment saying what it is.
- Python tools follow the sister repositories' rules (`tools/readability.py`, ruff, pyright, types on every
  signature).
