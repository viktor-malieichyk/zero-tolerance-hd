#!/usr/bin/env python3
# usage: hud_concept.py <native 320x224 gameplay screenshot> <1280x720 HD frame without HUD> <out.png>
"""HUD concept: the original HUD's own pieces (map, weapons bar, portrait card, the two counters cut down to
their digits) in three new console modules drawn in the original console's palette. Drawn on a 640x360
canvas in game pixels, shown 2x over a 1280x720 HD frame."""
from PIL import Image, ImageDraw
import sys
nat = Image.open(sys.argv[1]).convert("RGB"); bg = Image.open(sys.argv[2]).convert("RGB"); out = sys.argv[3]

BLACK, PLATE, SHADOW, MID, EDGE, BRIGHT, GREY, YEL, ORANGE, RUST = (0,0,0), (0,68,32), (0,32,32), (32,100,64), (96,136,136), (168,168,200), (64,68,64), (232,236,32), (200,100,32), (96,32,0)

W, H = 640, 360
hud = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(hud)

FONT = {  # 5x7
 "E": ["11111","10000","10000","11110","10000","10000","11111"], "N": ["10001","11001","10101","10011","10001","10001","10001"],
 "M": ["10001","11011","10101","10101","10001","10001","10001"], "I": ["11111","00100","00100","00100","00100","00100","11111"],
 "S": ["01111","10000","10000","01110","00001","00001","11110"], "H": ["10001","10001","10001","11111","10001","10001","10001"],
 "A": ["01110","10001","10001","11111","10001","10001","10001"], "L": ["10000","10000","10000","10000","10000","10000","11111"],
 "T": ["11111","00100","00100","00100","00100","00100","00100"], "P": ["11110","10001","10001","11110","10000","10000","10000"],
 "O": ["01110","10001","10001","10001","10001","10001","01110"], "R": ["11110","10001","10001","11110","10100","10010","10001"],
 "C": ["01111","10000","10000","10000","10000","10000","01111"], " ": ["00000"] * 7,
}
def text(x, y, s, c):
    for ch in s:
        for r, row in enumerate(FONT[ch]):
            for k, b in enumerate(row):
                if b == "1": d.point((x + k, y + r), c)
        x += 6
def text_w(s): return len(s) * 6 - 1

