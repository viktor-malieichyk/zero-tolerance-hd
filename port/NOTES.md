# Zero Tolerance native renderer: proof of concept

`ztrender.py` re-renders the 3D view from a 64 KB RAM image of the game plus the ROM, at any
resolution and field of view. With the original settings it reproduces the game's own frame buffer.
All addresses are Rev A (the Steam ROM has the same layout).

## Results (95 frames from real play, horizon 0)

Exact mode (`render(st, affine="game")`) uses the game's integer projection, column routines and shading:
- Column height exact: 98.0%. Texture column exact: 98.3%.
- **Wall pixels identical to the game's frame buffer: 99.1%.** Median frame 99.2%; 15 frames are pixel-identical.
- The remaining differences are mostly the original's 65-ray visibility (thin faces popping in and out) and
  the shaded-face path some cell types use.

Full 3D view (walls + floor/ceiling background + sprites, `showcase2.py`), 53 combat frames:
- **98.3% of all view pixels identical to the game's frame buffer** (median frame 99.6%).

High-res mode (any size/FOV): perspective-correct, original distance shading, the floor gradient,
and enemies projected from their world positions. See `images/enemy_*.png`.

## Known gaps (Python PoC; the HD core in `core/` handles these, see below)

- Sliding doors, multi-level walls and floor/ceiling edges aren't in the Python renderer.
- Sprite frame/view selection comes from captured draw calls (the original code picks them); a
  standalone port would need the per-object draw routines too.

**Multi-level walls** (cell handlers `$945E-$9861`, types `$0C-$11`, `$38-$3B`, `$40-$43`, `$48-$4B`)
- Solid. Each handler tests the player's elevation `$FF116E` (or the cell's side, d0/d1 = cell - camera
  cell) and stores 4 mode words: N `$FF1174`, S `$FF1176`, E `$FF1178`, W `$FF117A`.
- A mode word is two signed bytes: the vertical offset at the face's start (screen left) and end; 64 = one
  wall height. `$C70E-$C7D4` copies the face's word to `$FF1172`; nonzero sends the column to `$D0C4`,
  which adds the interpolated offset to the horizon: the wall shifts by height * (horizon + m) / 64 rows
  (`$D202`). The floor/ceiling rows of that column come from `$D074` (solid colour 1).
- Type `$30` (`$9862`): lift shaft walls, offset = elevation low byte | 1 on all faces.
- Render (`$BAE6`): if the player's cell type is >= 6 the horizon is reduced by `$FF116E` for the walls,
  then `$BB6C`/`$BB7E` add it back before sprites are projected.

**Floor/ceiling edges** (handlers for types `$31-$5B`)
- Register a corner pair (relative to the camera cell `$FF0E06/08`) plus a flag in a list at `$FF1182`
  (6 bytes each, count `$FF1180`) via `$9D42` (flag) / `$9D4A`.
- `$9D72` (after the walls) draws each edge with `$D5CE`: in columns where the edge is nearer than the
  wall, the floor and ceiling between the viewer and the edge get the normal background (flag) or colour 1.
  `$7F92` gives wall-less columns the normal background, before or after the edges depending on the
  player's cell type (table `$BB90`). In level 1, types `$54`/`$56` mark the roofed room behind the door.

**Sprite pieces**: all go through `$EDA0` (d1 column, d2 row, d4 x d0 size, a1 16x32 texels, mirror
`$FF1088`, shade list `$FF1096`, scale `$FF1094`). Objects are drawn from `$13360`/`$13388` (a0 = object);
map items (types with handler `$944E`) from `$113EE` (a3 = record in the list at `$FF10A2`: cell dy, dx,
type, scale, column). `$1329A` projects objects within `$C00` without FOV culling (scale capped at 300).

**Sky**: the panorama is 1024 px (128 tiles) wide; plane A (64 tiles) holds the part around the view.
Columns from about -160 to +184 px of the screen centre are kept current.

## Formats and constants

