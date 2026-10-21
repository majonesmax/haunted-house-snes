# Art and music license

The art and music in the shareable ROM are licensed under the
**Creative Commons Attribution 4.0 International License (CC BY 4.0)**:
https://creativecommons.org/licenses/by/4.0/

They come from the sister projects, where they're CC BY 4.0 too:

- the [Haunted House remaster](https://github.com/majonesmax/haunted-house-remastered)'s *nocturne* pack, its
  SNES look's title and ending scenes, its soundtrack and its orchestra's instruments (credit: "Haunted House
  remaster contributors");
- the [NES game](https://github.com/majonesmax/haunted-house-nes)'s mansion: its floor plans and its own songs
  (credit: "Haunted House: By Matchlight contributors").

The pictures in `docs/media/` are of the shareable ROM, and are CC BY 4.0 on the same terms.

Credit: "Haunted House: By Matchlight contributors".

The code is MIT-licensed (see `LICENSE`).

**In the ROM, under their own licenses:** [PVSnesLib](https://github.com/alekmaul/pvsneslib)'s library (zlib,
© Alekmaul) and the [Terrific Audio Driver](https://github.com/undisbeliever/terrific-audio-driver) (zlib,
© Marcus Rowe). They're downloaded at build time by `tools/get_tools.py` and aren't part of this repository.

**Not included and not covered:** Atari 2600 *Haunted House* itself (© 1982 Atari, by James Andreasen). The
faithful build reads the original's mansion and tables from your own copy at build time; nothing from it is
in this repository or in the shareable ROM. The snes9x emulator core, which the checks run the ROM in, is
downloaded by `tools/get_tools.py` and isn't part of this repository.
