#!/usr/bin/env python3
"""Zero Tolerance walls-only native renderer (proof of concept).

Reads game state from a 64 KB RAM image ($FF0000-$FFFFFF, big-endian) and assets from the ROM,
and renders the walls at any resolution / field of view. With the native settings
(128 columns x 2 px, 80 rows, 90 degree FOV) it should reproduce the game's own frame buffer.
"""
import struct, math
import numpy as np

import os
ROM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Zero Tolerance (USA, Europe) (Rev A).gen")
TEX_BASE = 0x12EF26          # 16x32 texels, column-major, 1 byte (doubled 4-bit index) per texel
rom = open(ROM_PATH, "rb").read()

def tex_raw(tid):
    return np.frombuffer(rom, np.uint8, 512, TEX_BASE + tid * 512).reshape(16, 32)   # [u][v] raw bytes

_COLROUT = {}
def col_routines(table):
    if table not in _COLROUT:
        from colroutines import extract
        _COLROUT[table] = extract(table)
    return _COLROUT[table]

def tex(tid):
    d = np.frombuffer(rom, np.uint8, 512, TEX_BASE + tid * 512)
    return (d.reshape(16, 32) & 0x0F)        # [u][v] colour index

# cell type -> special handler ($9226 dispatch table at $923A); $9458 means "blocks like a wall"
_HANDLERS = []
for _i in range(256):
    _v = struct.unpack(">I", rom[0x923A + _i * 4:0x923E + _i * 4])[0]
    if not (0x9000 <= _v < 0xB100): break
    _HANDLERS.append(_v)
SOLID_TYPES = {1} | {t for t, h in enumerate(_HANDLERS) if t >= 6 and h in (0x9458, 0x9862)}
# doors: thin wall through the cell middle, drawn with strip list $12 ($FF64E6); rays pass, but
# the door is opaque and nearer, so for display it ends the ray. 6: east-west at y+0.5, 7: north-south at x+0.5
DOOR_TYPES = {t: ("ew" if h == 0xAF5E else "ns") for t, h in enumerate(_HANDLERS) if h in (0xAF5E, 0xAD8C)}
DOOR_STRIPS = 0x12
# diagonal cells: type -> (face word, u=0 end, u=1 end) in cell-local corners
DIAG = {4: (0, (1, 1), (0, 0)), 2: (3, (0, 0), (1, 1)), 3: (0, (1, 0), (0, 1)), 5: (3, (0, 1), (1, 0))}

class State:
    def __init__(self, ram):
        self.ram = ram
        w = lambda a: struct.unpack(">h", ram[a - 0xFF0000:a - 0xFF0000 + 2])[0]
        uw = lambda a: struct.unpack(">H", ram[a - 0xFF0000:a - 0xFF0000 + 2])[0]
        l = lambda a: struct.unpack(">I", ram[a - 0xFF0000:a - 0xFF0000 + 4])[0]
        self.x, self.y = uw(0xFF0DEC), uw(0xFF0DEE)       # 8.8, 256 units per cell
        self.angle = uw(0xFF0E04) & 511
        self.dx, self.dy = w(0xFF0E00), w(0xFF0E02)        # length 256
        self.horizon = w(0xFF0E1A)
        self.h2 = w(0xFF117C)
        self.radius = w(0xFF0EB4)                           # cells drawn within this square radius
        self.routines = l(0xFF0EAA)                         # $4392 (distance-shaded) or $4436
        self.shades = [np.frombuffer(rom, np.uint8, 256, l(0xFF0E8A + i * 4)) for i in range(8)]
        mp = l(0xFF1024) - 0xFF0000
        self.map = np.frombuffer(ram, np.uint8, 1024, mp).reshape(32, 32)   # [y][x]
        self.ctype = np.frombuffer(ram, np.uint8, 256, 0x7BC6)
        # per cell: 4 face words (0 north, 1 west, 2 east, 3 south); each selects a strip list at
        # $FF63C6 + id*16: 4 strips across the face, each (top texture, bottom texture)
        self.faces = [struct.unpack(">4H", ram[0x73C6 + c * 8:0x73C6 + c * 8 + 8]) for c in range(256)]
        self.strips = lambda fid: [struct.unpack(">2H", ram[0x63C6 + fid * 16 + i * 4:0x63C6 + fid * 16 + i * 4 + 4]) for i in range(4)]

