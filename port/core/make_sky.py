#!/usr/bin/env python3
"""Build a full sky panorama PNG for the Zero Tolerance HD renderer.

    python3 make_sky.py <rom> <dump> <map address> <out.png> [--above N] [--below N] [--seed S]

<dump>.vram / <dump>.cram: the VDP's VRAM (64 KB) and CRAM (128 bytes, big-endian words in Genesis Plus
GX's 9-bit bbbgggrrr form) taken during gameplay of a level that uses this sky. <map address>: the
128 x 16 tile map the game streams the sky from (pointer at $FF271E: $153106, or $1553E6 for the planet).

The PNG is 1024 px wide (360 degrees, 2 px per angle unit) and indexed: pixel values are CRAM indices
(palette * 16 + colour, 0 = backdrop), so the game's palette fades still apply. The original art rows are
kept as they are: PNG row "zt_art_row" (text chunk) is sky map row "zt_map_row". Added:
- the planet, which the art cuts off at its top, completed: a circle is fitted to its visible rim and the
  missing rows are the reflection of the lower part about the centre row (same limb shading), blended to
  the art's brightness at the cut;
- stars above and below the art, using the art's own star shapes at the art's density.
The file can be edited (keep it indexed with the same palette, or save as RGB to use fixed colours).
"""
import sys, struct, argparse, random
import numpy as np
from PIL import Image, PngImagePlugin

ap = argparse.ArgumentParser()
ap.add_argument("rom"); ap.add_argument("dump"); ap.add_argument("map"); ap.add_argument("out")
ap.add_argument("--above", type=int, default=128); ap.add_argument("--below", type=int, default=128)
ap.add_argument("--seed", type=int, default=1)
a = ap.parse_args()
rom = open(a.rom, "rb").read(); vram = open(a.dump + ".vram", "rb").read(); cram = open(a.dump + ".cram", "rb").read()
mp = int(a.map, 16)

# ---- the original art: 128 x 16 tiles from the map
def entry(ty, tx): return struct.unpack(">H", rom[mp + ty * 256 + tx * 2: mp + ty * 256 + tx * 2 + 2])[0]
def tile_px(e, x, y):
    t = e & 0x7FF
    if e & 0x800: x = 7 - x
    if e & 0x1000: y = 7 - y
    b = vram[t * 32 + y * 4 + (x >> 1)]
    c = (b & 15) if x & 1 else (b >> 4)
    return ((e >> 13) & 3) * 16 + c if c else 0
def lit(e): return sum(1 for i in range(64) if tile_px(e, i & 7, i >> 3))
art = np.zeros((128, 1024), np.uint8)
for ty in range(16):
    for tx in range(128):
        e = entry(ty, tx)
        for y in range(8):
            for x in range(8): art[ty * 8 + y, tx * 8 + x] = tile_px(e, x, y)
rows = np.nonzero(art.any(1))[0]; art = art[rows.min(): rows.max() + 1]; AH = art.shape[0]
print(f"art: {AH} rows")

