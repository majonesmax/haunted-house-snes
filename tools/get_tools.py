"""Fetch the tools the build and the checks need, at pinned versions - none of them is committed:

  tools/pvsneslib/   PVSnesLib (the C compiler, the assembler and linker, the library, its converters)
  tools/tad/         the Terrific Audio Driver's source (its compiler is built with cargo: see docs/plan.md)
  cores/             snes9x's libretro core, for the checks (libretro's nightly builds keep only the latest)

Usage: python tools/get_tools.py [--force]
"""

import io
import os
import subprocess
import sys
import urllib.request
import zipfile

from snes import CORE

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PVSNESLIB_VERSION = "4.6.0"
PVSNESLIB_HOME = os.path.join(ROOT, "tools", "pvsneslib")
PVSNESLIB_SYSTEMS = {"darwin": "darwin", "win32": "windows"}   # (linux otherwise)
TAD_VERSION = "v0.4.2"
TAD_HOME = os.path.join(ROOT, "tools", "tad")
NIGHTLY = "https://buildbot.libretro.com/nightly"
CORE_SYSTEMS = {"darwin": "apple/osx/arm64", "win32": "windows/x86_64"}   # (linux x86_64 otherwise)


def fetch(url: str) -> bytes:
    print("fetching", url)
    with urllib.request.urlopen(url) as response:
        return response.read()


def get_pvsneslib(force: bool) -> None:
    if os.path.exists(os.path.join(PVSNESLIB_HOME, "pvsneslib", "devkitsnes")) and not force:
        print("PVSnesLib is already in", PVSNESLIB_HOME)
        return
    system = PVSNESLIB_SYSTEMS.get(sys.platform, "linux")
    name = f"pvsneslib_{PVSNESLIB_VERSION.replace('.', '')}_64b_{system}_release.zip"
    url = f"https://github.com/alekmaul/pvsneslib/releases/download/{PVSNESLIB_VERSION}/{name}"
    archive = zipfile.ZipFile(io.BytesIO(fetch(url)))
    os.makedirs(PVSNESLIB_HOME, exist_ok=True)
    archive.extractall(PVSNESLIB_HOME)
    for folder, _dirs, files in os.walk(os.path.join(PVSNESLIB_HOME, "pvsneslib", "devkitsnes")):
        for file in files:   # zip files keep no permission bits: the tools must be runnable
            os.chmod(os.path.join(folder, file), 0o755)
    print("PVSnesLib", PVSNESLIB_VERSION, "in", PVSNESLIB_HOME)


def get_audio_driver(force: bool) -> None:
    if os.path.exists(os.path.join(TAD_HOME, "Cargo.toml")) and not force:
        print("the audio driver is already in", TAD_HOME)
        return
    command = ["git", "clone", "--depth", "1", "--branch", TAD_VERSION,
               "https://github.com/undisbeliever/terrific-audio-driver", TAD_HOME]
    subprocess.run(command, check=True)
    print("Terrific Audio Driver", TAD_VERSION, "in", TAD_HOME, "- build its compiler with:")
    print("  cargo build --release --manifest-path", os.path.join(TAD_HOME, "Cargo.toml"))


def get_core(force: bool) -> None:
    if os.path.exists(CORE) and not force:
        print("the core is already there:", CORE)
        return
    system = CORE_SYSTEMS.get(sys.platform, "linux/x86_64")
    name = os.path.basename(CORE)
    archive = zipfile.ZipFile(io.BytesIO(fetch(f"{NIGHTLY}/{system}/latest/{name}.zip")))
    os.makedirs(os.path.dirname(CORE), exist_ok=True)
    with open(CORE, "wb") as core_file:
        core_file.write(archive.read(name))
    print("snes9x core in", CORE)


def main() -> None:
    force = "--force" in sys.argv
    get_pvsneslib(force)
    get_audio_driver(force)
    get_core(force)


if __name__ == "__main__":
    main()
