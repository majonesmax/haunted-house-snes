# Working on the SNES game with an AI assistant

Notes for Claude Code (or any coding assistant) working in this repository. People: the same notes are a quick
tour.

*Haunted House: By Matchlight* for the Super Nintendo: Atari 2600 *Haunted House*, rule for rule, as a native
SNES game, in C. It's the third of three sister projects, kept side by side (`../haunted-house` the remaster,
`../haunted-house-nes` the NES game): the remaster's spec and models are the rules, the NES game's mansion is
the house, and this repository reads both at build time. The plan: [docs/plan.md](docs/plan.md); why things
are as they are: [docs/decisions.md](docs/decisions.md).

## Commands

(To come with step 0 of the plan. The shape, as the NES game's: `tools/get_tools.py` fetches PVSnesLib, the
audio driver and the emulator core; `tools/build.py` makes `build/shareable/haunted_house.sfc` and, with
your 2600 ROM, `build/faithful/`; `tests/verify_engine.py` checks the engine frame by frame; `python
tools/readability.py` runs the code rules.)

## Rules

- **The engine is written from the spec** (`../haunted-house/docs/spec.md` and `game/player.py`), never from
  the original's code, and not from the NES game's assembly.
- **Prove it.** After any change to `src/`, run `tests/verify_engine.py` on both builds.
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
- Comments say why. Each file starts with a comment saying what it is.
- Python tools follow the sister repositories' rules (`tools/readability.py`, ruff, pyright, types on every
  signature).