# ---- planet columns and colours: tiles with 40+ of 64 pixels lit; planet colours never appear elsewhere
dense = sorted({tx for ty in range(AH // 8) for tx in range(128) if lit(entry(ty, tx)) >= 40})
pcols = set()
for tx in dense:
    for k in range(-2, 3): pcols.add((tx + k) % 128)
star_mask_cols = np.array([(x // 8) not in pcols for x in range(1024)])
star_colours = set(art[:, star_mask_cols].ravel().tolist()) - {0}
dense_colours = set()
for tx in dense:
    for ty in range(AH // 8):
        if lit(entry(ty, tx)) >= 40: dense_colours |= set(art[ty * 8: ty * 8 + 8, tx * 8: tx * 8 + 8].ravel().tolist())
planet_colours = sorted(dense_colours - star_colours - {0})
print("planet colours", planet_colours, "star colours", sorted(star_colours))

def rgb(i):
    w = struct.unpack(">H", cram[i * 2: i * 2 + 2])[0]
    return ((w & 7) * 255 // 7, ((w >> 3) & 7) * 255 // 7, ((w >> 6) & 7) * 255 // 7)

H = a.above + AH + a.below
out = np.zeros((H, 1024), np.uint8)
out[a.above: a.above + AH] = art

# ---- complete the planet
if planet_colours and dense:
    lum = lambda c: sum(v * k for v, k in zip(rgb(c), (30, 59, 11)))
    ramp = sorted(planet_colours, key=lum); level = {c: i for i, c in enumerate(ramp)}
    m = np.isin(art, planet_colours)
    xs0 = (min(dense) - 3) * 8; W = (max(dense) - min(dense) + 7) * 8       # planet window (no wrap handling needed here)
    pts = []
    for y in range(3, AH):
        r_ = np.nonzero(m[y, xs0: xs0 + W])[0]
        if len(r_) > 2: pts += [(r_.min(), y + .5), (r_.max() + 1, y + .5)]
    for x in range(W):
        c_ = np.nonzero(m[:, xs0 + x])[0]
        if len(c_) and c_.max() < AH - 2: pts.append((x + .5, c_.max() + 1))
    P = np.array(pts, float)
    A = np.c_[2 * P[:, 0], 2 * P[:, 1], np.ones(len(P))]
    cx, cy, c0 = np.linalg.lstsq(A, (P ** 2).sum(1), rcond=None)[0]; r = np.sqrt(c0 + cx * cx + cy * cy)
    print(f"planet circle: centre ({xs0 + cx:.1f}, {cy:.1f}) radius {r:.1f}; top at art row {cy - r:.1f}")
    # the fit's centre is pulled sideways by the ragged shadow edge; the widest art row gives the true one
    widths = [(len(np.nonzero(m[y])[0]), y) for y in range(AH)]
    wy = max(widths)[1]; wr = np.nonzero(m[wy])[0]
    wcx = (wr.min() + wr.max() + 1) / 2.0; wrad = (wr.max() + 1 - wr.min()) / 2.0
    print(f"widest art row {wy}: x {wr.min()}-{wr.max()}, centre {wcx}, radius {wrad}")
    if cy - wrad < -1:
        top = int(np.floor(cy - wrad)) - 1
        assert -top <= a.above, "not enough rows above the art for the planet"
        for x in range(int(wcx - wrad) - 1, int(wcx + wrad) + 2):
            ys = [int(round(2 * cy - y - 1)) for y in range(3)]
            av = [level[art[y, x]] for y in range(3) if m[y, x]]
            sv = [level[art[y2, x]] for y2 in ys if 0 <= y2 < AH and m[y2, x]]
            d = (np.mean(av) - np.mean(sv)) if av and sv else 0
            for y in range(top, 0):
                # the disc: centred on the widest art row, as wide as it (the fitted circle is pulled
                # sideways by the ragged shadow edge); shading from the mirrored art row, the darkest
                # planet colour where that row has a gap
                if (x + .5 - wcx) ** 2 + (y + .5 - cy) ** 2 > wrad * wrad: continue
                y2 = int(round(2 * cy - y - 1))
                lv = level[art[y2, x]] if (0 <= y2 < AH and m[y2, x]) else 0
                f = max(0.0, 1 - (-y - 1) / 14)
                v = lv + d * f + (((y & 1) * 2 + (x & 1) * 3) % 4 - 1.5) / 4
                out[a.above + y, x % 1024] = ramp[int(min(len(ramp) - 1, max(0, round(v))))]

# ---- stars above and below: the art's own star shapes (8-connected lit pixel groups) at its density
stars_img = art.copy(); stars_img[:, ~star_mask_cols] = 0
seen = np.zeros_like(stars_img, bool); shapes = []
for y0 in range(AH):
    for x0 in range(1024):
        if stars_img[y0, x0] and not seen[y0, x0]:
            st = [(y0, x0)]; seen[y0, x0] = True; comp = []
            while st:
                y, x = st.pop(); comp.append((y, x))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, (x + dx) % 1024
                        if 0 <= yy < AH and stars_img[yy, xx] and not seen[yy, xx]: seen[yy, xx] = True; st.append((yy, xx))
            ymin = min(p[0] for p in comp); xmin = min(p[1] for p in comp)
            shapes.append([(y - ymin, (x - xmin) % 1024, stars_img[y, x]) for y, x in comp])
area = AH * star_mask_cols.sum()
density = len(shapes) / area
print(f"{len(shapes)} star shapes in the art, {density * 10000:.1f} per 10000 px")
rng = random.Random(a.seed)
occupied = out != 0
for y0, y1 in ((0, a.above), (a.above + AH, H)):
    n = int(density * (y1 - y0) * 1024)
    placed = tries = 0
    while placed < n and tries < n * 50:
        tries += 1
        s = rng.choice(shapes); x = rng.randrange(1024); y = rng.randrange(y0, y1)
        hh = max(p[0] for p in s) + 1; ww = max(p[1] for p in s) + 1
        if y + hh > y1: continue
        if occupied[max(0, y - 2): y + hh + 2, [(x + i) % 1024 for i in range(-2, ww + 2)]].any(): continue
        for dy, dx, c in s: out[y + dy, (x + dx) % 1024] = c
        occupied[max(0, y - 2): y + hh + 2, [(x + i) % 1024 for i in range(-2, ww + 2)]] = True
        placed += 1
    print(f"rows {y0}-{y1}: {placed} stars")

im = Image.fromarray(out, "P")
pal = []
for i in range(64): pal += list(rgb(i))
im.putpalette(pal + [0] * (768 - len(pal)))
info = PngImagePlugin.PngInfo(); info.add_text("zt_art_row", str(a.above)); info.add_text("zt_map_row", str(rows.min()))
im.save(a.out, pnginfo=info, transparency=0)
print("wrote", a.out, im.size)
