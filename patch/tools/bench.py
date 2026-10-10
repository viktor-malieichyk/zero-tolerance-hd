#!/usr/bin/env python3
"""Minimal libretro frontend: run Zero Tolerance in Genesis Plus GX headless and
measure visible 3D-view fps, top-of-screen blanking, and save screenshots."""
import ctypes as C, sys, os, hashlib, argparse
ap = argparse.ArgumentParser()
ap.add_argument("rom"); ap.add_argument("--oc", default="100"); ap.add_argument("--region", default="ntsc-u")
ap.add_argument("--secs", type=int, default=80); ap.add_argument("--mkstate", default=""); ap.add_argument("--turn", action="store_true"); ap.add_argument("--findangle", action="store_true"); ap.add_argument("--profile", default=""); ap.add_argument("--rw", default=""); ap.add_argument("--bootrw", action="store_true"); ap.add_argument("--speed", action="store_true"); ap.add_argument("--smooth", action="store_true"); ap.add_argument("--soak", action="store_true"); ap.add_argument("--bootshots", default=""); ap.add_argument("--bootdbg", action="store_true"); ap.add_argument("--depthlog", default=""); ap.add_argument("--findhp", action="store_true"); ap.add_argument("--objs", action="store_true"); ap.add_argument("--findenemy", default=""); ap.add_argument("--watch", default=""); ap.add_argument("--logicrate", action="store_true"); ap.add_argument("--nohudshots", default=""); ap.add_argument("--shotint", type=int, default=0); ap.add_argument("--poke", default=""); ap.add_argument("--state", default=""); ap.add_argument("--shots", default="")
ap.add_argument("--core", default=os.path.join(os.path.dirname(__file__), "genesis_plus_gx_libretro.dylib"))
a = ap.parse_args()
core = C.CDLL(a.core)
opts = {b"genesis_plus_gx_overclock": a.oc.encode(), b"genesis_plus_gx_region_detect": a.region.encode(),
        b"genesis_plus_gx_overscan": b"disabled"}
_keep = {}
class Var(C.Structure): _fields_ = [("key", C.c_char_p), ("value", C.c_char_p)]
class GameInfo(C.Structure): _fields_ = [("path", C.c_char_p), ("data", C.c_void_p), ("size", C.c_size_t), ("meta", C.c_char_p)]
pixfmt = [0]; sysdir = C.c_char_p(os.path.dirname(os.path.abspath(__file__)).encode())
ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
@ENV
def env(cmd, data):
    cmd &= 0xFFFF
    if cmd == 15:  # GET_VARIABLE
        v = C.cast(data, C.POINTER(Var)).contents
        if v.key in opts:
            _keep[v.key] = C.c_char_p(opts[v.key]); v.value = _keep[v.key].value; return True
        return False
    if cmd == 10: pixfmt[0] = C.cast(data, C.POINTER(C.c_int)).contents.value; return True
    if cmd in (9, 31): C.cast(data, C.POINTER(C.c_char_p))[0] = sysdir.value; return True
    if cmd == 52: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
    if cmd in (16, 3): return True  # SET_VARIABLES, SET_MESSAGE
    if cmd == 17: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
    return False
frame = [None, 0, 0, 0]
VID = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
@VID
def vid(data, w, h, pitch):
    if data: frame[0] = C.string_at(data, pitch * h); frame[1:] = [w, h, pitch]
