"""Play the ROM on this computer, with the keyboard: one window with the SNES's picture, and the sound.
Builds the ROM first if it isn't built. With --map, a map of the game's state read from the engine sits
beside the picture - the floor's walls, the eyes, the items, the monsters, and the numbers under it - to
watch the engine against the picture.

Keys (the SNES pad):
  arrow keys or W A S D    the D-pad: walk
  Space or X               B: light a match; put down what you hold
  Enter                    Start: a new game (the 2600's RESET)
  Tab                      Select: the next game, 1-9
  Z or G                   X: a hint in play; the help on the title; past the story
  O                        B and Select together: the lights-on cheat
  Escape                   quit

Usage: python tools/play.py [--faithful] [--map]      (the shareable build without --faithful)
"""

import collections
import os
import sys
import threading
import time

import numpy as np
import pygame
import sounddevice

import snes as S
from build import build, rom_path, shareable_wanted, symbols
import make_mansion   # (after build: it puts the NES game's tools, which have a build.py too, on the path)

SOUND_AHEAD = 2400          # samples kept queued (75 ms): the emulator runs whenever there are fewer, so
                            # the sound sets the pace - pygame's clock counts whole milliseconds and ran
                            # the game at 52 frames a second, the sound in gaps
IDLE_SECONDS = 0.002        # the wait between looks at the queue
SCALE = 3                   # the picture, 256 x 224, scaled (as the NES game's window)
PICTURE = (256 * SCALE, 224 * SCALE)
CHEAT_FRAMES = 6            # how long O holds B and Select together
MAP_SCALE = 2               # --map: a floor is 160 x 256 units
MAP_LEFT = PICTURE[0] + 16
NUMBER_LINES, LINE_HEIGHT = 6, 18   # --map: the numbers under the picture
MAP_WINDOW = (MAP_LEFT + 160 * MAP_SCALE + 16, PICTURE[1] + 16 + NUMBER_LINES * LINE_HEIGHT)
AUDIO_BLOCK = 512           # samples the sound card asks for at a time
MOST_QUEUED = 8000          # samples kept waiting at most: past this the oldest go, so the sound keeps up
WORK_RAM_BANK = 0x7E0000
KEYS = {
    pygame.K_UP: S.BUTTON_UP, pygame.K_w: S.BUTTON_UP,
    pygame.K_DOWN: S.BUTTON_DOWN, pygame.K_s: S.BUTTON_DOWN,
    pygame.K_LEFT: S.BUTTON_LEFT, pygame.K_a: S.BUTTON_LEFT, pygame.K_RIGHT: S.BUTTON_RIGHT,
    pygame.K_d: S.BUTTON_RIGHT, pygame.K_SPACE: S.BUTTON_B, pygame.K_x: S.BUTTON_B,
    pygame.K_RETURN: S.BUTTON_START, pygame.K_TAB: S.BUTTON_SELECT,
    pygame.K_z: S.BUTTON_X, pygame.K_g: S.BUTTON_X,
}
# the state block's bytes the map reads, by their 2600 addresses (src/state.h)
FLOOR, ROOM, POS_X, POS_Y, LIVES, MATCHES = 0x8D, 0x9C, 0xAA, 0xB5, 0x96, 0x82
FLAGS, GAME_STATE, GAME_NUMBER = 0x8A, 0x99, 0xCC
CARRIED, MATCH_TIME, MONSTERS_HERE, URN_SHAPES = 0x9A, 0xDF, 0x83, 0x9D
ITEM_FLOOR, ITEM_X, ITEM_Y = 0xA0, 0xAB, 0xB6
MONSTER_FLOOR, MONSTER_X, MONSTER_Y = 0xA5, 0xB0, 0xBB
MATCH_LIT = 0x40
ITEM_NAMES = ("key", "scepter", "urn 1", "urn 2", "urn 3")
MONSTER_LETTERS = "GBTTT"
WALL_COLOUR, FLOOR_COLOUR, EYES_COLOUR = (70, 60, 110), (18, 14, 28), (255, 240, 160)
ITEM_COLOUR, MONSTER_COLOUR, TEXT_COLOUR = (120, 220, 140), (230, 90, 90), (200, 200, 220)
MODES = {0x00: "playing", 0x01: "dying", 0x02: "reset", 0x40: "select / game over", 0x44: "won"}


