# Zero Tolerance HD core (Genesis Plus GX)

The game runs unchanged in emulation, with the `zt_high_fps` patched ROM. Each 10 Hz logic tick, hooks on the
68000 snapshot work RAM and the tick's sprite draw calls. Every video frame, `zt_hd.c` re-renders the 3D
view natively, interpolating between the last two ticks. It uses the game's own walls, doors, textures,
shading, floor gradient, sprites, and the plane A starfield/planet. A compact HUD cut from the emulated
screen goes on top. Non-gameplay screens (menus, map, agent select) are shown scaled.

No CPU overclock is needed: in HD mode the ROM patch skips the 68000's in-between renders and the host
draws those frames. Cost on Apple Silicon (native), emulation included: about 2.0-2.5 ms per frame at
1920x1080.

## Build

    git clone --depth 1 https://github.com/libretro/Genesis-Plus-GX.git
    python3 apply_zt_hd.py Genesis-Plus-GX
    cd Genesis-Plus-GX && make -f Makefile.libretro      # add CC="cc -arch x86_64" for Intel RetroArch

## Core options

- `genesis_plus_gx_zt_hd`: enabled / disabled
- `genesis_plus_gx_zt_hd_res`: 960x540 ... 2560x1440
- `genesis_plus_gx_zt_hd_fov`: 90 (original) ... 120
- `genesis_plus_gx_zt_hd_ui_scale`: `auto` (output height / 360) or 1 ... 4. The HUD is three console
  modules along the bottom, built from the original HUD's pieces (design: `port/design`): left the portrait
  with "+ health" under it, middle the weapons bar (ammo counts redrawn in Menlo Bold at the output
  resolution, `zt_hud_font.h` from `make_hud_font.py`), right "ENEMIES <count>" over the map.
- `genesis_plus_gx_zt_hd_autoswitch`: `on` (default) or `off`. When the current weapon runs out of ammo, switch
  to the best weapon left (a gun, then grenades or mines, then the fire extinguisher; the fists, the melee
  weapon, last) by pressing C for you. Off: the original (you are left on the fists).
- `genesis_plus_gx_zt_hd_layout`: `hd` (HD only), `side_by_side` (original left, HD right; 1920 -> 1920x540),
  `top_bottom` (original above HD; 1920 -> 960x1080), or `toggle` (switch between HD and original with a key)
