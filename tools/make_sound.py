"""The sound's data for the Terrific Audio Driver (docs/plan.md, step 3): the remaster's orchestra
(its music/orchestra.py - organ, strings, brass, harp, bell, harpsichord, timpani - and the house's wood and
creaks, music/house.py) made into SNES samples, and its twenty sound effects (music/orchestral_effects.py)
written as the driver's MML, played on those samples and the sound chip's own noise.

The SNES has 64K of sound memory for the driver, the samples, the effects and a song, so nothing is kept as
a whole recording: an effect is a few notes on an instrument, as the remaster builds them. A steady
instrument (an organ, strings) is one looped waveform; a plucked or struck one is a short one-shot at a low
sample rate; and a chord an effect needs (the ghost's organ, the urn's swell) is one looped waveform with
all its notes in, since an effect plays on a single channel.

Makes, in build/<kind>/sound/:
  samples/NAME.wav            each instrument
  sound-effects.txt           the effects, in MML
  haunted.terrificaudio       the driver's project file
  audio-data.bin              the driver, its loader and all the sound data (tad-compiler pv-export)
and src/audio_data.asm (binds it into the ROM, with the driver's loadAudioData()), build/<kind>/audio.h
(the effects' numbers for the C) and src/audio_ids.inc (the same for the assembly).

Usage: python tools/make_sound.py [--faithful]      (tools/build.py runs it)
"""

import json
import os
import re
import subprocess
import sys
import wave
from collections.abc import Callable, Sequence
from typing import NamedTuple

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMASTER = os.path.join(os.path.dirname(ROOT), "haunted-house")
TAD = os.path.join(ROOT, "tools", "tad")
TAD_COMPILER = os.path.join(TAD, "target", "release", "tad-compiler")
sys.path.insert(0, REMASTER)
import make_songs  # noqa: E402
from music import house  # noqa: E402
from music import orchestra as O  # noqa: E402
from music.chiptune import RATE, midi_hz  # noqa: E402

Floats = np.ndarray
SNES_RATE = 32000          # the sound chip's own rate: a sample's tuning is its pitch played back at this
BLOCK = 16                 # BRR blocks are 16 samples: lengths and loop points are multiples
PEAK = 0.8                 # samples are made this loud (headroom for the sound chip's interpolation)
LOOP_LENGTH = 64           # a steady instrument's loop: one cycle of 64 samples, 500 Hz at 32 kHz
LOOP_TUNING = SNES_RATE / LOOP_LENGTH
FIRST_AUDIO_BANK = 8       # the sound data's first ROM bank (the code and pictures fill 0-7)


class Instrument(NamedTuple):
    name: str
    wave: Floats             # -1..1, at `rate`
    rate: int                # the sample rate it's made at
    root: float              # the pitch (Hz) in the sample at that rate
    looping: bool            # the whole sample loops (a steady tone); else it plays once
    envelope: str            # the driver's ADSR or GAIN setting


# --- making the samples -----------------------------------------------------------------------------------
def resampled(sound: Floats, rate: int) -> Floats:
    """A sound made at the remaster's rate, at another."""
    count = int(len(sound) * rate / RATE)
    return np.interp(np.arange(count) * RATE / rate, np.arange(len(sound)), sound)