def _s16(v): v &= 0xFFFF; return v - 0x10000 if v & 0x8000 else v
def _s32(v): v &= 0xFFFFFFFF; return v - 0x100000000 if v & 0x80000000 else v
def _divs(a, b):
    """68000 DIVS.W: 32-bit / low 16 bits of b, quotient truncated toward zero; None on overflow."""
    a = _s32(a); b = _s16(b)
    if b == 0: return None
    q = abs(a) // abs(b); q = q if (a >= 0) == (b >= 0) else -q
    return q if -32768 <= q <= 32767 else None

def game_face(st, ax, ay, bx, by):
    """The original's integer face projection and clipping ($C9A8/$CA04/$CA4C-$CCDC, $CD5E).
    Ends in world units (256 per cell), a = texture u 0. Returns (x0, x1, iz0, d1, u0, du) or None."""
    cx = st.x - (st.dx >> 3); cy = st.y - (st.dy >> 3)
    def proj(x, y):
        rx = _s16(x - cx); ry = _s16(y - cy)
        return _s32(rx * st.dx + ry * st.dy), _s32(ry * st.dx - rx * st.dy)      # D, L
    Da, La = proj(ax, ay); Db, Lb = proj(bx, by)
    def xz(D, L):
        q = _s16(D >> 6)
        if q == 0: return None
        x = _divs(L, q); iz = _divs(0x10000, q)
        return None if x is None or iz is None else (_s16(x + 0x40), iz)
    def clip_D(t): return ((Da + (_s16((Db - Da) >> 3) * _s16(t) >> 5)) >> 6)
    def iz_at(t):
        q = _s16(clip_D(t)); 
        return None if q == 0 else _divs(0x10000, q)
    a_out = -La >= Da; b_out = Lb >= Db
    if not a_out and not b_out:
        A = xz(Da, La); B = xz(Db, Lb)
        if A is None or B is None: return None
        (x0, iz0), (x1, iz1), u0, u1 = A, B, 0, 0xFF
    elif not a_out and b_out:              # right end clipped
        den = ((Da - La) - (Db - Lb)) >> 8
        t = _divs(Da - La, den) if _s16(den) else None
        A = xz(Da, La)
        if t is None or A is None: return None
        iz1 = iz_at(t)
        if iz1 is None: return None
        (x0, iz0), x1, u0, u1 = A, 0x7F, 0, t
    elif a_out and not b_out:              # left end clipped
        den = ((Da + La) - (Db + Lb)) >> 8
        t = _divs(Da + La, den) if _s16(den) else None
        B = xz(Db, Lb)
        if t is None or B is None: return None
        iz0 = iz_at(t)
        if iz0 is None: return None
        x0, (x1, iz1), u0, u1 = 0, B, t, 0xFF
    else:                                  # both ends clipped
        den6 = ((Da + La) - (Db + Lb)) >> 8; den5 = ((Da - La) - (Db - Lb)) >> 8
        t6 = _divs(Da + La, den6) if _s16(den6) else None
        t5 = _divs(Da - La, den5) if _s16(den5) else None
        if t6 is None or t5 is None: return None
        iz0, iz1 = iz_at(t6), iz_at(t5)
        if iz0 is None or iz1 is None: return None
        x0, x1, u0, u1 = 0, 0x7F, t6, t5
    if iz0 < 0 or iz1 < 0 or x1 < 0: return None
    x0 = max(0, x0)
    if x0 >= 0x80: return None
    x1 = min(x1, 0x7F)
    n = x1 - x0 + 1
    if n <= 0: return None
    d1 = _divs((iz1 << 8) - (iz0 << 8), n)
    du = _divs((u1 - u0) << 6, n)
    if d1 is None or du is None: return None
    return x0, x1, iz0, d1, u0, du