class Speaker:
    """The game's sound, played as it's made: each frame's samples join a queue the sound card reads."""

    def __init__(self, rate: float):
        self.queue: collections.deque[np.ndarray] = collections.deque()
        self.waiting = 0
        self.lock = threading.Lock()     # (the sound card's thread takes from the queue as the game adds)
        self.stream = sounddevice.OutputStream(samplerate=rate, channels=2, dtype="int16",
                                               blocksize=AUDIO_BLOCK, callback=self.fill)
        self.stream.start()

    def add(self, samples: np.ndarray) -> None:
        with self.lock:
            self.queue.append(samples)
            self.waiting += len(samples)
            while self.waiting > MOST_QUEUED and len(self.queue) > 1:
                self.waiting -= len(self.queue.popleft())

    def queued(self) -> int:
        with self.lock:
            return self.waiting

    def fill(self, out: np.ndarray, frames: int, _time: object, _status: object) -> None:
        with self.lock:
            self.take(out, frames)

    def take(self, out: np.ndarray, frames: int) -> None:
        filled = 0
        while filled < frames and self.queue:
            chunk = self.queue[0]
            taken = min(frames - filled, len(chunk))
            out[filled:filled + taken] = chunk[:taken]
            filled += taken
            self.waiting -= taken
            if taken == len(chunk):
                self.queue.popleft()
            else:
                self.queue[0] = chunk[taken:]
        out[filled:] = 0


class StateMap:
    """The game as the engine has it, drawn as a map: the floor's plan with the eyes, items and monsters
    on it, and the numbers beside."""

    def __init__(self, machine: S.Snes, shareable: bool):
        self.ram = machine.ram
        self.state_at = symbols(shareable)["game_ram"] - WORK_RAM_BANK
        _constants, tables, _eyes, _bits = (make_mansion.shareable() if shareable
                                            else make_mansion.faithful(make_mansion.E.checked_rom(
                                                make_mansion.E.DEFAULT_ROM)))
        self.walls = tables["mansion_walls"]        # 16 rows a floor, a bit per column
        self.font = pygame.font.SysFont("menlo", 14)

    def byte(self, address: int) -> int:
        return int(self.ram[self.state_at + address - 0x80])

    def at(self, x: int, y: int) -> tuple[int, int]:
        """A floor place (x across, y up) on the map (y down)."""
        return MAP_LEFT + x * MAP_SCALE, 4 + (255 - y) * MAP_SCALE

    def draw(self, window: pygame.Surface) -> None:
        floor = self.byte(FLOOR)
        if floor * 16 + 16 > len(self.walls):   # the ROM is still booting: the state isn't set up yet
            return
        pygame.draw.rect(window, FLOOR_COLOUR, (MAP_LEFT, 4, 160 * MAP_SCALE, 256 * MAP_SCALE))
        for row in range(16):
            plan = self.walls[floor * 16 + row]
            for column in range(-1, 9):            # the plan's 8 columns, and the solid outside them
                outside = column < 0 or column > 7
                wall = (row != 8) if outside else bool(plan & (1 << column))
                if wall:
                    left, top = self.at(16 * (column + 1), 16 * row + 15)
                    pygame.draw.rect(window, WALL_COLOUR, (left, top, 16 * MAP_SCALE, 16 * MAP_SCALE))
        self.draw_cast(window, floor)
        self.draw_numbers(window)

    def draw_cast(self, window: pygame.Surface, floor: int) -> None:
        for item in range(5):
            if self.byte(ITEM_FLOOR + item) == floor and self.byte(CARRIED) != item:
                left, top = self.at(self.byte(ITEM_X + item), self.byte(ITEM_Y + item) + 7)
                pygame.draw.rect(window, ITEM_COLOUR, (left, top, 8 * MAP_SCALE, 8 * MAP_SCALE), 1)
                window.blit(self.font.render(str(item), True, ITEM_COLOUR), (left + 2, top))
        for monster in range(5):
            if self.byte(MONSTER_FLOOR + monster) == floor:
                left, top = self.at(self.byte(MONSTER_X + monster), self.byte(MONSTER_Y + monster) + 9)
                pygame.draw.rect(window, MONSTER_COLOUR, (left, top, 8 * MAP_SCALE, 10 * MAP_SCALE), 1)
                window.blit(self.font.render(MONSTER_LETTERS[monster], True, MONSTER_COLOUR), (left + 2, top))
        left, top = self.at(self.byte(POS_X), self.byte(POS_Y) + 2)
        pygame.draw.rect(window, EYES_COLOUR, (left, top, 8 * MAP_SCALE, 3 * MAP_SCALE))

    def numbers(self) -> list[str]:
        carried = self.byte(CARRIED)
        match = self.byte(FLAGS) & MATCH_LIT
        return [f"game {self.byte(GAME_NUMBER) + 1}   {MODES.get(self.byte(GAME_STATE), '?')}",
                f"floor {self.byte(FLOOR) + 1}  room {self.byte(ROOM)}"
                f"   x {self.byte(POS_X)}  y {self.byte(POS_Y)}",
                f"lives {self.byte(LIVES)}   matches {self.byte(MATCHES):02X}",
                f"match {'lit, ' + str(self.byte(MATCH_TIME)) + ' s' if match else 'out'}"
                f"   monsters here {self.byte(MONSTERS_HERE)}",
                f"holding {ITEM_NAMES[carried] if carried < 5 else 'nothing'}"
                f"   urn shapes {[self.byte(URN_SHAPES + piece) for piece in range(3)]}",
                "the map: the engine's state - walls, eyes, items 0-4, monsters G B T"]

    def draw_numbers(self, window: pygame.Surface) -> None:
        for line, text in enumerate(self.numbers()):
            window.blit(self.font.render(text, True, TEXT_COLOUR), (8, PICTURE[1] + 8 + line * LINE_HEIGHT))


