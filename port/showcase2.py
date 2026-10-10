#!/usr/bin/env python3
"""Full-scene PoC: original 3D view vs native exact vs 1280x720 widescreen (walls, floor gradient, sprites)."""
import sys, json, math, numpy as np
from PIL import Image, ImageDraw
from ztrender import State, render, game_fb
from ztsprites import draw_native, draw_hires, background_native
from showcase import palette

def cmds_of(t):
    out = []
    for r in t:
        x = r[1] & 0xFFFF; x = x - 0x10000 if x >= 0x8000 else x
        out.append((r[8] & 0xFFFFFF, r[9] & 0xFFFFFF, r[10] & 0xFFFFFF, x, r[5] & 0xFFFF))
    return out

def native(st, ram, cmds):
    walls, mask = render(st, k=64, affine="game")
    img = np.where(mask, walls, background_native(ram))
    zb = np.zeros(128)
    for c, i in render.info.items(): zb[c] = i[0]
    for cmd in cmds: draw_native(img, zb, ram, cmd)
    return img

def hires_full(st, ram, cmds, W=1280, H=720, hfov=106.0):
    half = math.tan(math.radians(hfov / 2)); focal = (W / 2) / half; k = focal / 2
    walls, mask = render(st, cols=W, colw=1, rows=H, fov_deg=hfov, k=k, affine=False, limit=False)
    wdist = np.full(W, 1e9)
    for c, i in render.info.items(): wdist[c] = i[7]
    # background: the game's 80-row gradient, rows mapped from the horizon outward by the same scale
    bg80 = background_native(ram); f = k / 64.0
    bg = np.zeros((H, W), np.uint8)
    for y in range(H):
        r = int(round(40 + (y + 0.5 - H / 2) / f)); r = max(0, min(79, r))
        bg[y, 0::2] = bg80[r, 0]; bg[y, 1::2] = bg80[r, 1]
    img = np.where(mask, walls, bg)
    for cmd in sorted(cmds, key=lambda c: c[4]): draw_hires(img, wdist, st, ram, cmd, W, H, focal)
    return img

if __name__ == "__main__":
    out = sys.argv[1]; files = sys.argv[2:]
    P = palette([(open(f, 'rb').read(), f.replace('.bin', '.png')) for f in files])
    for n, f in enumerate(files):
        ram = open(f, 'rb').read(); st = State(ram); cmds = cmds_of(json.load(open(f.replace('.bin', '.json'))))
        g = game_fb(ram); nat = native(st, ram, cmds); hi = hires_full(st, ram, cmds)
        canvas = Image.new('RGB', (1280, 720 + 220 + 20), (30, 30, 30))
        canvas.paste(Image.fromarray(P[g]).resize((640, 200), Image.NEAREST), (0, 18))
        canvas.paste(Image.fromarray(P[nat]).resize((640, 200), Image.NEAREST), (640, 18))
        canvas.paste(Image.fromarray(P[hi]), (0, 240))
        d = ImageDraw.Draw(canvas)
        d.text((4, 3), "original 3D view (game frame buffer, 256x80)", fill=(255, 255, 255))
        d.text((644, 3), "native exact re-render (%.1f%% identical)" % (100 * (nat == g).mean()), fill=(255, 255, 255))
        d.text((4, 224), "native 1280x720, 106 deg FOV: walls, floor gradient, enemies from world positions", fill=(255, 255, 255))
        canvas.save(f"{out}_{n}.png")
    print("ok")