AUD = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
@AUD
def aud(l, r): pass
AUDB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
@AUDB
def audb(d, n): return n
POLL = C.CFUNCTYPE(None)
@POLL
def poll(): pass
held = set()
INP = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
@INP
def inp(port, dev, idx, id): return 1 if (port == 0 and id in held) else 0
core.retro_set_environment(env); core.retro_set_video_refresh(vid); core.retro_set_audio_sample(aud)
core.retro_set_audio_sample_batch(audb); core.retro_set_input_poll(poll); core.retro_set_input_state(inp)
core.retro_init()
data = open(a.rom, "rb").read(); buf = C.create_string_buffer(data, len(data))
gi = GameInfo(os.path.abspath(a.rom).encode(), C.cast(buf, C.c_void_p), len(data), None)
assert core.retro_load_game(C.byref(gi)), "load failed"
START, UP, LEFT = 3, 4, 6
def px(x, y):
    d, w, h, p = frame
    if pixfmt[0] == 2:  # RGB565
        return d[y * p + x * 2] | d[y * p + x * 2 + 1] << 8
    return int.from_bytes(d[y * p + x * 4:y * p + x * 4 + 4], "little")
def BPP(): return 2 if pixfmt[0] == 2 else 4
def view_hash():
    d, w, h, p = frame
    return hashlib.md5(b"".join(d[y * p + 40 * BPP():y * p + 150 * BPP()] for y in range(48, 80))).digest()
def save_png(path):
    import zlib, struct
    d, w, h, p = frame; rows = []
    for y in range(h):
        r = bytearray(b"\0")
        for x in range(w):
            v = px(x, y)
            if pixfmt[0] == 2: r += bytes([(v >> 11 & 31) << 3, (v >> 5 & 63) << 2, (v & 31) << 3])
            else: r += bytes([v >> 16 & 255, v >> 8 & 255, v & 255])
        rows.append(bytes(r))
    def ch(t, b): return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                          + ch(b"IDAT", zlib.compress(b"".join(rows))) + ch(b"IEND", b""))

from PIL import Image
ref = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "hud_ref.png")).convert("RGB")
PTS = [(x, y) for x in range(0, 320, 7) for y in (2, 30, 128, 135, 222)] + [(x, y) for y in range(40, 224, 6) for x in (2, 10, 316)]
def rgb(x, y):
    v = px(x, y)
    if pixfmt[0] == 2: return ((v >> 11 & 31) << 3, (v >> 5 & 63) << 2, (v & 31) << 3)
    return (v >> 16 & 255, v >> 8 & 255, v & 255)
def hud():
    if frame[1] != 320 or frame[2] != 224: return False
    m = sum(1 for (x, y) in PTS if all(abs(a - b) < 12 for a, b in zip(rgb(x, y), ref.getpixel((x, y)))))
    return m / len(PTS) > 0.7
hz = 50 if a.region == "pal" else 60
if a.mkstate:
    streak = 0
    for f in range(1, 200 * hz):
        held.clear()
        if streak == 0 and f % (2 * hz) < 6: held.add(START)
        core.retro_run()
        streak = streak + 1 if hud() else 0
        if streak > 8 * hz:
            n = core.retro_serialize_size(); b = C.create_string_buffer(n)
            assert core.retro_serialize(b, n); open(a.mkstate, "wb").write(b.raw)
            save_png(a.mkstate + ".png"); print("state saved at frame", f); break
    else: sys.exit("never reached gameplay")
    sys.exit(0)
if a.state:
    raw = open(a.state, "rb").read(); b = C.create_string_buffer(raw, len(raw))
    assert core.retro_unserialize(b, len(raw)), "unserialize failed"
    core.retro_get_memory_data.restype = C.c_void_p
    for spec in filter(None, a.poke.split(",")):
        addr, val = (int(x, 16) for x in spec.split("="))
        C.memmove(core.retro_get_memory_data(2) + (addr & 0xFFFF), struct.pack("<H", val) if False else bytes([val & 0xFF, val >> 8]), 2)