- `genesis_plus_gx_zt_hd_toggle_key`: switch key, default G
- `genesis_plus_gx_zt_hd_menu_key`: in-game settings menu key, default M
- `genesis_plus_gx_zt_hd_weapon`: shown / hidden (the player's weapon sprite in the HD view)
- `genesis_plus_gx_zt_hd_sky`: `original` (star band at its size) or `fill` (scaled uniformly to fill the view
  height; the planet stays round; one seam at a fixed direction since the panorama no longer divides 360 deg)

- `genesis_plus_gx_zt_hd_sky_ext`: `full_planet` (default), `stars` or `black`. The original sky art is an
  80-row band. `stars` repeats the level's own band above and below it (shifted sideways per repeat, star
  columns only, so the planet isn't copied). `full_planet` also completes the planet the art cuts off: a
  circle is fitted to its visible rim and the missing top is the reflection of the lower part about the
  centre row (same limb shading), blended to the art's brightness at the cut. Built from the level's own
  tiles once the planet has been on screen.

## Texels and shading

A texture byte is two pixels side by side (high nibble left, low nibble right); signs and stripes use the
two halves for double horizontal detail, so each byte is sampled as two half-width texels. Distance shading
maps a colour through the game's shade tables, which can return two colours (a dither between levels);
`genesis_plus_gx_zt_hd_shading` = `smooth` (default) blends them, `dither` draws the pattern. The floor
gradient's two-colour bytes are treated the same way.

## Sky panorama PNG

The game streams each sky from a 128 x 16 tile map (pointer at `$FF271E`: `$153106`, or `$1553E6` for the
planet sky). The HD sky reads that map whole. With "Sky beyond band: Stars, full planet", the core uses
`zt_sky_<map address>.png` from the saves folder (next to `zt_hd.cfg`) when it exists:

    python3 make_sky.py <rom> <dump> 1553E6 zt_sky_1553E6.png

`<dump>.vram`/`.cram` are the VDP's VRAM and CRAM from a level using that sky. The PNG is 1024 px wide
(360 degrees) and indexed with CRAM indices, so palette fades still apply; it keeps the original 80 art rows,
completes the planet, and adds stars above and below from the art's own star shapes. It can be edited
(keep it indexed with the same palette, or save as RGB/RGBA for fixed colours). Without a PNG the core
builds the same thing at runtime. `patch/tools/zt_sky_1553E6.png` is the one for level 1.

## Steam release

`steam/ew_wrap.c` implements the Steam frontend's `ew_*` interface (from `src.7z` in the Steam release) on
top of this core, so `steam/build_steam.sh` builds a 32-bit `ew_core.dll` that replaces the shipped
Mednafen one. Notes on the frontend (`zero tolerance.exe`) are in the file's header: it allocates its
frame buffer from the first screen size it asks for, and sizes its viewport from the screen size and the
texture from the raster size. The `-turbo` launch option (68000 clock divider 7 -> 3) isn't used.

## In-game menu

Press the menu key (M). The game pauses. Up/Down select; Left/Right change resolution, field of view, layout,
switch key, HUD scale, weapon, sky and menu key. Changes apply immediately (including the output size) and
are saved to `zt_hd.cfg` in RetroArch's save folder. That file overrides the core options on the next start.

`patch/tools/retroarch-zt-hd.cfg` launches with HD on at 1280x720:

    open -a RetroArch --args -L <tools>/genesis_plus_gx_zt_hd_x86_64.dylib \
      --appendconfig <tools>/retroarch-zt-hd.cfg "<patch>/Zero Tolerance (high fps).gen"

## Hooks (68000 PC)

- `$B9A6`: render start. Ignored for between-ticks renders (`$FF7762` set).
- `$1BCB4`: sprite draw (a0 object, a1 sub-frame record, a2 piece base).
- ROM long at `$1D0034` (patch jump table +52): end of the tick render. The snapshot is committed here.

The core sets `$FF7772` = 1 (`ZT_HD`) so the ROM skips the 68000's in-between renders and the NTSC top band.

## Notes

- In HD mode the ROM patch uploads the native view the original way (half per VBlank, display on), so the
  emulated screen has no top band and no flicker.
- The weapon is VDP sprites inside the native view area (sprite table at `reg[5]`), drawn scaled above the
  weapons bar.
- Sprites: every piece the game draws (`$EDA0`) is captured with its anchor (object at `$13360`/`$13388`,
  map item at `$113EE`) and re-projected. That covers enemies, pickups, projectiles and effects. Objects are
  not culled by the native FOV, so they also appear at the edges of a wider HD view; map items the game's
  90 degree cast didn't reach are drawn from the last pieces seen for their type.
- Sky: plane A only holds half of the 1024 px panorama (the game streams tile columns as you turn). The
  columns the game keeps current are copied into a host panorama of tile entries, so the planet stays whole
  at any FOV. Columns not yet seen since the level started fall back to plane A.
- Multi-level walls (stair/pit/upper-floor types, lift walls `$9862`) get their vertical offsets (the cell
  handlers are interpreted) and the dark floor/ceiling they cause; floor/ceiling edges (types `$31-$5B`,
  e.g. roofed rooms) are captured at `$9D72`. Wall and sprite horizons are the ones the game used that tick.

## Not done yet

- Stair/pit cell types aren't in level 1, so their offsets are implemented from the code but not compared
  against the original yet (level 1's roofed room and lift walls are).
- Map item layouts are taken from the largest view of each item type so far (the game's rects are in whole
  native columns); the first time you walk up to a new item type its layout can shift slightly once.
- The walk-animation accumulator is advanced in the draw code, so in the 60 fps (non-HD) patch walk cycles
  run faster; HD mode doesn't render between ticks, so it's unaffected.
