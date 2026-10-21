"""The music: the remaster's soundtrack (a pack's music.json, in its music/chiptune.py notation) written as
the Terrific Audio Driver's MML, arranged as the remaster's orchestra arranges it (its music/orchestra.py)
and played on the instruments tools/make_sound.py makes.

A song is a tempo, a style, a chord a bar, a melody in eighth notes and a drum pattern in sixteenths. Each
becomes channels: A the melody, B C D the style's accompaniment, E the bass, F the drums (G and H are left
for the sound effects). The sound chip's echo is the orchestra's hall.

    organ     the organ holds the chord over a pedal note; the melody on the organ
    drive     a harpsichord arpeggiates, strings hold the chord, a harp walks the bass; violin melody
    fanfare   the same with brass arpeggios and a brass melody
    march     harpsichord chords on the off-beats over a walking bass; violin melody (a minuet)
    creep     a harp's broken chord over low strings; the melody on a bell
    tremolo   strings tremble on the root and the semitone above; violin melody

Used by tools/make_sound.py (songs_for).
"""

import json
import os
import sys
from collections.abc import Callable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
NES = os.path.join(os.path.dirname(ROOT), "haunted-house-nes")
sys.path.insert(0, REMASTER)
from music.chiptune import CHORDS, NOTE  # noqa: E402

Song = dict[str, object]
TICKS_PER_SIXTEENTH = 12          # with #ZenLen 192 a quarter note is 48 ticks: #Tempo is then the bpm
SIXTEENTHS_PER_BAR = 16
CLASSIC_MUSIC = os.path.join(REMASTER, "packs", "nocturne", "music.json")   # the SNES look's soundtrack
MANSION_MUSIC = os.path.join(NES, "mansion", "music.json")                  # the shareable mansion's own
FAITHFUL_FLOOR_SONGS = ["floor1", "floor2", "floor3", None]                # the attic is the quiet floor
MELODY = {"organ": "organ", "drive": "violin", "fanfare": "brass", "march": "violin", "creep": "bell",
          "tremolo": "violin"}
# Each part's instrument (tools/make_sound.py's samples, with an envelope for the part) and loudness.
INSTRUMENTS = """@organ organ
@violin strings adsr 11 1 6 0
@brass brass
@bell bell
@harp harp
@harpsichord harpsichord
@strings strings
@tremble strings adsr 15 4 4 0
@timpani timpani
@noise organ adsr 15 6 0 0
@hat organ adsr 15 7 0 0
"""
MELODY_VOLUME, PART_VOLUME, BASS_VOLUME, DRUM_VOLUME = 110, 55, 80, 80   # (the effects sit a little above)
HEADER = """#ZenLen 192
#EchoLength 48
#EchoFeedback 60
#EchoVolume 28
"""


# --- notes --------------------------------------------------------------------------------------------
def midi_of(name: str) -> int:
    """'F#4' / 'Bb5' -> a MIDI note (A4 = 69), as the remaster's note_hz reads them."""
    semitone = NOTE[name[0]]
    rest = name[1:]
    while rest and rest[0] in "#b":
        semitone += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + semitone


NAMES = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]


def note(midi: int, sixteenths: float) -> str:
    """A note in the driver's MML, its octave given each time (o4 c is middle C, 60), and its length."""
    return f"o{midi // 12 - 1} {NAMES[midi % 12]}%{round(sixteenths * TICKS_PER_SIXTEENTH)}"


def rest(sixteenths: float) -> str:
    return f"r%{round(sixteenths * TICKS_PER_SIXTEENTH)}"


def chord(symbol: str) -> tuple[int, list[int]]:
    """'Am' -> (its root, MIDI, in octave 3; its notes), as the remaster's chord_notes."""
    accidental = symbol[1] if len(symbol) > 1 and symbol[1] in "#b" else ""
    quality = symbol[1 + len(accidental):]
    root = 48 + NOTE[symbol[0]] + {"#": 1, "b": -1, "": 0}[accidental]
    return root, [root + interval for interval in CHORDS[quality]]


# --- the melody ---------------------------------------------------------------------------------------
def melody(tokens: list[str]) -> str:
    """Eighth-note tokens - a note, '-' to hold it, '.' a rest - as notes and rests."""
    out = []
    index = 0
    while index < len(tokens):
        after = index + 1
        while after < len(tokens) and tokens[after] == "-":
            after += 1
        eighths = after - index
        if tokens[index] in ("-", "."):
            out.append(rest(eighths * 2))
        else:
            out.append(note(midi_of(tokens[index]), eighths * 2))
        index = after
    return " ".join(out)


# --- the accompaniment, a bar at a time ----------------------------------------------------------------
# Each arrangement gives, for one bar, the three accompaniment parts and the bass.
Bar = tuple[list[str], list[str], list[str], list[str]]


def held(midi: int) -> list[str]:
    return [note(midi, SIXTEENTHS_PER_BAR)]


def held_organ(root: int, tones: list[int], _style: str) -> Bar:
    padded = (tones + tones)[:3]
    return held(padded[0] + 12), held(padded[1] + 12), held(padded[2] + 12), held(root - 12)


def driving(root: int, tones: list[int], _style: str) -> Bar:
    sequence = tones + [tones[0] + 12, tones[1] + 12]
    arpeggio = [note(sequence[step % len(sequence)] + 12, 1) for step in range(SIXTEENTHS_PER_BAR)]
    bass = [note(root - 12, 4) for _beat in range(4)]
    return arpeggio, held(tones[0] + 12), held(tones[-1] + 12), bass