core.retro_get_memory_data.restype = C.c_void_p; core.retro_get_memory_size.restype = C.c_size_t
def wram(): return C.string_at(core.retro_get_memory_data(2), core.retro_get_memory_size(2))
if a.findangle:
    import struct
    snaps = []
    for f in range(120):
        held.clear(); held.add(LEFT); core.retro_run()
        if f % 10 == 9: snaps.append(wram())
    tot = None
    def word(m, off): return struct.unpack("<H", m[off:off+2])[0]  # GPGX WRAM is byteswapped
    cands = []
    for off in range(0, 0x10000, 2):
        vals = [word(m, off) for m in snaps]
        d = [((vals[i+1]-vals[i]) + 0x8000) % 0x10000 - 0x8000 for i in range(len(vals)-1)]
        nz = [x for x in d if x]
        if len(nz) >= 8 and (all(x > 0 for x in nz) or all(x < 0 for x in nz)) and max(abs(x) for x in nz) < 0x400:
            cands.append((hex(0xFF0000 + off), sum(d), d))
    for c in cands[:40]: print(c)
    sys.exit(0)

if a.profile:
    on = C.c_int.in_dll(core, "zt_prof_on"); core.zt_prof_reset()
    excl = (C.c_uint * 0x100000).in_dll(core, "zt_excl"); incl = (C.c_uint * 0x100000).in_dll(core, "zt_incl"); calls = (C.c_uint * 0x100000).in_dll(core, "zt_calls")
    for f in range(60): core.retro_run()
    on.value = 1
    N = a.secs * hz
    for f in range(N):
        held.clear(); held.add(UP)
        if f % (4 * hz) < hz: held.add(LEFT)
        core.retro_run()
    on.value = 0
    total = sum(excl)
    import json
    json.dump({"total": total, "frames": N, "excl": {i*2: excl[i] for i in range(0x100000) if excl[i]},
               "incl": {i*2: incl[i] for i in range(0x100000) if incl[i]}, "calls": {i*2: calls[i] for i in range(0x100000) if calls[i]}},
              open(a.profile, "w"))
    print("total cycles", total, "per frame", total // N)
    sys.exit(0)

TAGS = {0xaa2:"vbl",0x79a:"79a",0xd36:"d36",0x23c2:"23c2",0x2cec:"2cec",0xdab8:"move",0x13576:"13576",0x1c0f6:"1c0f6",0x1c52c:"1c52c",
        0x131e8:"wrap",0x1c410:"1c410",0xec1c:"wobble",0xd49a:"d49a",0xb9a6:"RENDER",0xe816:"e816",0xece2:"ece2",0xecc0:"unwobble",
        0xb35c:"b35c",0x13182:"13182",0x744:"sprdma",0x57e0c:"57e0c",0x22be:"22be",0x1e0fa:"1e0fa"}
if a.rw:
    on = C.c_int.in_dll(core, "zt_prof_on"); core.zt_prof_reset()
    tag_of = (C.c_uint * 0x100000).in_dll(core, "zt_tag_of")
    names = ["main"] + list(TAGS.values())
    for bit, addr in enumerate(TAGS, start=1): tag_of[addr >> 1] = 1 << bit
    rd = (C.c_uint * 0x10000).in_dll(core, "zt_rd"); wr = (C.c_uint * 0x10000).in_dll(core, "zt_wr")
    for f in range(60): core.retro_run()
    on.value = 1
    for f in range(a.secs * hz):
        held.clear(); held.add(UP)
        if f % (4 * hz) < hz: held.add(LEFT)
        if f % 30 < 3: held.add(5)  # fire? (B button id 0 / A id 8) - try a few
        core.retro_run()
    on.value = 0
    def nm(m): return ",".join(n for b, n in enumerate(names) if m >> b & 1)
    import json
    json.dump({"names": names, "rd": list(rd), "wr": list(wr)}, open(a.rw, "w"))
    print("saved")
    sys.exit(0)

if a.bootrw:
    on = C.c_int.in_dll(core, "zt_prof_on"); core.zt_prof_reset(); on.value = 1
    rd = (C.c_uint * 0x10000).in_dll(core, "zt_rd"); wr = (C.c_uint * 0x10000).in_dll(core, "zt_wr")
    streak = 0
    for f in range(150 * hz):
        held.clear()
        if streak == 0:
            if f % (2 * hz) < 6: held.add(START)
        else:
            held.add(UP)
            if f % (4 * hz) < hz: held.add(LEFT)
            if f % 20 < 2: held.add(0)
            if f % 37 < 2: held.add(8)
        core.retro_run()
        streak = streak + 1 if hud() else 0
    for lo, hi in [(0x6456, 0x64CB), (0x773C, 0x785D), (0x732C, 0x7389), (0x71D4, 0x7215), (0x10C0, 0x1169)]:
        used = [x for x in range(lo, hi + 1) if rd[x]]
        print(f"FF{lo:04X}-FF{hi:04X}: bytes ever READ = {len(used)}", [hex(0xff0000+u) for u in used[:6]])
    sys.exit(0)

if a.speed:
    import struct
    def w16(addr): m = C.string_at(core.retro_get_memory_data(2) + (addr & 0xFFFF), 2); return struct.unpack("<H", m)[0]
    for f in range(150): held.clear(); held.add(LEFT); core.retro_run()   # let overclock kick in
    ang_total, last_a, changes, last_h = 0, w16(0xFF0E04), 0, None
    N = a.secs * hz
    for f in range(N):
        held.clear(); held.add(LEFT); core.retro_run()
        cur = w16(0xFF0E04); d = ((cur - last_a + 256) & 511) - 256; ang_total += d; last_a = cur
        h = view_hash()
        if h != last_h: changes += 1
        last_h = h
    print(f"fps {changes / a.secs:5.1f}   turn rate {abs(ang_total) / a.secs:6.1f} angle units/s")
    sys.exit(0)

if a.smooth:
    import struct
    def w16(addr): m = C.string_at(core.retro_get_memory_data(2) + (addr & 0xFFFF), 2); return struct.unpack("<H", m)[0]
    for f in range(150): held.clear(); held.add(LEFT); core.retro_run()
    ra, real = [], []
    for f in range(40):
        held.clear(); held.add(LEFT if f < 25 else UP); core.retro_run()
        ra.append(w16(0xFF7760)); real.append(w16(0xFF0E04))
    print("rendered angle:", ra)
    print("logic angle:   ", real)
    if a.shots:
        for f in range(6):
            held.clear(); held.add(LEFT); core.retro_run(); save_png(f"{a.shots}_{f}.png")
    sys.exit(0)

if a.soak:
    import random, struct
    rng = random.Random(int(os.environ.get("ZT_SEED", "1234")))
    def w16(addr): m = C.string_at(core.retro_get_memory_data(2) + (addr & 0xFFFF), 2); return struct.unpack("<H", m)[0]
    buttons = [UP, LEFT, 7, 5, 0, 8, 1]  # up, left, right, down, B, A, Y(C)
    cur, last_h, changes, frozen, maxfrozen, fpsl, hudless = set(), None, 0, 0, 0, [], 0
    nshots = [0]
    for f in range(a.secs * hz):
        if f % 20 == 0:
            cur = set(b for b in buttons if rng.random() < 0.35)
            if LEFT in cur and 7 in cur: cur.discard(7)
        held.clear(); held.update(cur)
        if not hud():
            hudless += 1
            if f % (2 * hz) < 6: held.add(START)
            if a.nohudshots and f % 20 == 0 and nshots[0] < 90: save_png(f"{a.nohudshots}_{f:06d}.png"); nshots[0] += 1
        core.retro_run()
        h = view_hash()
        if h != last_h: changes += 1; frozen = 0
        else: frozen += 1
        maxfrozen = max(maxfrozen, frozen); last_h = h
        if f % hz == hz - 1: fpsl.append(changes); changes = 0
        if a.shots and f % ((a.shotint or 20) * hz) == 0: save_png(f"{a.shots}_{f // hz:03d}.png")
    print(f"fps avg {sum(fpsl)/len(fpsl):.1f} min {min(fpsl)} max {max(fpsl)}  longest static view {maxfrozen} frames  non-HUD frames {hudless}  vbl={w16(0xFF0000)}")
    sys.exit(0)

if a.bootshots:
    for f in range(1, 60 * hz):
        held.clear()
        if f % (2 * hz) < 6: held.add(START)
        core.retro_run()
        if f % (3 * hz) == 0: save_png(f"{a.bootshots}_{f // hz:03d}.png")
    sys.exit(0)

if a.bootdbg:
    import struct
    def w16(addr): m = C.string_at(core.retro_get_memory_data(2) + (addr & 0xFFFF), 2); return struct.unpack("<H", m)[0]
    seen = 0
    for f in range(1, 60 * hz):
        held.clear()
        if not seen and f % (2 * hz) < 6: held.add(START)
        core.retro_run()
        if hud(): seen += 1
        if seen and seen < 200 and f % 1 == 0:
            depth = next((y for y in range(224) if len(set(px(x, y) for x in range(0, 320, 4))) > 1), 224)
            if seen < 40 or seen % 20 == 0:
                print(f"f={f} depth={depth} DISP={w16(0xFF7764)} BAND={w16(0xFF7766)} NOBAND={w16(0xFF776A)} HPEND={w16(0xFF7768)} IEON={w16(0xFF776C)} hints={w16(0xFF7770)} hv={w16(0xFF7772):04x} fb={w16(0xFF0002)}")
        if seen >= 200: break
    sys.exit(0)

if a.depthlog:
    out = []
    for f in range(600):
        held.clear(); held.add(LEFT); core.retro_run()
        depth = next((y for y in range(224) if len(set(px(x, y) for x in range(0, 320, 4))) > 1), 224)
        out.append(depth)
        if depth == 12 and not os.path.exists(a.depthlog + "_12.png"): save_png(a.depthlog + "_12.png")
        if depth == 15 and not os.path.exists(a.depthlog + "_15.png"): save_png(a.depthlog + "_15.png")
    print("".join("x" if d == 15 else ("." if d < 15 else "+") for d in out))
    sys.exit(0)

if a.findhp:
    import struct
    base = core.retro_get_memory_data(2)
    ram = C.string_at(base, 0x10000)
    cands = [o for o in range(0, 0x10000, 2) if struct.unpack("<H", ram[o:o+2])[0] in (0x99, 0x9900)]
    print("cands", [hex(0xFF0000 + o) for o in cands])
    sys.exit(0)

if a.objs:
    import struct
    def ram(): return C.string_at(core.retro_get_memory_data(2), 0x10000)
    def w(m, addr): return struct.unpack("<H", m[(addr & 0xFFFF):(addr & 0xFFFF) + 2])[0]
    def l(m, addr): return (w(m, addr) << 16) | w(m, addr + 2)
    for f in range(150): held.clear(); core.retro_run()
    hist = {}
    N = a.secs * hz
    for f in range(N):
        held.clear(); core.retro_run()
        m = ram(); n = w(m, 0xFF24E8); p = l(m, 0xFF24EA); k = 0
        while p and (p >> 16) == 0xFF and k < n:
            hist.setdefault(p, []).append((w(m, p + 0x20), w(m, p + 0x22)))
            p = l(m, p); k += 1
    for p, pts in sorted(hist.items()):
        dist = sum(abs(((pts[j+1][0]-pts[j][0]+0x8000)&0xFFFF)-0x8000) + abs(((pts[j+1][1]-pts[j][1]+0x8000)&0xFFFF)-0x8000) for j in range(len(pts)-1))
        print(f"obj {p:06X} samples {len(pts)} moved {dist / a.secs:7.1f} units/s  start {pts[0]} end {pts[-1]}")
    sys.exit(0)

if a.findenemy:
    import random, struct
    rng = random.Random(7)
    def wv(addr): return struct.unpack("<H", C.string_at(core.retro_get_memory_data(2) + (addr & 0xFFFF), 2))[0]
    cur = set(); seen = 0
    for f in range(400 * hz):
        if f % 20 == 0:
            cur = set(b for b in [UP, LEFT, 7, 0] if rng.random() < 0.4)
            if LEFT in cur and 7 in cur: cur.discard(7)
        held.clear(); held.update(cur)
        if not hud() and f % (2 * hz) < 6: held.add(START)
        core.retro_run()
        n = wv(0xFF24E8)
        if n: seen += 1
        else: seen = 0
        if seen == 30:
            nsz = core.retro_serialize_size(); b = C.create_string_buffer(nsz)
            assert core.retro_serialize(b, nsz); open(a.findenemy, "wb").write(b.raw); save_png(a.findenemy + ".png")
            print("enemy state saved at frame", f, "count", n); sys.exit(0)
    print("no enemies found"); sys.exit(1)

if a.watch:
    lo, hi = (int(x, 16) for x in a.watch.split("-"))
    C.c_uint.in_dll(core, "zt_watch_lo").value = lo; C.c_uint.in_dll(core, "zt_watch_hi").value = hi
    on = C.c_int.in_dll(core, "zt_prof_on"); core.zt_prof_reset(); on.value = 1
    for f in range(a.secs * hz): held.clear(); core.retro_run()
    on.value = 0
    pcs = (C.c_uint * 64).in_dll(core, "zt_watch_pc"); ns = (C.c_uint * 64).in_dll(core, "zt_watch_n"); st = ((C.c_uint * 8) * 64).in_dll(core, "zt_watch_stack")
    for k in range(64):
        if ns[k]: print(f"pc {pcs[k]:06X} writes {ns[k]:5d}  call stack (innermost first): " + " ".join(f"{x:06X}" for x in st[k] if x))
    sys.exit(0)

if a.logicrate:
    import random
    rng = random.Random(99)
    calls = (C.c_uint * 0x100000).in_dll(core, "calls" if False else "zt_calls")
    on = C.c_int.in_dll(core, "zt_prof_on"); core.zt_prof_reset(); on.value = 1
    cur = set(); per = []; last = 0
    for f in range(a.secs * hz):
        if f % 20 == 0:
            cur = set(b for b in [UP, LEFT, 7, 0, 8] if rng.random() < 0.4)
            if LEFT in cur and 7 in cur: cur.discard(7)
        held.clear(); held.update(cur)
        if not hud() and f % (2 * hz) < 6: held.add(START)
        core.retro_run()
        if f % (5 * hz) == 5 * hz - 1:
            c = calls[0x23c2 >> 1]; per.append((c - last) / 5); last = c
    per.sort()
    print("logic ticks/s per 5s window: median %.1f  p25 %.1f  p75 %.1f  min %.1f  max %.1f" % (per[len(per)//2], per[len(per)//4], per[3*len(per)//4], per[0], per[-1]))
    sys.exit(0)
depths, fps_log, last, changes, blanked, gframes, nohud = {}, [], None, 0, 0, 0, 0
for f in range(1, a.secs * hz + 1):
    held.clear()
    if a.turn: held.add(LEFT)
    else:
        held.add(UP)
        if f % (4 * hz) < hz: held.add(LEFT)
    core.retro_run()
    if not hud(): nohud += 1
    hsh = view_hash()
    if hsh != last: changes += 1
    last = hsh
    gframes += 1
    row = [px(x, 3) for x in range(0, 320, 4)]
    if len(set(row)) == 1:
        blanked += 1
        depth = next((y for y in range(224) if len(set(px(x, y) for x in range(0, 320, 4))) > 1), 224)
        depths[depth] = depths.get(depth, 0) + 1
    if f % hz == 0: fps_log.append(changes); changes = 0
    if a.shots and f % (5 * hz) == 0: save_png(f"{a.shots}_{f // hz:03d}.png")
game = fps_log
print("fps/s:", " ".join(map(str, fps_log)))
print(f"avg fps: {sum(game)/len(game):.1f}  min {min(game)}  max {max(game)}  blank-top frames: {blanked}/{gframes}  non-HUD frames: {nohud}")
print("blank band depth histogram:", sorted(depths.items()))
