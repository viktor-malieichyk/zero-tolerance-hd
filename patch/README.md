# Zero Tolerance high frame rate patch

For **Zero Tolerance (USA, Europe) (Rev A)**, SHA-1 `d6d9733a619ba6be0dd76591d8dec621e4fdc17e`.
Emulator use only: it needs far more CPU than a real Mega Drive has.

## What it does

- **Fixed-rate game logic.** Logic runs at 10 Hz no matter how fast frames render. The original
  ties everything to frame rate and runs ~7–11 fps in play, so 10 Hz matches typical speed.
  Build with another rate via `python3 make_patch.py <hz>`.
  Frames between logic ticks re-render with the camera interpolated between the last two ticks
  (one tick of display latency), so turning and walking are smooth while game speed stays constant.
- **Single-VBlank framebuffer upload.** The original uploads each frame in two halves across two
  VBlanks (30 fps cap). The patch uploads it in one.
- **Top band (NTSC only).** On NTSC the 10 KB upload doesn't fit in VBlank and runs ~14 lines into
  the next frame, so during gameplay the top 15 lines are kept blank on every frame. That hides the
  weapon name labels above the weapon icons. PAL has no band.

## Use

Apply `zt_high_fps.ips` to the ROM, or use `Zero Tolerance (high fps).gen`.

Genesis Plus GX (RetroArch): set **CPU Speed** (`genesis_plus_gx_overclock`).

| CPU speed | NTSC fps | PAL fps |
|---|---|---|
| 100% | ~11 (same as original) | ~11 |
| 500% (menu max) | ~36 | ~46 |
| 800%+ | 60 | 50 (at 1500%) |

Stock Genesis Plus GX only offers up to 500%, and RetroArch resets unknown values to the default.
The HD core (`port/core/`, built with `apply_zt_hd.py`) also adds 600-1500%; with its HD renderer
switched off it is an ordinary Genesis Plus GX. To launch with it at 1000%, write a RetroArch settings
file that points at `tools/zt-core-options.cfg` and pass it with `--appendconfig`:

```
echo "core_options_path = \"$PWD/tools/zt-core-options.cfg\"" | cat tools/retroarch-zt.cfg - > tools/retroarch-zt.local.cfg
open -a RetroArch --args -L <path to core> --appendconfig "$PWD/tools/retroarch-zt.local.cfg" "$PWD/Zero Tolerance (high fps).gen"
```

For the HD renderer, use `play_mac.sh` (see the top-level README).

## Steam release (QUByte Classics: Zero Tolerance Collection, Windows)

The Steam version stores the ROM unencrypted as `res/game` and runs it in `ew_core.dll`, a Mednafen
Genesis core. Its ROM is Rev A plus QUByte changes, including a 15 fps limiter, and its emulator
has a 68000 clock divider (7 = normal, 3 with the `-turbo` launch option, about 2.33x).

`python3 make_patch.py --steam <Steam install folder>` writes `steam/res/game` and
`steam/ew_core.dll` (back up the originals, then copy both over the install). For the HD renderer on
Steam, use `steam/res/game` with the drop-in `ew_core.dll` from `port/core/steam/` instead. It also writes
`steam/zt_high_fps_steam.ips` for the ROM alone. The ROM gets the same patch plus the limiter
removed. The DLL gets a 2-byte change that sets the divider to 1 (7x CPU), with or without `-turbo`.
Steam's "Verify integrity of game files" restores the originals.

Tested with a native macOS build of the Steam emulator's own source (`src.7z`): 60 fps, constant
game speed, constant 16-line top band, deaths and agent screens clean. I couldn't run the actual
Windows executable here.

## Build

`python3 make_patch.py` checks the ROM hash, assembles `zt_high_fps.asm` with `vasmm68k_mot`
([vasm](http://sun.hasenbraten.de/vasm/), `make CPU=m68k SYNTAX=mot`; in `tools/` or on `PATH`),
applies the hooks, and writes the ROM and the IPS.

`tools/bench.py` is a headless libretro harness (Genesis Plus GX) used for testing. For example:
`python3 tools/bench.py "Zero Tolerance (high fps).gen" --state tools/level1.state --speed --oc 1000`
prints fps and turn rate. It needs Pillow. Save states and the HUD reference screenshot it uses aren't
included (they contain game data): `--mkstate` makes a state, and a gameplay screenshot saved as
`tools/hud_ref.png` serves as the reference.

## Not tested

Two-player link cable mode, level-to-level transitions via the exit lift, and floor cells with
lift or stair animations. Tested: death and respawn at 100% and 1000%, combat with enemies.