def minuet(root: int, tones: list[int], _style: str) -> Bar:
    parts: list[list[str]] = [[], [], []]
    padded = (tones + tones)[:3]
    for part, midi in zip(parts, padded):
        for _beat in range(4):
            part += [rest(2), note(midi + 12, 2)]
    bass = [note(root - 12, 4), note(root - 5, 4), note(root - 12, 4), note(root - 5, 4)]
    return parts[0], parts[1], parts[2], bass


def trembling(root: int, tones: list[int], _style: str) -> Bar:
    shiver = [note(tones[0] + 12 + step % 2, 1) for step in range(SIXTEENTHS_PER_BAR)]
    return shiver, [rest(SIXTEENTHS_PER_BAR)], [rest(SIXTEENTHS_PER_BAR)], held(root - 12)


def creep(root: int, tones: list[int], _style: str) -> Bar:
    """A harp's broken chord, an eighth a note, on two channels in turn so each rings on."""
    first: list[str] = []
    second: list[str] = []
    for step in range(8):
        midi = tones[step % len(tones)] + 12
        if step % 2 == 0:
            first += [note(midi, 2)]
            second += [rest(2)]
        else:
            first += [rest(2)]
            second += [note(midi, 2)]
    return first, second, [rest(SIXTEENTHS_PER_BAR)], held(root - 12)


ARRANGEMENTS: dict[str, Callable[[int, list[int], str], Bar]] = {
    "organ": held_organ, "drive": driving, "fanfare": driving, "march": minuet, "tremolo": trembling,
    "creep": creep}
PART_INSTRUMENTS = {"organ": ("organ", "organ", "organ", "organ"),
                    "drive": ("harpsichord", "strings", "strings", "harp"),
                    "fanfare": ("brass", "strings", "strings", "harp"),
                    "march": ("harpsichord", "harpsichord", "harpsichord", "harp"),
                    "tremolo": ("tremble", "strings", "strings", "strings"),
                    "creep": ("harp", "harp", "strings", "strings")}


# --- the drums ------------------------------------------------------------------------------------------
# The orchestra's drums (music/orchestra.py): the timpani at full, the snare at half and short, the hat a
# faint tick - noise from the sound chip, at its loudness and with its quick decay.
DRUM_HITS = {"k": "@timpani V80 o1 b%{t}", "s": "@noise V40 N20,%{t}", "h": "@hat V14 N28,%{t}"}


def drum_bar(pattern: str) -> str:
    """A bar of the pattern: k timpani, s snare, h hat, '.' nothing, a sixteenth each."""
    out = []
    for kind in pattern.ljust(SIXTEENTHS_PER_BAR, "."):
        hit = DRUM_HITS.get(kind)
        out.append(hit.format(t=TICKS_PER_SIXTEENTH) if hit else rest(1))
    return " ".join(out)


# --- a song ---------------------------------------------------------------------------------------------
def channel(letter: str, instrument: str, volume: int, body: str, loop: bool) -> str:
    start = "L " if loop else ""
    return f"{letter} @{instrument} V{volume} E {start}{body}"


def song_mml(name: str, song: Song) -> str:
    """One song as MML: header, instruments, and its six channels."""
    style = str(song.get("style", "march"))
    if style not in ARRANGEMENTS:          # (as the orchestra: a style it doesn't know creeps, violin on top)
        style = "creep"
        melody_instrument = "violin"
    else:
        melody_instrument = MELODY[style]
    loop = bool(song.get("loop", True))
    bars = [chord(symbol) for symbol in str(song["chords"]).split()]
    arranged = [ARRANGEMENTS[style](root, tones, style) for root, tones in bars]
    tokens = [token for bar in str(song["melody"]).split("|") for token in bar.split()]
    lines = [f"#Title {name}", f"#Tempo {song['bpm']}", HEADER, INSTRUMENTS,
             channel("A", melody_instrument, MELODY_VOLUME, melody(tokens), loop)]
    instruments = PART_INSTRUMENTS[style]
    for index, letter in enumerate("BCD"):
        body = " ".join(" ".join(bar[index]) for bar in arranged)
        lines.append(channel(letter, instruments[index], PART_VOLUME, body, loop))
    bass = " ".join(" ".join(bar[3]) for bar in arranged)
    lines.append(channel("E", instruments[3], BASS_VOLUME, bass, loop))
    if song.get("drums"):
        lines.append(channel("F", "noise", DRUM_VOLUME, f"[{drum_bar(str(song['drums']))}]{len(bars)}", loop))
    return "\n".join(lines) + "\n"


def all_songs() -> dict[str, Song]:
    """The SNES look's soundtrack and the shareable mansion's own songs (the faithful build plays the
    first's floor songs)."""
    with open(CLASSIC_MUSIC) as classic:
        songs: dict[str, Song] = dict(json.load(classic)["songs"])
    with open(MANSION_MUSIC) as mansion:
        songs.update(json.load(mansion)["songs"])
    return songs


def floor_songs(shareable: bool) -> list[str | None]:
    """Each floor's song, by floor (None: the quiet floor)."""
    if not shareable:
        return list(FAITHFUL_FLOOR_SONGS)
    with open(MANSION_MUSIC) as mansion:
        return list(json.load(mansion)["floor_songs"])


def write_songs(sound_folder: str) -> list[dict[str, str]]:
    """Every song's MML into sound_folder/songs; their entries for the project file."""
    folder = os.path.join(sound_folder, "songs")
    os.makedirs(folder, exist_ok=True)
    entries = []
    for name, song in all_songs().items():
        with open(os.path.join(folder, f"{name}.mml"), "w") as out:
            out.write(song_mml(name, song))
        entries.append({"name": name, "source": os.path.join("songs", f"{name}.mml")})
    return entries
