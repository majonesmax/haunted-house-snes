# The faithful build: the original's mansion, from your own ROM

*Haunted House: By Matchlight* comes in two builds of one engine. The **shareable** one, which you can
download, has the NES game's mansion. The **faithful** one has the original's: the 2600 game's own four
floors, their walls, doors, locks and stairs, and its rules' numbers, read from your copy of the game when you
build it. Everything you see and hear is still the remaster's (its SNES look, its *nocturne* pack, its
orchestra); only the house and its numbers are the original's.

It's the build that proves the engine plays exactly like the original, and it's for you alone: nothing from
the 2600 game is in this repository, and the ROM it makes must never be shared.

## What you need

- **Your own copy of Haunted House for the Atari 2600**, the NTSC cartridge (Atari CX2654), as a 4K ROM file:
  MD5 `f0a6e99f5875891246c3dbecbf2d2cea`. That's the one everything was worked out and checked on; the build
  checks the fingerprint and stops with another (its tables are read from fixed places in it).
- **Python 3.12 or newer**, and **Rust** (https://rustup.rs) for the audio driver's compiler.
- **The remaster and the NES game**, beside this repository: the remaster's model of the game and its SNES
  look, and the NES game's tools that read the original's mansion, are what the build is made from.

## Step by step

```sh
# 1. The three repositories, side by side
git clone https://github.com/majonesmax/haunted-house-snes
git clone https://github.com/majonesmax/haunted-house-remastered haunted-house
git clone https://github.com/majonesmax/haunted-house-nes
cd haunted-house-snes

# 2. Python and its packages; the SNES tools and the audio driver's compiler
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python tools/get_tools.py
cargo build --release -p tad-compiler --manifest-path tools/tad/Cargo.toml

# 3. Your ROM, where the remaster keeps it
mkdir -p ../haunted-house/roms
cp /path/to/your/haunted_house.a26 ../haunted-house/roms/haunted_house.a26

# 4. Build it: build/faithful/haunted_house.sfc
.venv/bin/python tools/build.py --faithful
```

Step 4 reads the original's mansion and tables from your ROM (with the NES game's `tools/extract.py`), draws
the four floors from them in the SNES look, arranges the soundtrack, and compiles the ROM.

## Playing it

Open `build/faithful/haunted_house.sfc` in any SNES emulator, or play it here with the keyboard:

```sh
.venv/bin/python tools/play.py --faithful
```

Keys in `tools/play.py`: arrows walk, Space lights a match or puts down what you hold, Enter starts a game, Tab
chooses it (1-9), Z gives a hint (the help, on the title), O is the lights-on cheat, Escape quits.

## Checking it plays like the original

```sh
.venv/bin/python tests/verify_engine.py          # (without --shareable: the faithful build)
```

It plays the ROM beside the remaster's model of the original, with the same controls, game after game, and
compares the game's state after every frame. It should say every frame was predicted exactly.