**Camera** (a6 = `$FF8000`)
- X/Y: `$FF0DEC`/`$FF0DEE`, 8.8 fixed point, 256 units per cell, wraps at `$2000`.
- Angle: `$FF0E04`, 0-511. 0 = -Y, 128 = +X, 256 = +Y, 384 = -X.
- Direction: `$FF0E00/02` = table at `$8124 + angle*4` (cos, sin), length 256.
- Horizon offset: `$FF0E1A`. Wobble offsets: `$FF0E28` (angle) and `$FF0E2A` (horizon); 0 when inactive.
- The renderer pulls the camera back by direction/8 (32 units) while drawing (`$B9A6`).

**Projection**
- 128 columns of 2 px, 80 rows, 90 deg FOV.
- Screen column = 64 + 64*lateral/depth. Clipping at |lateral| = depth.
- Camera space: depth = rel . dir, lateral = rel_y*dir_x - rel_x*dir_y (`$C9A8`/`$CA04`).
- Wall height h = 64/depth (in cells). Centred on row 40.
- The top texture is drawn upward from the centre and the bottom texture downward, 32 texels each over h/2 rows.
- A per-column height buffer at `$FF6126` keeps the tallest wall drawn in each column.
- Texture u is interpolated **affinely** across each face on screen.

**Map**
- 32x32 cell bytes; pointer at `$FF1024` (e.g. `$FF7CD6`).
- Cell type: 256-byte table at `$FF7BC6`. 0 empty, 1 wall, 2-5 diagonals; 6+ go through the
  `$9226` dispatch table at `$923A`. Handler `$9458` = solid (types `$79-$80` in level 1),
  `$9454`/`$944E` = passable.
- View radius in cells: `$FF0EB4` (square around the camera cell).

**Faces**
- 4 words per cell at `$FF73C6 + cell*8`: 0 north, 1 west, 2 east, 3 south.
- Each word selects a strip list at `$FF63C6 + id*16`: 4 strips of (top texture, bottom texture).
- A face is 64x64 texels: 4 strips across, each 16 columns; top and bottom textures 32 rows each.
- Texture u = 0 is at the end of the face on the viewer's left:
  north `1-frac(x)`, south `frac(x)`, west `frac(y)`, east `1-frac(y)`.
- Diagonals (end at u=0 -> end at u=1, cell-local; face word):
  type 4: (1,1)->(0,0), word 0; type 2: (0,0)->(1,1), word 3;
  type 3: (1,0)->(0,1), word 0; type 5: (0,1)->(1,0), word 3.
  The half on the other side of the diagonal from the viewer is solid.

**Column drawing (native)**
- Heights are rounded down to even. For h <= 80, a pre-written routine per height (table at `$4392`,
  or `$4436` when `$FF0EAA` says so) first copies the background rows above the wall, then writes
  h rows. Each row is a texel byte from the top (`a1`) or bottom (`a2`) texture column, at a fixed offset.
  `colroutines.py` extracts every height's row list from the ROM.
- Distance shading: routines for heights <= 40 in the `$4392` set translate each byte through one of
  8 shade tables, pointers at `$FF0E8A..$FF0EA6` (ROM `$3392 + n*$100`). Height 40 = level 0, height 2 = level 7.
  A shaded byte can hold two different nibbles, so the two pixels of a column dither between levels.
- For h > 80 (`0xCE74`): from row 40 outward, the top texel goes upward from 31 and the bottom texel downward from 0.
  An error counter starts at h, drops by 64 per row, and steps the texel when negative (then adds h). No shading.
- Face spans use the original's integer math: `game_face()` in `ztrender.py` mirrors `$CA4C-$CCDC` and
  `$CD5E` (`divs` truncation, clipping, `iz` step, texture step taken before the first column).

**Doors**
- Types 6/7 (handlers `$AF5E`/`$AD8C`): a thin wall through the cell middle (east-west at y+0.5 or
  north-south at x+0.5), using strip list `$12` (`$FF64E6`). Rays pass through; the door is drawn nearer.