def face_u(ends, px, py, dirx, diry, c, cols, affine):
    """Texture u (0..1) for screen column c on a face. Affine: linear in screen x between the
    (frustum-clipped) projected end points, as the original does; else perspective-correct."""
    (ax, ay), (bx, by) = ends
    def cam(x, y):
        rx, ry = x - px, y - py
        return rx * dirx + ry * diry, ry * dirx - rx * diry      # depth, lateral (lateral>0 = right)
    da, la = cam(ax, ay); db, lb = cam(bx, by)
    half = render.half
    ua, ub = 0.0, 1.0
    # clip against left (lat = -depth*half) and right (lat = depth*half) planes
    for sgn in (-1, 1):
        fa = la * sgn - da * half; fb = lb * sgn - db * half       # >0 means outside
        if fa > 0 and fb > 0: return None
        if fa > 0 or fb > 0:
            t = fa / (fa - fb)
            dc, lc, uc = da + (db - da) * t, la + (lb - la) * t, ua + (ub - ua) * t
            if fa > 0: da, la, ua = dc, lc, uc
            else: db, lb, ub = dc, lc, uc
    if da <= 0 or db <= 0: return None
    xa = (la / (da * half) + 1) * cols / 2; xb = (lb / (db * half) + 1) * cols / 2
    if abs(xb - xa) < 1e-6: return ua
    t = (c + 0.5 - xa) / (xb - xa)
    if affine == "game":   # the original's integer stepping: whole-column ends, step taken before column 0
        x0 = max(0, int(xa)); x1 = min(cols - 1, int(xb)); n = x1 - x0 + 1
        if n <= 0: return None
        u0 = int(ua * 256); u1 = int(ub * 256)
        step = int(((u1 - u0) << 6) / n)
        acc = (u0 << 6) + step * (c - x0 + 1)
        return min(acc / 16384.0, 0.99999)
    if not affine:   # perspective-correct: interpolate u/z and 1/z
        iza, izb = 1 / da, 1 / db
        return ((ua * iza) + t * (ub * izb - ua * iza)) / (iza + t * (izb - iza))
    return ua + t * (ub - ua)

