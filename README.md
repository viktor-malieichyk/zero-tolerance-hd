# Zero Tolerance: high frame rate and HD

Mods for **Zero Tolerance** (Technopop, Accolade, 1994), the Mega Drive / Genesis first-person shooter:

1. **High frame rate patch** (`patch/`): a ROM patch that runs the game logic at a fixed 10 Hz and
   renders the frames in between with an interpolated camera. With a CPU overclock in the emulator the
   view runs at up to 60 fps while the game keeps its original speed.
2. **HD renderer** (`port/core/`): a modified [Genesis Plus GX](https://github.com/libretro/Genesis-Plus-GX)
   libretro core that re-renders the 3D view natively at any resolution (960x540 to 3840x2160) and field
   of view, from the running game's own state, textures, sprites and sky. The game runs unchanged in
   emulation; the HUD is rearranged along the bottom. In-game settings menu, side-by-side or switchable
   original view.
3. **Steam drop-in** (`port/core/steam/`): the HD renderer as a replacement `ew_core.dll` for the Steam
   release (QUByte Classics), so it runs from the Steam game without RetroArch.

No game data is included. You need your own copy of the game. Supported ROMs (`patch/games.py`):

| Game | File in this folder | SHA-1 |
|---|---|---|
| Zero Tolerance (USA, Europe) (Rev A) | `Zero Tolerance (USA, Europe) (Rev A).gen` | `d6d9733a619ba6be0dd76591d8dec621e4fdc17e` |
| Zero Tolerance, Rev A with the Sega Mouse hack | `ZT.bin` | `e0dd42d65302c62904bbbe226efc68e2c71fdfab` |
| Zero Tolerance: Underground | `ZTU.bin` | `9f8df85692bea0b794dbf6a5f4f3ee579840694a` |
| Beyond Zero Tolerance (unreleased sequel, build 062393a) | `BZT.BIN` | `ab7791def9ad91c0f0870b1f928ceb13b76acb9c` |

The Steam drop-in supports the Steam release of the first game.

## Layout

| Path | What |
|---|---|
| `patch/zt_high_fps.asm`, `patch/make_patch.py` | the ROM patch (68000 assembly) and its builder (cartridge and Steam ROM) |
| `patch/games.py` | the supported ROMs and each one's addresses (the HD core's are in `zt_hd.c`, `zt_games[]`) |
| `patch/play_mac.sh`, `patch/tools/*.cfg` | macOS launcher and RetroArch settings |
| `patch/windows/`, `patch/mac/` | Windows launcher (`play_zt_hd.bat`), READMEs and settings for the RetroArch packages |
| `make_release.sh` | builds the release packages (Steam, Windows RetroArch, macOS RetroArch) into `release/` |
| `patch/steam_hd/` | README and settings for the Steam drop-in package |
| `port/core/zt_hd.c`, `zt_hd.h`, `zt_font.h` | the HD renderer |
| `port/core/apply_zt_hd.py` | patches a Genesis Plus GX checkout (hooks, core options, video output, menu) |
| `port/core/make_sky.py` | builds the full sky panorama PNG (completed planet, more stars) from the game's tiles |
| `port/core/steam/` | `ew_core.dll` wrapper for the Steam frontend and its build script |
| `port/*.py`, `port/NOTES.md` | the Python proof of concept renderer and the reverse-engineering notes (formats, addresses) |

## Build

Requirements: Python 3 (with Pillow and NumPy for `make_sky.py`), a C compiler, `make`,
[vasm](http://sun.hasenbraten.de/vasm/) (`vasmm68k_mot`, built with `make CPU=m68k SYNTAX=mot`) in
`patch/tools/` or on `PATH`, and for Windows builds mingw-w64.

**ROM patch.** Put the ROMs, named as in the table above, in this folder, then

    python3 patch/make_patch.py            # or name some: zt, zt_mouse, ztu, bzt

For each ROM found it writes a patched ROM and an IPS into `patch/` (Rev A: `Zero Tolerance (high fps).gen`
and `zt_high_fps.ips`; the others `<name> (high fps).bin` and `<name>.ips`). The HD core needs a patched ROM.

**HD core** (RetroArch, macOS / Linux / Windows):

    git clone --depth 1 https://github.com/libretro/Genesis-Plus-GX.git
    python3 port/core/apply_zt_hd.py Genesis-Plus-GX
    make -C Genesis-Plus-GX -f Makefile.libretro                       # this machine
    make -C Genesis-Plus-GX -f Makefile.libretro CC="cc -arch x86_64"  # Intel macOS RetroArch
    make -C Genesis-Plus-GX -f Makefile.libretro platform=win \
         CC=x86_64-w64-mingw32-gcc CXX=x86_64-w64-mingw32-g++ AR=x86_64-w64-mingw32-ar   # Windows

On macOS, copy the core to `patch/tools/genesis_plus_gx_zt_hd.dylib` (Apple Silicon RetroArch) or
`genesis_plus_gx_zt_hd_x86_64.dylib` (Intel RetroArch) and run `patch/play_mac.sh`.
See `port/core/README.md` for the core options and the in-game menu.

**Steam drop-in:** `sh port/core/steam/build_steam.sh <clean Genesis-Plus-GX checkout> <Steam game folder>`
builds `ew_core.dll` (32-bit, needs `i686-w64-mingw32-gcc`). It runs `make_patch.py --steam` and builds the
resulting patch into the DLL, which applies it in memory to the game's own `res/game` (checked by CRC32),
so the release package contains no ROM and installs by replacing `ew_core.dll` only. See
`patch/steam_hd/README.txt`.

**Release packages:** `sh make_release.sh <version> <Steam ew_core.dll> <Windows x64 core> <macOS arm64 core>
<macOS x86_64 core>` (after `python3 patch/make_patch.py`). The RetroArch packages carry the patch as
`Zero Tolerance (USA, Europe) (Rev A).ips`, which RetroArch applies to the user's ROM of that name as it loads it.

**Sky panorama** (optional, for the planet levels): `port/core/make_sky.py` builds
`zt_sky_1553E6.png` from a VRAM/CRAM dump of a level with that sky; put it next to the game or in
RetroArch's saves folder. Without it the core builds the same sky at runtime.

## Status

Level 1 is tested end to end on macOS (RetroArch). The Windows RetroArch core and the Steam drop-in
are built and tested through test harnesses, not on Windows itself. Stair/pit cells don't occur in
level 1, so their rendering is implemented from the game's code but not compared with the original.

## Credits and licences

The code in this repository is under the MIT licence (`LICENSE`). Zero Tolerance is © 1994 Technopop / Accolade; the Steam release is by QUByte Interactive. This
project contains no part of the game. Genesis Plus GX is by Eke-Eke and contributors under its own
non-commercial licence, which also applies to cores built from it. The menu font in `zt_font.h` is
rendered from Menlo (Bitstream Vera licence).