- Type `$2A` (`$9A7E`) is an enemy spawn point (the cell is cleared when the player is within `$800`), not a wall.

**Floor / ceiling background**
- `$D49A` builds two 80-byte columns at `$FF6226` from a ROM gradient (pointer `$FF0EAE`), shifted by
  the horizon. Even screen columns copy `+$50`, odd columns `+$00`, which gives the dithered gradient.
- Column routines copy the rows above and below the wall from it (shared tail at `$4836`).

**Objects and sprites**
- Object list: count `$FF24E8`, head `$FF24EA`, linked by +0.
- Fields: +`$0E` draw routine, +`$12` AI routine, +`$20/$22` position, +`$24` height offset,
  +`$2A/$2C` facing/velocity, +`$32` floor, +`$34` state, +`$35` direction, +`$3C` walk-animation
  accumulator, +`$42` animation table (ROM).
- `$1329A` projects visible objects (same projection as walls: scale = `$10000/(D>>6)`, column
  = 64 + lateral/(D>>6)). They go into a heap sorted by scale (`$133C0`) and are drawn far to near
  by calling +`$0E`.
- The enemy routine `$1856C` picks a frame 0-13 from state/direction. `$1BA04` picks a view
  (1/2/4/6/8 views; facing vs view direction, thresholds `$9B`/`$C8`/`$5A`), then a sub-frame. Walking
  uses the +`$3C` accumulator, which is advanced **in the draw routine**: the fixed-tick patch's extra
  frames speed up walk cycles; still to fix.
- Sub-frame record (38 bytes): +0/+1 x/y anchor (0 none, 1 centre, 2 end), +2/+3 piece width/height
  factors (width = f*scale>>5 columns, height = f*scale>>4 rows), +4/+5 grid columns/rows, +6 16
  attribute bytes (nonzero = mirrored), +`$16` 16 piece IDs (4x4 grid).
- Pieces: 512 bytes = 16x32 texels, column-major, like wall textures, at animation base +
  id*512. Texel 0 is transparent. y = ((horizon - bob - z) * scale >> 6) + 40.
- Piece drawer `$EDA0`: 16 texel columns over the scaled width (accumulator +16 per column).
  Depth test against the wall height buffer. Shade list `$FF1096` (`$ED50` = unshaded; otherwise
  5 levels from scale>>3).
- Hook point for an emulator-hosted renderer: `0x1BCB4`, where a0 = object, a1 = sub-frame record,
  a2 = piece base, d1 = column, d5 = scale.

**Textures**
- ROM `$12EF26 + id*512`: 16 columns x 32 rows, column-major, 1 byte per texel.
- Each byte is a 4-bit colour index repeated in both nibbles. Index 0 is transparent (the sky shows through).

**Game frame buffer**
- `$FF3926`, 10,240 bytes: 32 tile columns of `$140` bytes, 80 rows x 4 bytes (8 px, 4bpp).

## Files

- `colroutines.py`: extracts the per-height column routines (row lists + shade levels) from the ROM.
- `ztrender.py`: renderer. `render()` uses per-column rays; `render_game()` uses the original's 65-ray visibility.
- `colcmp.py`: decodes per-column traces of the game's wall loop (`0xCE3C`: height, texture pointers).
- `cmpview.py`: game vs native comparison image.
- `ztsprites.py`: sprite drawing (native exact and high-res) and the floor/ceiling background.
- `showcase.py` / `showcase2.py`: write original vs native vs 1280x720 images (walls only / full scene).
- `samples/`: RAM dumps taken at frame submit (`$FF0002` = 2), screenshots, and wall-loop traces.

The RAM dumps and traces came from Genesis Plus GX with a profiler build (register trace at a PC). They
contain game data, so `samples/` and `images/` are not in the repository; the scripts expect a 64 KB
big-endian work RAM dump taken at frame submit (`$FF0002` = 2) and a screenshot of the same frame.