def render(st, cols=128, colw=2, rows=80, fov_deg=90.0, k=None, face_order=(0, 1, 2, 3), flip=(False,) * 4,
           pullback=32, vscale=1.0, limit=True, affine=True, shade=True):
    """Returns (index image [rows][cols*colw], wall mask)."""
    k = k if k is not None else 80.0          # wall height in rows at distance 1 cell (fitted)
    W = cols * colw
    img = np.zeros((rows, W), np.uint8)
    info = {}
    mask = np.zeros((rows, W), bool)
    # camera (game pulls back by dir/8 while rendering)
    px = (st.x - st.dx * pullback / 256.0) / 256.0     # game pulls the camera back by dir/8 (32 units)
    py = (st.y - st.dy * pullback / 256.0) / 256.0
    dirx, diry = st.dx / 256.0, st.dy / 256.0
    half = math.tan(math.radians(fov_deg / 2)); render.half = half
    planex, planey = -diry * half, dirx * half       # screen right
    center = rows / 2
    ccx, ccy = st.x >> 8, st.y >> 8
    for c in range(cols):
        camx = (2 * (c + 0.5) / cols) - 1
        rx, ry = dirx + planex * camx, diry + planey * camx
        mx, my = int(px), int(py)
        ddx = abs(1 / rx) if rx else 1e30
        ddy = abs(1 / ry) if ry else 1e30
        if rx > 0: stepx, sdx = 1, (mx + 1 - px) * ddx
        else:      stepx, sdx = -1, (px - mx) * ddx
        if ry > 0: stepy, sdy = 1, (my + 1 - py) * ddy
        else:      stepy, sdy = -1, (py - my) * ddy
        hit = None; diag = None
        for _ in range(64):
            if sdx < sdy:
                sdx += ddx; mx += stepx; side = 0
            else:
                sdy += ddy; my += stepy; side = 1
            if not (0 <= mx < 32 and 0 <= my < 32): break
            if limit and (abs(mx - ccx) > st.radius or abs(my - ccy) > st.radius): break
            cell = st.map[my][mx]; ct = st.ctype[cell]
            if ct in SOLID_TYPES:
                hit = cell; break
            if ct in DOOR_TYPES:
                if DOOR_TYPES[ct] == "ew": ax, ay, bx, by = mx, my + 0.5, mx + 1, my + 0.5
                else:                      ax, ay, bx, by = mx + 0.5, my, mx + 0.5, my + 1
                if (bx - ax) * (py - ay) - (by - ay) * (px - ax) < 0:    # u=0 on the viewer's left
                    ax, ay, bx, by = bx, by, ax, ay
                den = rx * (by - ay) - ry * (bx - ax)
                if abs(den) > 1e-12:
                    t = ((ax - px) * (by - ay) - (ay - py) * (bx - ax)) / den
                    tin = (sdx - ddx) if side == 0 else (sdy - ddy)
                    if tin - 1e-9 <= t <= min(sdx, sdy) + 1e-9:
                        hit = cell; diag = ("door", (ax, ay), (bx, by), t); break
                continue
            if ct in DIAG:
                fw, (a0x, a0y), (b0x, b0y) = DIAG[ct]
                ax, ay, bx, by = mx + a0x, my + a0y, mx + b0x, my + b0y
                tin = (sdx - ddx) if side == 0 else (sdy - ddy)          # ray param at cell entry
                ex, ey = px + rx * tin, py + ry * tin
                # open side: cross(b-a, p-a) > 0 (viewer's side for the u convention)
                if (bx - ax) * (ey - ay) - (by - ay) * (ex - ax) < -1e-9:   # entered through the solid half
                    hit = cell; break
                # intersect ray with the diagonal
                den = rx * (by - ay) - ry * (bx - ax)
                if abs(den) > 1e-12:
                    t = ((ax - px) * (by - ay) - (ay - py) * (bx - ax)) / den
                    tout = min(sdx, sdy)
                    if tin - 1e-9 <= t <= tout + 1e-9:
                        hit = cell; diag = (fw, (ax, ay), (bx, by), t); break
        if hit is None: continue
        if diag:
            fw, ea, eb, dist = diag; face = fw; ends = (ea, eb)
        else:
            if side == 0:
                dist = sdx - ddx
                face = 1 if stepx > 0 else 2         # ray moving east hits the west face, etc.
            else:
                dist = sdy - ddy
                face = 0 if stepy > 0 else 3         # ray moving south hits the north face
            fx, fy = mx, my
            ends = {0: ((fx + 1, fy), (fx, fy)), 3: ((fx, fy + 1), (fx + 1, fy + 1)),
                    1: ((fx, fy), (fx, fy + 1)), 2: ((fx + 1, fy + 1), (fx + 1, fy))}[face]
        exact = None
        if affine == "game" and cols == 128 and colw == 2 and abs(fov_deg - 90) < 1e-9:
            (eax, eay), (ebx, eby) = ends
            gf = game_face(st, int(round(eax * 256)), int(round(eay * 256)), int(round(ebx * 256)), int(round(eby * 256)))
            if gf and gf[0] <= c <= gf[1]:
                x0, x1, iz0, d1, u0, du = gf; i = c - x0
                exact = ((iz0 << 8) + i * d1) >> 8, min(63, max(0, ((u0 << 6) + du * (i + 1)) >> 8))
        u = face_u(ends, px, py, dirx, diry, c, cols, affine)
        if u is None and exact is None: continue
        if exact: u = (exact[1] + 0.5) / 64
        if face == "door":
            strips = st.strips(DOOR_STRIPS); face = 0
        else:
            if flip[face]: u = 1 - u
            strips = st.strips(st.faces[hit][face])
        ucol = min(63, max(0, int(u * 64)))
        top, bot = strips[ucol // 16]
        tt, tb = tex(top), tex(bot)
        tu = ucol % 16
        h = k / max(dist, 1e-3) * vscale
        if exact: h = exact[0]
        info[c] = (h, top, tu, bot, tu, face, hit, dist, ucol)
        mid = center + h * st.horizon / 64.0 / 2
        if affine == "game" and rows == 80 and st.horizon == 0:
            # exact: the original's per-height column routines (row list + shade table), or for
            # walls taller than the view, its centre-out loop (unshaded)
            hr = tex_raw(top)[tu], tex_raw(bot)[tu]
            hi = int(h)
            if hi <= 80:
                hi &= ~1
                for r, (src, off, sh) in enumerate(col_routines(st.routines).get(hi, [])):
                    b = int(hr[src - 1][off]); b = int(st.shades[sh][b]) if sh is not None else b
                    yy = 40 - hi // 2 + r
                    img[yy, c * colw] = b >> 4; img[yy, c * colw + 1] = b & 15; mask[yy, c * colw:(c + 1) * colw] = True
            else:
                err, t = hi, 0
                for kk in range(40):
                    for yy, b in ((39 - kk, int(hr[0][31 - t])), (40 + kk, int(hr[1][t]))):
                        img[yy, c * colw] = b >> 4; img[yy, c * colw + 1] = b & 15; mask[yy, c * colw:(c + 1) * colw] = True
                    err -= 64
                    if err < 0: t = min(31, t + 1); err += hi
            continue
        y0, y1 = mid - h / 2, mid + h / 2
        # distance shading as the original: shade level of the equivalent native wall height, the
        # shade table's two nibbles mixed in a checker pattern
        sh = None
        if shade:
            hn = int(64.0 / max(dist, 1e-3)) & ~1
            if 2 <= hn <= 80:
                r = col_routines(st.routines).get(hn)
                if r: sh = r[0][2]
        rt, rb = tex_raw(top)[tu], tex_raw(bot)[tu]
        for yy in range(max(0, int(math.ceil(y0))), min(rows, int(math.ceil(y1)))):
            tv = min(63, int((yy - y0) / h * 64))
            b = int(rt[tv]) if tv < 32 else int(rb[tv - 32])
            if sh is not None: b = int(st.shades[sh][b])
            for xx in range(c * colw, (c + 1) * colw):
                img[yy, xx] = (b >> 4) if ((xx + yy) & 1) == 0 else (b & 15)
            mask[yy, c * colw:(c + 1) * colw] = True
    render.info = info
    return img, mask

def game_fb(ram):
    """The game's own 256x80 frame buffer as colour indices."""
    fb = ram[0x3926:0x3926 + 10240]
    out = np.zeros((80, 256), np.uint8)
    a = np.frombuffer(fb, np.uint8).reshape(32, 80, 4)       # [tile col][row][4 bytes]
    for c in range(32):
        for k in range(4):
            out[:, c * 8 + k * 2] = a[c, :, k] >> 4
            out[:, c * 8 + k * 2 + 1] = a[c, :, k] & 15
    return out

# ---------------------------------------------------------------------------
# "game" mode: the original's visibility method. 65 rays (every second entry of the
# ray-angle table) find the first solid cell; only faces of those cells are drawn,
# as projected segments with affine texture u and a per-column height buffer.
# ---------------------------------------------------------------------------
RAY_OFFS = [struct.unpack(">h", rom[0x9124 + i * 2:0x9126 + i * 2])[0] for i in range(129)]
DIRTAB = [struct.unpack(">hh", rom[0x8124 + a * 4:0x8128 + a * 4]) for a in range(512)]

def visible_cells(st, step=2, pullback=32):
    px = (st.x - st.dx * pullback / 256.0) / 256.0
    py = (st.y - st.dy * pullback / 256.0) / 256.0
    ccx, ccy = st.x >> 8, st.y >> 8
    cells = []
    for i in range(0, 129, step):
        dxr, dyr = DIRTAB[(st.angle + RAY_OFFS[i]) & 511]
        rx, ry = dxr / 256.0, dyr / 256.0
        mx, my = int(px), int(py)
        ddx = abs(1 / rx) if rx else 1e30; ddy = abs(1 / ry) if ry else 1e30
        stepx, sdx = (1, (mx + 1 - px) * ddx) if rx > 0 else (-1, (px - mx) * ddx)
        stepy, sdy = (1, (my + 1 - py) * ddy) if ry > 0 else (-1, (py - my) * ddy)
        for _ in range(64):
            if sdx < sdy: sdx += ddx; mx += stepx
            else: sdy += ddy; my += stepy
            if not (0 <= mx < 32 and 0 <= my < 32): break
            if abs(mx - ccx) > st.radius or abs(my - ccy) > st.radius: break
            if st.ctype[st.map[my][mx]] == 1:
                if (mx, my) not in cells: cells.append((mx, my))
                break
    return cells, px, py

def render_game(st, k=64, cols=128, colw=2, rows=80, pullback=32, step=2):
    img = np.zeros((rows, cols * colw), np.uint8); zbuf = np.zeros(cols)
    mask = np.zeros((rows, cols * colw), bool)
    info = {}
    cells, px, py = visible_cells(st, step, pullback)
    dirx, diry = st.dx / 256.0, st.dy / 256.0
    def cam(x, y):
        rx, ry = x - px, y - py
        return rx * dirx + ry * diry, ry * dirx - rx * diry
    for (mx, my) in cells:
        cell = st.map[my][mx]
        # faces whose outside is towards the camera: 0 north (py<my), 3 south, 1 west, 2 east
        faces = []
        if py < my: faces.append(0)
        if py > my + 1: faces.append(3)
        if px < mx: faces.append(1)
        if px > mx + 1: faces.append(2)
        for face in faces:
            (ax, ay), (bx, by) = {0: ((mx + 1, my), (mx, my)), 3: ((mx, my + 1), (mx + 1, my + 1)),
                                  1: ((mx, my), (mx, my + 1)), 2: ((mx + 1, my + 1), (mx + 1, my))}[face]
            da, la = cam(ax, ay); db, lb = cam(bx, by); ua, ub = 0.0, 1.0
            skip = False
            for sgn in (-1, 1):
                fa = la * sgn - da; fb = lb * sgn - db
                if fa > 0 and fb > 0: skip = True; break
                if fa > 0 or fb > 0:
                    t = fa / (fa - fb)
                    dc, lc, uc = da + (db - da) * t, la + (lb - la) * t, ua + (ub - ua) * t
                    if fa > 0: da, la, ua = dc, lc, uc
                    else: db, lb, ub = dc, lc, uc
            if skip or da <= 0 or db <= 0: continue
            xa = (la / da + 1) * cols / 2; xb = (lb / db + 1) * cols / 2
            if xb <= xa: continue
            strips = st.strips(st.faces[cell][face])
            for c in range(max(0, int(math.ceil(xa - 0.5))), min(cols, int(math.ceil(xb - 0.5)))):
                t = (c + 0.5 - xa) / (xb - xa)
                iz = 1 / da + t * (1 / db - 1 / da)
                h = k * iz
                if h < zbuf[c]: continue
                zbuf[c] = h
                u = ua + t * (ub - ua)
                ucol = min(63, max(0, int(u * 64)))
                top, bot = strips[ucol // 16]; tt, tb = tex(top), tex(bot); tu = ucol % 16
                info[c] = (h, top, tu, bot, tu, face, cell, 1 / iz, ucol)
                y0 = rows / 2 - h / 2
                for yy in range(max(0, int(math.ceil(y0))), min(rows, int(math.ceil(y0 + h)))):
                    tv = min(63, int((yy - y0) / h * 64))
                    img[yy, c * colw:(c + 1) * colw] = tt[tu][tv] if tv < 32 else tb[tu][tv - 32]
                    mask[yy, c * colw:(c + 1) * colw] = True
    render_game.info = info
    return img, mask