def plate(x, y, w, h, cut=(6, 6, 0, 0)):
    """console plate: chamfered corners (top-left, top-right, bottom-right, bottom-left), bevel, rivets"""
    tl, tr, br, bl = cut
    pts = [(x + tl, y), (x + w - 1 - tr, y), (x + w - 1, y + tr), (x + w - 1, y + h - 1 - br), (x + w - 1 - br, y + h - 1),
           (x + bl, y + h - 1), (x, y + h - 1 - bl), (x, y + tl)]
    d.polygon(pts, fill=PLATE, outline=BLACK)
    # bevel: light top and left inside the outline, dark bottom and right
    d.line([(x + 1, y + h - 2 - bl), (x + 1, y + tl + 1), (x + tl + 1, y + 1), (x + w - 2 - tr, y + 1)], fill=EDGE)
    d.line([(x + w - 2 - tr, y + 1), (x + w - 2, y + tr + 1)], fill=EDGE)
    d.line([(x + w - 2, y + tr + 2), (x + w - 2, y + h - 2 - br), (x + w - 2 - br, y + h - 2), (x + bl + 1, y + h - 2)], fill=SHADOW)
    # the original's dithered texture on the plate face
    for yy in range(y + 3, y + h - 3, 2):
        for xx in range(x + 3 + (yy // 2) % 2 * 2, x + w - 3, 4):
            if hud.getpixel((xx, yy))[:3] == PLATE: d.point((xx, yy), MID)
def rivet(x, y): d.point((x, y), BRIGHT); d.point((x + 1, y + 1), SHADOW); d.point((x + 1, y), EDGE); d.point((x, y + 1), EDGE)

def frame_in(x, y, w, h):
    """recessed window for a piece of the original HUD: dark rim top-left, light rim bottom-right"""
    d.rectangle([x - 2, y - 2, x + w + 1, y + h + 1], fill=BLACK)
    d.line([(x - 2, y + h + 1), (x + w + 1, y + h + 1), (x + w + 1, y - 2)], fill=EDGE)
    d.line([(x - 2, y + h + 1), (x - 2, y - 2), (x + w + 1, y - 2)], fill=SHADOW)

def paste_nat(box, x, y, s=1):
    piece = nat.crop(box)
    if s != 1: piece = piece.resize((piece.width * s, piece.height * s), Image.NEAREST)
    hud.paste(piece, (x, y))

def digits(box):
    """the counter's black inside cut down to its digits (bounding box of the yellow pixels)"""
    x0, y0, x1, y1 = box; xs, ys = [], []
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            p = nat.getpixel((xx, yy))
            if p[0] > 150 and p[2] < 100: xs.append(xx); ys.append(yy)
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)

def counter_tab(x, y, w, label, dbox, cut):
    """tab on top of a module: label, then the digits 2x on black"""
    plate(x, y, w, 44, cut)
    text(x + (w - text_w(label)) // 2, y + 5, label, EDGE)
    ix, iy, iw, ih = x + 6, y + 15, w - 12, 24
    frame_in(ix, iy, iw, ih)
    dw, dh = (dbox[2] - dbox[0]) * 2, (dbox[3] - dbox[1]) * 2
    paste_nat(dbox, ix + (iw - dw) // 2, iy + (ih - dh) // 2, 2)

M = 4
# ---- base rail joining the three modules
plate(100, 340, 440, 16, (0, 0, 0, 0))
d.line([(102, 347), (537, 347)], fill=SHADOW); d.line([(102, 348), (537, 348)], fill=EDGE)

# ---- left: map, with the enemy counter on a tab above it, joined by the original's orange cable
LX, LY, LW, LH = M, 252, 106, 104
counter_tab(LX, LY - 40, 70, "ENEMIES", digits((3, 71, 29, 81)), (4, 8, 0, 0))
plate(LX, LY, LW, LH, (0, 10, 0, 0))
frame_in(LX + 7, LY + 7, 92, 92); paste_nat((100, 130, 192, 222), LX + 7, LY + 7)
for cx in (LX + 4, LX + LW - 6): rivet(cx, LY + LH - 6)
# cable: out of the tab's right side, along and down into the map frame's top
for i, c in enumerate((RUST, ORANGE, ORANGE)):
    d.line([(LX + 70, LY - 20 + i), (LX + 82 + i, LY - 20 + i), (LX + 82 + i, LY + 4)], fill=c)
d.rectangle([LX + 80, LY + 2, LX + 87, LY + 5], fill=GREY, outline=BLACK)

# ---- right: portrait card, with the health counter on a tab above it
RW, RH = 142, 104; RX, RY = W - M - RW, 252
counter_tab(RX + RW - 70, RY - 40, 70, "HEALTH", digits((295, 71, 313, 81)), (8, 4, 0, 0))
plate(RX, RY, RW, RH, (10, 0, 0, 0))
frame_in(RX + 8, RY + 7, 126, 92); paste_nat((192, 130, 318, 222), RX + 8, RY + 7)
for cx in (RX + 4, RX + RW - 6): rivet(cx, RY + RH - 6)

# ---- middle: the weapons bar in a console with the original's chamfered top corners
BW, BH = 240, 36; BX, BY = (W - BW) // 2, 318
plate(BX - 10, BY - 6, BW + 20, BH + 12 + 2, (10, 10, 0, 0))
frame_in(BX, BY, BW, BH); paste_nat((40, 0, 280, 36), BX, BY)
for cx in (BX - 7, BX + BW + 5): rivet(cx, BY + BH + 3)
# bigger ammo counts over each slot's bottom-left (as the HD renderer draws them: 3x on a black plate)
for bx_ in (0, 46, 102, 158, 205):
    tx0, ty0 = 40 + bx_ + 1, 29
    pts = [(x, y) for y in range(7) for x in range(30) if (lambda p: p[0] > 176 and p[1] > 176 and p[2] < 96)(nat.getpixel((tx0 + x, ty0 + y)))]
    if not pts: continue
    x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts); y1 = max(p[1] for p in pts)
    g = 3; px0 = BX + bx_ + 2; py1 = BY + 35
    d.rectangle([px0 - 1, py1 - (y1 + 1) * g - 1, px0 + (x1 - x0 + 1) * g, py1], fill=BLACK)
    for x, y in pts:
        if x <= x1: d.rectangle([px0 + (x - x0) * g, py1 - (y1 + 1 - y) * g, px0 + (x - x0) * g + g - 1, py1 - (y1 - y) * g - 1], fill=YEL)

big = hud.resize((W * 2, H * 2), Image.NEAREST)
res = bg.copy(); res.paste(big, (0, 0), big)
res.save(out)
big.save(out.replace(".png", "_layer.png"))
print("wrote", out)
