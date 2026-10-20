"""A Super Nintendo emulator to test the game in: the snes9x libretro core, loaded as a library and run a
frame at a time, with no window. The checks use it to play the built ROM and read its work RAM between frames.

    snes = Snes("build/shareable/haunted_house.sfc")
    snes.run(60, held={BUTTON_B})    # a second with B held
    snes.ram[0x0000]                 # the 128K of work RAM ($7E0000-$7FFFFF), live
    snes.picture                     # the last frame, RGB

The core goes in cores/ (python tools/get_tools.py). It's the NES game's harness (tools/nes.py there) with the
SNES's core, RAM and buttons.
"""

import ctypes as C
import os
import sys
from typing import Any, Callable

import numpy as np
from numpy.typing import NDArray

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY_ENDINGS = {"darwin": ".dylib", "win32": ".dll"}   # (and .so everywhere else)
CORE = os.path.join(ROOT, "cores", "snes9x_libretro" + LIBRARY_ENDINGS.get(sys.platform, ".so"))
WORK_DIR = os.fsencode(os.path.join(ROOT, "build", "core"))

# libretro constants (libretro.h)
ENV_GET_CAN_DUPE, ENV_GET_SYSTEM_DIRECTORY, ENV_SET_PIXEL_FORMAT = 3, 9, 10
ENV_GET_VARIABLE, ENV_SET_VARIABLES, ENV_GET_VARIABLE_UPDATE, ENV_GET_SAVE_DIRECTORY = 15, 16, 17, 31
PIXEL_XRGB8888, PIXEL_RGB565 = 1, 2   # snes9x draws in RGB565 and refuses a frontend that won't take it
DEVICE_JOYPAD = 1
MEMORY_SYSTEM_RAM = 2
BUTTON_B, BUTTON_Y, BUTTON_SELECT, BUTTON_START = 0, 1, 2, 3   # the libretro joypad's numbering
BUTTON_UP, BUTTON_DOWN, BUTTON_LEFT, BUTTON_RIGHT = 4, 5, 6, 7
BUTTON_A, BUTTON_X, BUTTON_L, BUTTON_R = 8, 9, 10, 11
WORK_RAM = 128 * 1024

Ram = NDArray[np.uint8]
Picture = NDArray[np.uint8]


def rgb565_to_rgb(pairs: NDArray[np.uint8]) -> Picture:
    """Pixels of two bytes (5 bits red, 6 green, 5 blue, low byte first) as 8-bit RGB."""
    packed = pairs[..., 0].astype(np.uint16) | pairs[..., 1].astype(np.uint16) << 8
    red = (packed >> 11) & 0x1F
    green = (packed >> 5) & 0x3F
    blue = packed & 0x1F
    picture = np.stack([red << 3 | red >> 2, green << 2 | green >> 4, blue << 3 | blue >> 2], axis=-1)
    return picture.astype(np.uint8)


class GameInfo(C.Structure):
    _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]


class AvInfo(C.Structure):
    _fields_ = [("base_width", C.c_uint), ("base_height", C.c_uint), ("max_width", C.c_uint),
                ("max_height", C.c_uint), ("aspect_ratio", C.c_float), ("fps", C.c_double),
                ("sample_rate", C.c_double)]


class Variable(C.Structure):
    _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIO_BATCH_CB = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
STATE_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)