def one_shot(name: str, sound: Floats, rate: int, root: float, envelope: str = "gain F127") -> Instrument:
    """A sound that plays once, cut to whole BRR blocks and faded at the end."""
    made = resampled(sound, rate)
    made = made[:len(made) // BLOCK * BLOCK]
    fade = min(len(made), BLOCK * 4)
    made[-fade:] *= np.linspace(1, 0, fade)
    return Instrument(name, made, rate, root, False, envelope)


def cycle(weights: Sequence[tuple[float, float]], length: int = LOOP_LENGTH) -> Floats:
    """One loop of a steady tone: partials (number of cycles in the loop, loudness) added up."""
    phase = 2 * np.pi * np.arange(length) / length
    tone: Floats = np.zeros(length)
    for cycles, loudness in weights:
        tone = tone + loudness * np.sin(phase * cycles)
    return tone


def looped(name: str, tone: Floats, root: float, envelope: str) -> Instrument:
    return Instrument(name, tone, SNES_RATE, root, True, envelope)


def fm_cycle(index: float, ratio: float, length: int = LOOP_LENGTH) -> Floats:
    """One loop of the orchestra's two-operator FM (music/orchestra.py fm) with its index held."""
    phase = 2 * np.pi * np.arange(length) / length
    return np.sin(phase + index * np.sin(phase * ratio))


def chord_cycle(parts: list[int], length: int, stops: list[tuple[int, float]]) -> Floats:
    """A chord as one loop: each note a whole number of cycles in the loop, each with the given
    harmonics. `parts` are the notes' cycle counts; the lowest is the root."""
    weights = [(part * number, loudness) for part in parts for number, loudness in stops]
    return cycle(weights, length)


ORGAN_STOPS = [(number, loudness) for number, loudness in O.ORGAN_STOPS]
STRING_STOPS = [(number, 1 / number) for number in range(1, O.STRING_HARMONICS + 1)]
CHORD_LOOP = 512           # samples: a chord's loop, so its notes' cycles are whole numbers
CLASH_LOOP = 2048


def steady_instruments() -> list[Instrument]:
    """The looped ones: the organ, strings, brass, and the chords the effects play."""
    chord_root = SNES_RATE / CHORD_LOOP
    clash_root = SNES_RATE / CLASH_LOOP
    return [
        looped("organ", cycle(ORGAN_STOPS), LOOP_TUNING, "adsr 11 0 7 0"),
        looped("strings", cycle(STRING_STOPS), LOOP_TUNING, "adsr 8 0 6 0"),
        looped("brass", 0.7 * fm_cycle(2.6, 1) + 0.3 * fm_cycle(0.8, 2), LOOP_TUNING, "adsr 10 1 6 0"),
        # a minor triad (10:12:15) on the organ: the ghost's chord
        looped("organ_minor", chord_cycle([10, 12, 15], CHORD_LOOP, ORGAN_STOPS[:3]), chord_root * 10,
               "adsr 9 0 7 0"),
        # a major chord, open (4:8:10:12) on strings: the whole urn's swell
        looped("strings_major", chord_cycle([4, 8, 10, 12], CHORD_LOOP, STRING_STOPS[:4]), chord_root * 4,
               "adsr 9 0 7 0"),
        # D, D#, G#, A together on strings: being caught
        looped("strings_clash", chord_cycle([19, 20, 27, 28], CLASH_LOOP, STRING_STOPS[:4]), clash_root * 19,
               "adsr 14 2 5 0"),
    ]


def seconds(count: float) -> int:
    return int(count * RATE)


RUMBLE_RATE = 4000         # the thunder's rumble: low, so a low sample rate holds it...
RUMBLE_LENGTH = 2048       # ...and a loop of this many samples (half a second)
RUMBLE_LOW, RUMBLE_HIGH, RUMBLE_TILT = 30, 700, 0.7   # Hz kept, louder low down (music/house.py thunder)


def rumble() -> Instrument:
    """The thunder's rumble (the remaster's house.thunder): noise kept to its low frequencies. Filtered
    round the loop, it loops without a seam."""
    noise = np.random.default_rng(31).normal(size=RUMBLE_LENGTH)
    frequencies = np.fft.rfftfreq(RUMBLE_LENGTH, 1 / RUMBLE_RATE)
    keep = (frequencies >= RUMBLE_LOW) & (frequencies <= RUMBLE_HIGH)
    shape = keep / np.maximum(frequencies, RUMBLE_LOW) ** RUMBLE_TILT
    low = np.fft.irfft(np.fft.rfft(noise) * shape, RUMBLE_LENGTH)
    return Instrument("rumble", low, RUMBLE_RATE, midi_hz(60), True, "adsr 12 1 4 9")


def struck_instruments() -> list[Instrument]:
    """The ones that play once: plucked, struck, knocked, creaking."""
    harp_root, bell_root, harpsichord_root = midi_hz(69), midi_hz(84), midi_hz(72)
    return [
        one_shot("harp", O.harp(harp_root, seconds(0.45)), 12000, harp_root),
        one_shot("bell", O.bell(bell_root, seconds(0.4)), 16000, bell_root),
        one_shot("harpsichord", O.harpsichord(harpsichord_root, seconds(0.22)), 16000, harpsichord_root),
        one_shot("timpani", O.timpani(seconds(0.7)), 8000, 58.0),
        one_shot("wood", house.wood(40, 120, 0.025), 16000, 120.0),
        one_shot("creak", house.creak(4, 0.55, 140), 8000, midi_hz(60)),
        rumble(),
    ]


def instruments() -> list[Instrument]:
    return steady_instruments() + struck_instruments()


def write_wave(path: str, instrument: Instrument) -> None:
    pcm = instrument.wave / max(1e-9, np.abs(instrument.wave).max()) * PEAK * 32767
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(instrument.rate)
        out.writeframes(pcm.astype("<i2").tobytes())


def tuning(instrument: Instrument) -> float:
    """The pitch the sample has when the sound chip plays it at 32 kHz (the driver's 'frequency')."""
    return instrument.root * SNES_RATE / instrument.rate


NOTE_NAMES = ["c", "c+", "d", "d+", "e", "f", "f+", "g", "g+", "a", "a+", "b"]
LOWEST_NOTE = 24           # c1
HIGHEST_NOTE = 107         # b7: the driver's highest
FASTEST = 3.99             # the sound chip plays a sample at most this many times faster than at 32 kHz


def note_name(midi: int) -> str:
    """The driver's name for a MIDI note: c4 is middle C, 60."""
    return f"{NOTE_NAMES[midi % 12]}{midi // 12 - 1}"


def highest_note(instrument: Instrument) -> int:
    """The highest MIDI note the sound chip can play this sample at."""
    reach = tuning(instrument) * FASTEST
    return min(HIGHEST_NOTE, int(np.floor(69 + 12 * np.log2(reach / 440))))


def sample_entry(instrument: Instrument, folder: str) -> dict[str, object]:
    source: dict[str, object] = {"type": "wav", "source": os.path.join(folder, f"{instrument.name}.wav"),
                                 "evaluator": "default"}
    if instrument.looping:
        source["loop_point"] = 0
        source["loop_filter"] = "reset_filter"
    return {"name": instrument.name, "source": source, "ignore_gaussian_overflow": False,
            "pitches": {"type": "notes", "frequency": round(tuning(instrument), 3),
                        "first_note": note_name(LOWEST_NOTE),
                        "last_note": note_name(highest_note(instrument))},
            "envelope": instrument.envelope}


# --- the effects -----------------------------------------------------------------------------------------
# Each effect is the remaster's (music/orchestral_effects.py), on one channel: its notes as MIDI numbers
# (n60 is middle C; effects_text spells them) with lengths in ticks (%n: effects play at 125 ticks a second);
# N<0-31> is the sound chip's noise at a pitch (31 the highest), sounding while its instrument is held.
EFFECTS: dict[str, str] = {
    # the head scraping the box, then the flame catching
    "match_strike": "@o organ adsr 15 6 0 0\nA @o v12 N28,%10 v10 A15,3,2,10 N18,%50",
    # blown out: a breath
    "match_out": "@o organ adsr 13 5 0 0\nA @o v10 N17,%40",
    # old hinges: a slow creak
    "door_open": "@c creak\nA @c v12 n60,%70",
    # the door swinging to: a wooden knock
    "door_close": "@w wood\nA @w v14 n46,%25",
    # the handle rattles; a low string says no
    "locked": "@o organ adsr 15 7 0 0\n@s strings adsr 13 2 5 0\n"
              "A @o v11 N25,%4 r%5 N25,%4 r%5 N25,%4 r%6 @s v12 n38,%18 n37,%30",
    # walking into a wall
    "bump": "@w wood\nA @w v13 n40,%20",
    # steps, climbing - or going down - the scale, on the harp
    "stairs_up": "@h harp\nA @h v13 l%14 n57 n60 n62 n64 n67 n69 ^%50",
    "stairs_down": "@h harp\nA @h v13 l%14 n69 n67 n64 n62 n60 n57 ^%50",
    # bells: a small, bright jingle
    "pickup_key": "@b bell\nA @b v11 l%8 n84 n88 n84 n88 ^%55",
    # a harp sweeping up a major chord, a bell on top
    "pickup_scepter": "@h harp\n@b bell\nA @h v13 l%5 n60 n64 n67 n72 n76 n79 @b v11 n84,%120",
    # a low harp chord, broken
    "pickup_urn": "@h harp\nA @h v14 l%9 n48 n55 n60 n64 ^%100",
    # setting something down: a low harp note
    "drop": "@h harp\nA @h v14 n43,%50",
    # two pieces join: a harp glissando, up
    "urn_join": "@h harp\nA @h v12 l%4 n67 n69 n71 n74 n76 n79 n81 n83 n86 n88 n91 ^%90",
    # the urn is whole: the glissando, then strings ringing out
    "urn_whole": "@h harp\n@s strings_major\n"
                 "A @h v12 l%4 n67 n69 n71 n74 n76 n79 n81 n83 n86 n88 n91 n95 @s v12 n55,%200",
    # caught: clashing strings, sliding away
    "caught": "@x strings_clash\nA @x v14 n62,%30 {d <d}%100",
    # a crack, a timpani roll and the storm's low rumble, dying away
    "thunder": "@o organ adsr 15 7 0 0\n@t timpani\n@r rumble\n"
               "A @o v7 N18,%8 @t v13 n35,%7 v11 n35,%7 v9 n35,%7 @r v15 n60,%220",
    # oooo: an organ chord that swells and sinks a semitone
    "monster_ghost": "@g organ_minor\nA @g V60 Vs+150,50 n57,%69 n56,%69",
    # wings: a flurry on the harpsichord, high
    "monster_bat": "@k harpsichord\nA @k v12 l%6 n84 n81 n84 n81 n84 n81 ^%10",
    # legs: low strings plucked, scurrying
    "monster_tarantula": "@p strings adsr 15 5 0 0\nA @p v14 l%5 n40 n41 n40 n43 n41 n40 n41 n43 n44",
    # one step on old boards, quiet
    "footstep": "@w wood\nA @w v6 n47,%15",
}
FIRST_EFFECTS = ["caught", "thunder"]          # high priority: never dropped for another
LAST_EFFECTS = ["footstep"]                    # low priority: dropped for any other


MIDI_NOTE = re.compile(r"n(\d+)(,(%\d+))?")


def spelled(match: re.Match[str]) -> str:
    """One MIDI note in the driver's MML: its octave and name, and its length if given."""
    midi = int(match.group(1))
    return f"o{midi // 12 - 1} {NOTE_NAMES[midi % 12]}{match.group(3) or ''}"


def effects_text() -> str:
    """The effects, their MIDI notes (n60, n60,%14) spelled as the driver's notes (o4 c, o4 c%14)."""
    sections = [f"=== {name} === mml\n{MIDI_NOTE.sub(spelled, text)}\n" for name, text in EFFECTS.items()]
    return "; The sound effects: tools/make_sound.py (from the remaster's music/orchestral_effects.py).\n\n" \
        + "\n".join(sections)


# --- the project and the export ----------------------------------------------------------------------------
def project(sound_folder: str, made: list[Instrument]) -> dict[str, object]:
    songs = make_songs.write_songs(sound_folder)
    middle = effect_order()[len(FIRST_EFFECTS):len(EFFECTS) - len(LAST_EFFECTS)]
    return {"_about": {"file_type": "Terrific Audio Driver project file", "version": "0.4.2"},
            "brr_samples": [sample_entry(instrument, "samples") for instrument in made],
            "default_sfx_flags": {"one_channel": True, "interruptible": True},
            "high_priority_sound_effects": FIRST_EFFECTS, "sound_effects": middle,
            "low_priority_sound_effects": LAST_EFFECTS, "sound_effect_file": "sound-effects.txt",
            "songs": songs}


def effect_order() -> list[str]:
    """The effects in the driver's numbering: high priority first, low last (its export order)."""
    middle = [name for name in EFFECTS if name not in FIRST_EFFECTS + LAST_EFFECTS]
    return FIRST_EFFECTS + middle + LAST_EFFECTS


def effect_numbers_text() -> str:
    """src/audio_ids.inc: the effects' numbers for the assembly (src/fast.asm, audio_events), as the
    driver's own header gives them to the C."""
    lines = ["; The sound effects' numbers: tools/make_sound.py. Don't edit."]
    lines += [f".define SFX_{name} {number}" for number, name in enumerate(effect_order())]
    return "\n".join(lines) + "\n"


def export(project_path: str, sound_folder: str) -> str:
    """Run the driver's compiler; returns its assembly, with the data's path made whole."""
    asm_path = os.path.join(sound_folder, "audio-data.asm")
    bin_path = os.path.join(sound_folder, "audio-data.bin")
    subprocess.run([TAD_COMPILER, "pv-export", "--lorom", "--bank", str(FIRST_AUDIO_BANK),
                    "--output-asm", asm_path, "--output-bin", bin_path, project_path], check=True)
    with open(asm_path) as made:
        text = made.read()
    return text.replace('.incbin "audio-data.bin"', f'.incbin "{bin_path}"')


Maker = Callable[[], list[Instrument]]


TICKS = re.compile(r"%(\d+)")
EFFECT_TICKS_A_SECOND = 125      # the driver plays effects at this fixed rate
FRAMES_A_SECOND = 60


def effect_frames(name: str) -> int:
    """About how many frames an effect sounds: its notes', rests' and noises' lengths added up."""
    ticks = sum(int(found) for found in TICKS.findall(EFFECTS[name]))
    return min(255, round(ticks * FRAMES_A_SECOND / EFFECT_TICKS_A_SECOND))


def songs_header_text(shareable: bool) -> str:
    """songs.h: each floor's song, by floor, in the driver's numbering (audio.h, SONG_name); and each
    effect's length in frames, in its numbering (a new song waits for the effect: loading one stops all)."""
    songs = [f"SONG_{name}" if name else "SONG_BLANK" for name in make_songs.floor_songs(shareable)]
    lengths = [str(effect_frames(name)) for name in effect_order()]
    return ("/* Each floor's song and each effect's length: tools/make_sound.py. Don't edit. */\n"
            "#ifndef SONGS_H\n#define SONGS_H\n/* (include audio.h first: its guard doesn't hold) */\n\n"
            f"#define SONG_FLOORS {len(songs)}\n"
            f"static const u8 floor_songs[SONG_FLOORS] = {{{', '.join(songs)}}};\n"
            f"static const u8 effect_frames[{len(lengths)}] = {{{', '.join(lengths)}}};\n\n#endif\n")


def write(kind_folder: str, shareable: bool = True, make: Maker = instruments) -> None:
    sound_folder = os.path.join(kind_folder, "sound")
    sample_folder = os.path.join(sound_folder, "samples")
    os.makedirs(sample_folder, exist_ok=True)
    made = make()
    for instrument in made:
        write_wave(os.path.join(sample_folder, f"{instrument.name}.wav"), instrument)
    with open(os.path.join(sound_folder, "sound-effects.txt"), "w") as out:
        out.write(effects_text())
    project_path = os.path.join(sound_folder, "haunted.terrificaudio")
    with open(project_path, "w") as out:
        json.dump(project(sound_folder, made), out, indent=2)
    asm = export(project_path, sound_folder)
    with open(os.path.join(ROOT, "src", "audio_data.asm"), "w") as out:
        out.write('; The sound data, bound into the ROM: tools/make_sound.py. Don\'t edit.\n'
                  '.include "hdr.asm"\n.define LOROM 1\n\n' + asm)
    subprocess.run([TAD_COMPILER, "pv-enums", "-o", os.path.join(kind_folder, "audio.h"), project_path],
                   check=True)
    with open(os.path.join(ROOT, "src", "audio_ids.inc"), "w") as out:
        out.write(effect_numbers_text())
    with open(os.path.join(kind_folder, "songs.h"), "w") as out:
        out.write(songs_header_text(shareable))
    song_count = len(make_songs.all_songs())
    print(f"  the sound: {len(made)} instruments, {len(EFFECTS)} effects, {song_count} songs, "
          f"{os.path.getsize(os.path.join(sound_folder, 'audio-data.bin'))} bytes")


def main() -> None:
    shareable = "--faithful" not in sys.argv
    write(os.path.join(ROOT, "build", "shareable" if shareable else "faithful"), shareable)


if __name__ == "__main__":
    main()