def held_buttons(cheat_left: int) -> set[int]:
    """The buttons the keys hold, and B and Select together for a few frames after O."""
    pressed = pygame.key.get_pressed()
    held = {button for key, button in KEYS.items() if pressed[key]}
    if cheat_left > 0:
        held |= {S.BUTTON_B, S.BUTTON_SELECT}
    return held


def main() -> None:
    shareable = shareable_wanted(sys.argv)
    rom = rom_path(shareable)
    if not os.path.exists(rom):
        build(shareable=shareable)
    machine = S.Snes(rom)
    pygame.init()
    with_map = "--map" in sys.argv
    window = pygame.display.set_mode(MAP_WINDOW if with_map else PICTURE)
    pygame.display.set_caption("Haunted House: By Matchlight")
    state_map = StateMap(machine, shareable) if with_map else None
    speaker = Speaker(machine.sample_rate())
    machine.recording = True
    cheat_left = 0
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_o:
                cheat_left = CHEAT_FRAMES
        if speaker.queued() >= SOUND_AHEAD:
            time.sleep(IDLE_SECONDS)
            continue
        machine.sound.clear()
        machine.run(1, held_buttons(cheat_left))
        cheat_left -= 1
        for samples in machine.sound:
            speaker.add(samples)
        show(window, machine, state_map)


def show(window: pygame.Surface, machine: S.Snes, state_map: "StateMap | None") -> None:
    """The latest picture, scaled, and with --map the state map beside it."""
    window.fill((0, 0, 0))
    if machine.picture is not None:
        frame = pygame.surfarray.make_surface(machine.picture[..., :3].swapaxes(0, 1))
        window.blit(pygame.transform.scale(frame, PICTURE), (0, 0))
    if state_map is not None:
        state_map.draw(window)
    pygame.display.flip()


if __name__ == "__main__":
    main()
