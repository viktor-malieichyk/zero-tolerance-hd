"""Sprite (enemy/item) drawing from captured draw commands ($1BCB4: a0 object, a1 sub-frame record,
a2 piece graphics base, d1 screen column, d5 scale), following $1BCB4-$1BD70 and $EDA0."""
import struct, numpy as np
from ztrender import rom

def r8(a): return rom[a]
def ram_w(ram, a): return struct.unpack(">h", ram[a - 0xFF0000:a - 0xFF0000 + 2])[0]
def ram_l(ram, a): return struct.unpack(">I", ram[a - 0xFF0000:a - 0xFF0000 + 4])[0]

def piece_raw(base, pid):
    return np.frombuffer(rom, np.uint8, 512, base + pid * 512).reshape(16, 32)   # [u][v]

def sprite_shade(ram, scale):
    """None = unshaded; else ROM address of the shade table ($EDA0-$EDF4)."""
    lst = ram_l(ram, 0xFF1096)                    # -$6F6A
    if lst == 0xED50: return struct.unpack(">I", rom[0xED50:0xED54])[0]
    d3 = (scale >> 3) - 1
    if d3 < 0: return -1                          # too far: not drawn
    d3 = max(0, 4 - d3)
    return struct.unpack(">I", rom[lst + d3 * 4:lst + d3 * 4 + 4])[0]

def draw_native(img, zbuf, ram, cmd):
    """Draw one captured sprite command into a 128-column x 80-row native image (2 px per column)."""
    obj, rec, pbase, x, scale = cmd
    H = ram_w(ram, 0xFF0E1A); bob = ram_w(ram, 0xFF116E); z = ram_w(ram, obj + 0x24)
    y = (((H - bob - z) * scale) >> 6) + 0x28
    pw = (r8(rec + 2) * scale) >> 5; ph = (r8(rec + 3) * scale) >> 4
    cols, rows = r8(rec + 4), r8(rec + 5)
    if r8(rec) == 1: x -= (cols * pw) >> 1
    elif r8(rec): x -= cols * pw
    if r8(rec + 1) == 1: y -= (rows * ph) >> 1
    elif r8(rec + 1): y -= rows * ph
    shade = sprite_shade(ram, scale)
    if shade == -1: return
    table = np.frombuffer(rom, np.uint8, 256, shade) if shade else None
    for r in range(rows):
        for c in range(cols):
            attr = r8(rec + 6 + r * 4 + c); pid = r8(rec + 6 + 16 + r * 4 + c)
            px = piece_raw(pbase, pid)
            draw_piece(img, zbuf, px, x + c * pw, y + r * ph, pw, ph, scale, table, attr != 0)

def draw_piece(img, zbuf, px, x0, y0, w, h, scale, table, flip):
    if w <= 0 or h <= 0: return
    acc, u = 0, (15 if flip else 0)
    for i in range(w):
        col = x0 + i
        if 0 <= col < 128 and scale >= zbuf[col]:
            for j in range(h):
                yy = y0 + j
                if not 0 <= yy < 80: continue
                v = min(31, j * 32 // h)
                b = int(px[u][v])
                if b == 0: continue
                if table is not None: b = int(table[b])
                img[yy, col * 2] = b >> 4; img[yy, col * 2 + 1] = b & 15
        acc += 16
        while acc >= w and w > 0:
            acc -= w; u += -1 if flip else 1
        u = max(0, min(15, u))

def background_native(ram):
    """The floor/ceiling background the column routines copy (buffer at $FF6226: even columns +$50, odd +$00)."""
    buf = np.frombuffer(ram, np.uint8, 0xA0, 0x6226)
    out = np.zeros((80, 256), np.uint8)
    for c in range(128):
        col = buf[0x50:0xA0] if c % 2 == 0 else buf[0:0x50]
        out[:, c * 2] = col >> 4; out[:, c * 2 + 1] = col & 15
    return out

def draw_hires(img, wdist, st, ram, cmd, W, H, focal):
    """Draw a captured sprite command at high resolution from the object's world position.
    wdist[x] = wall distance (cells) per screen column, for depth testing."""
    obj, rec, pbase, _, _ = cmd
    k = focal / 2.0; f = k / 64.0                       # high-res pixels per native row
    px = (st.x - (st.dx >> 3)) / 256.0; py = (st.y - (st.dy >> 3)) / 256.0
    ox = ram_w(ram, obj + 0x20) / 256.0; oy = ram_w(ram, obj + 0x22) / 256.0
    if ox < 0: ox += 256
    if oy < 0: oy += 256
    dirx, diry = st.dx / 256.0, st.dy / 256.0
    rx, ry = ox - px, oy - py
    depth = rx * dirx + ry * diry; lat = ry * dirx - rx * diry
    if depth <= 0.05: return
    s = 64.0 / depth                                     # native scale (= wall height there)
    Hz = ram_w(ram, 0xFF0E1A); bob = ram_w(ram, 0xFF116E); z = ram_w(ram, obj + 0x24)
    xc = W / 2 + focal * lat / depth
    yc = H / 2 + ((Hz - bob - z) * s / 64.0) * f
    pw = r8(rec + 2) * s / 32 * 2 * f; ph = r8(rec + 3) * s / 16 * f
    cols, rows = r8(rec + 4), r8(rec + 5)
    x0 = xc - (cols * pw / 2 if r8(rec) == 1 else (cols * pw if r8(rec) else 0))
    y0 = yc - (rows * ph / 2 if r8(rec + 1) == 1 else (rows * ph if r8(rec + 1) else 0))
    shade = sprite_shade(ram, int(s))
    if shade == -1: shade = None
    table = np.frombuffer(rom, np.uint8, 256, shade) if shade else None
    for r in range(rows):
        for c in range(cols):
            attr = r8(rec + 6 + r * 4 + c); pid = r8(rec + 6 + 16 + r * 4 + c)
            pc = piece_raw(pbase, pid)
            ax, ay = x0 + c * pw, y0 + r * ph
            for xx in range(max(0, int(ax)), min(W, int(ax + pw))):
                if depth >= wdist[xx]: continue
                u = int((xx - ax) / pw * 16); u = 15 - u if attr else u
                u = max(0, min(15, u))
                for yy in range(max(0, int(ay)), min(H, int(ay + ph))):
                    b = int(pc[u][max(0, min(31, int((yy - ay) / ph * 32)))])
                    if b == 0: continue
                    if table is not None: b = int(table[b])
                    img[yy, xx] = (b >> 4) if ((xx + yy) & 1) == 0 else (b & 15)
