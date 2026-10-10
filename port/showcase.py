#!/usr/bin/env python3
"""Walls-only PoC showcase: original 256x80 view vs native re-render vs high-res / widescreen."""
import sys, math, numpy as np
from PIL import Image, ImageDraw
from ztrender import State, render, game_fb, tex, face_u

def palette(rams_shots):
    P = np.zeros((16, 3), np.uint8)
    for ram, shot in rams_shots:
        g = game_fb(ram); im = Image.open(shot).convert('RGB'); votes = {}
        for y in range(80):
            for x in range(256):
                votes.setdefault(g[y, x], {}).setdefault(im.getpixel((32 + x, 40 + y)), 0)
                votes[g[y, x]][im.getpixel((32 + x, 40 + y))] += 1
        for i, d in votes.items():
            if not P[i].any(): P[i] = max(d, key=d.get)
    return P

def floor_bands(ram, mask):
    """Floor colour index as a function of floor distance, sampled from the game's own frame."""
    g = game_fb(ram); bands = []
    for y in range(41, 80):
        row = [g[y, x] for x in range(256) if not mask[y, x] and g[y, x]]
        if row: bands.append((1.0 / (y + 0.5 - 40), max(set(row), key=row.count)))
    return bands   # (distance-ish, index), near first

def hires(st, W, H, hfov, ram):
    """Perspective-correct walls at W x H with horizontal FOV hfov, same proportions as the game."""
    half = math.tan(math.radians(hfov / 2)); focal = (W / 2) / half
    k = focal / 2                       # game: focal 128 px (64 columns x 2), wall scale 64
    cols = W
    img, mask = render(st, cols=cols, colw=1, rows=H, fov_deg=hfov, k=k, affine=False)
    # floor: map each row's distance to the game's floor colour bands (scaled to the game's geometry)
    _, m80 = render(st, k=64)
    bands = floor_bands(ram, m80)
    for y in range(H // 2 + 1, H):
        d = 1.0 / ((y + 0.5 - H / 2) / (k / 64.0))        # same distance measure as the 80-row view
        idx = min(bands, key=lambda b: abs(b[0] - d))[1] if bands else 0
        row = img[y]; row[~mask[y]] = idx
    return img

if __name__ == "__main__":
    files = sys.argv[1:]
    P = palette([(open(f, 'rb').read(), f.replace('.bin', '.png')) for f in files])
    panels = []
    for f in files:
        ram = open(f, 'rb').read(); st = State(ram)
        orig = P[game_fb(ram)]
        nat, _ = render(st, k=64)
        wide = hires(st, 1280, 720, 106.0, ram)
        panels.append((orig, P[nat], P[wide]))
    for n, (orig, nat, wide) in enumerate(panels):
        canvas = Image.new('RGB', (1280, 720 + 400 + 30), (30, 30, 30))
        canvas.paste(Image.fromarray(orig).resize((640, 200), Image.NEAREST), (0, 20))
        canvas.paste(Image.fromarray(nat).resize((640, 200), Image.NEAREST), (640, 20))
        canvas.paste(Image.fromarray(wide), (0, 430))
        d = ImageDraw.Draw(canvas)
        d.text((4, 4), "original game frame buffer 256x80 (2.5x)", fill=(255, 255, 255))
        d.text((644, 4), "native re-render from game RAM, original settings (2.5x)", fill=(255, 255, 255))
        d.text((4, 414), "native re-render 1280x720, 106 deg FOV, perspective-correct (walls + sampled floor only)", fill=(255, 255, 255))
        canvas.save(f"images/showcase_{n}.png")
    print("ok")