class Snes:
    def __init__(self, rom: str, core: str = CORE):
        self.pixel_format = PIXEL_XRGB8888
        os.makedirs(WORK_DIR, exist_ok=True)
        self.lib = C.CDLL(core)
        self.held: set[int] = set()
        self.picture: Picture | None = None
        self.sound: list[NDArray[np.int16]] = []   # the sound's samples, kept while recording is on
        self.recording = False
        self.options: dict[bytes, C.c_char_p] = {}
        self._callbacks = [ENV_CB(self._environment), VIDEO_CB(self._video),
                           AUDIO_CB(lambda left, right: None), AUDIO_BATCH_CB(self._sound),
                           POLL_CB(lambda: None), STATE_CB(self._input)]
        setters = (self.lib.retro_set_environment, self.lib.retro_set_video_refresh,
                   self.lib.retro_set_audio_sample, self.lib.retro_set_audio_sample_batch,
                   self.lib.retro_set_input_poll, self.lib.retro_set_input_state)
        for setter, callback in zip(setters, self._callbacks):
            setter(callback)
        self.lib.retro_init()
        self.ram = self._load(rom)

    def _load(self, rom: str) -> Ram:
        with open(rom, "rb") as rom_file:
            self._rom_bytes = C.create_string_buffer(rom_file.read())   # kept: the core reads it later
        size = len(self._rom_bytes) - 1
        game = GameInfo(rom.encode(), C.cast(self._rom_bytes, C.c_void_p), size, None)
        if not self.lib.retro_load_game(C.byref(game)):
            raise RuntimeError(f"the core refused {rom}")
        self.lib.retro_set_controller_port_device(0, DEVICE_JOYPAD)
        self.lib.retro_get_memory_data.restype = C.c_void_p
        address = self.lib.retro_get_memory_data(MEMORY_SYSTEM_RAM)
        return np.ctypeslib.as_array(C.cast(address, C.POINTER(C.c_uint8)), shape=(WORK_RAM,))

    def save(self) -> bytes:
        """The whole console's state, to come back to with load()."""
        self.lib.retro_serialize_size.restype = C.c_size_t
        size = self.lib.retro_serialize_size()
        buffer = C.create_string_buffer(size)
        if not self.lib.retro_serialize(buffer, size):
            raise RuntimeError("the core would not save its state")
        return buffer.raw

    def load(self, state: bytes) -> None:
        buffer = C.create_string_buffer(state, len(state))
        if not self.lib.retro_unserialize(buffer, len(state)):
            raise RuntimeError("the core would not load the state")

    def run(self, frames: int = 1, held: set[int] | None = None) -> None:
        self.held = held or set()
        for _ in range(frames):
            self.lib.retro_run()

    # --- what the core asks of us ------------------------------------------------------------
    def _environment(self, command: int, data: Any) -> bool:
        answers: dict[int, Callable[[Any], bool]] = {
            ENV_GET_CAN_DUPE: lambda data: self._set_bool(data, True),
            ENV_SET_PIXEL_FORMAT: self._take_pixel_format,
            ENV_GET_SYSTEM_DIRECTORY: self._give_directory,
            ENV_GET_SAVE_DIRECTORY: self._give_directory,
            ENV_SET_VARIABLES: lambda data: True,       # every setting stays at the core's default
            ENV_GET_VARIABLE: lambda data: False,
            ENV_GET_VARIABLE_UPDATE: lambda data: self._set_bool(data, False),
        }
        answer = answers.get(command & 0xFFFF)
        return answer(data) if answer else False

    def _take_pixel_format(self, data: Any) -> bool:
        self.pixel_format = C.cast(data, C.POINTER(C.c_int))[0]
        return self.pixel_format in (PIXEL_XRGB8888, PIXEL_RGB565)

    @staticmethod
    def _set_bool(data: Any, value: bool) -> bool:
        C.cast(data, C.POINTER(C.c_bool))[0] = value
        return True

    @staticmethod
    def _give_directory(data: Any) -> bool:
        C.cast(data, C.POINTER(C.c_char_p))[0] = WORK_DIR
        return True

    def _video(self, data: Any, width: int, height: int, pitch: int) -> None:
        if not data:
            return
        rows = np.ctypeslib.as_array(C.cast(data, C.POINTER(C.c_uint8)), shape=(height, pitch))
        if self.pixel_format == PIXEL_RGB565:
            self.picture = rgb565_to_rgb(rows[:, :width * 2].reshape(height, width, 2))
        else:
            self.picture = rows[:, :width * 4].reshape(height, width, 4)[..., [2, 1, 0]].copy()

    def _sound(self, data: Any, frames: int) -> int:
        if self.recording:
            self.sound.append(np.ctypeslib.as_array(data, shape=(frames * 2,)).reshape(frames, 2).copy())
        return frames

    def sample_rate(self) -> float:
        """The sound's samples a second."""
        info = AvInfo()
        self.lib.retro_get_system_av_info(C.byref(info))
        return info.sample_rate

    def _input(self, port: int, device: int, index: int, button: int) -> int:
        return 1 if port == 0 and device == DEVICE_JOYPAD and button in self.held else 0
