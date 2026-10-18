#!/usr/bin/env python3
"""Zero Tolerance - high frame rate patch builder.

Assembles zt_high_fps.asm into free ROM space and hooks it into the game:
fixed-rate logic with interpolated rendering, single-VBlank framebuffer DMA,
and a constant blank band at the top of the screen during gameplay.
See zt_high_fps.asm for details. Supported ROMs and their addresses: games.py.

Writes each patched ROM and an IPS patch next to this script.

  python3 make_patch.py [--hz 10] [GAME ...]       cartridge ROMs found in the repo root (all, or the GAMEs
                                                   named: zt, zt_mouse, ztu, bzt), for RetroArch etc.
  python3 make_patch.py --steam DIR [--hz 10]      Steam release (QUByte Classics), from its install DIR:
                                                   writes steam/res/game and steam/ew_core.dll to copy over
"""
import argparse, hashlib, shutil, struct, subprocess, sys, pathlib
from games import GAMES

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ASM = HERE / "zt_high_fps.asm"
BIN = HERE / "zt_high_fps.bin"
VASM = HERE / "tools" / "vasmm68k_mot"         # or vasmm68k_mot on PATH (http://sun.hasenbraten.de/vasm/)
TICK_HZ = 10                            # game logic rate; the original runs ~7-11 fps in play
# Entry points: the asm starts with a table of bra.w at 4-byte steps.
(DECIDE, LOGIC_RENDER, INIT_RENDER, SKY, CELL,
 VBLANK, HINT, DISP_ON, DISP_OFF, QDMA_ON, QDMA_OFF,
 EXIT_CHECK, DEATH_EXIT) = range(0, 52, 4)
SKY_A4, CELL_POP = 72, 76               # Beyond's variants

def w(*words):
    return b"".join(struct.pack(">H", x & 0xFFFF) for x in words)

def jsr(addr): return w(0x4EB9) + struct.pack(">I", addr)
def jmp(addr): return w(0x4EF9) + struct.pack(">I", addr)
def a6(addr): return addr - 0xFF8000            # a6-relative displacement
NOP = w(0x4E71)

def hooks(g, org):
    """(address, original bytes, replacement) for game addresses g, patch code at org"""
    def bsr_w(site, target): return w(0x6100, target - site - 2)
    def vdp_reg(v): return w(0x33FC, v, 0x00C0, 0x0004)                # move.w #v,$C00004
    sr2500 = w(0x46FC, 0x2500)
    h = [
        # main loop
        (g["S_DECIDE"], bsr_w(g["S_DECIDE"], g["INPUT_A"]) + bsr_w(g["S_DECIDE"] + 4, g["INPUT_B"]),
         jmp(org + DECIDE) + NOP),
        (g["S_LOGIC_RENDER"], jsr(g["RENDER_CALL"]), jsr(org + LOGIC_RENDER)),  # render in logic block
        (g["S_INIT_RENDER"], jsr(g["RENDER_CALL"]), jsr(org + INIT_RENDER)),    # level start render
        (g["S_RESPAWN_RENDER"], jsr(g["RENDER_CALL"]), jsr(org + INIT_RENDER)), # respawn render
        # sky scroll angle
        (g["S_SKY"], w(0x342E, a6(g["CAM_A"]), 0x287C, 0x00C0, 0x0000), jsr(org + SKY_A4) + NOP + NOP)
        if g.get("SKY_A4") else (g["S_SKY"], w(0x342E, a6(g["CAM_A"]), 0x4442), jsr(org + SKY)),
        # floor-cell logic in RENDER
        (g["S_CELL"], bsr_w(g["S_CELL"], g["CELL_LOGIC"]) + w(0x301F), jsr(org + CELL_POP))
        if g.get("CELL_POP") else
        (g["S_CELL"], bsr_w(g["S_CELL"], g["CELL_LOGIC"]) + w(0x302E, a6(g["BOB"])), jsr(org + CELL) + NOP),
        # VBlank: keep the counters, replace the framebuffer upload
        (g["S_VBLANK"], w(0x4A79) + struct.pack(">I", g["FB_PENDING"]), jmp(org + VBLANK)),
        # main loop exits (level exit, death): band off
        (g["S_EXIT"], w(0x4A6E, a6(g["EXIT_FLAG"]), 0x6600, g["EXIT_TGT"] - g["S_EXIT"] - 6),
         jsr(org + EXIT_CHECK) + NOP),
        (g["S_DEATH"], w(0x3E2E, a6(g["LIVES"]), 0x6700 | (g["DEATH_TGT"] - g["S_DEATH"] - 6)),
         jsr(org + DEATH_EXIT)),
        # HUD DMA queue: don't end the band early
        (g["S_QDMA_ON"], vdp_reg(0x8174), jsr(org + QDMA_ON) + NOP),
        (g["S_QDMA_OFF"], vdp_reg(0x8164), jsr(org + QDMA_OFF) + NOP),
        # line interrupt vector, and let level 4 through (was $2500)
        (0x0070, struct.pack(">I", g["HINT_OLD"]), struct.pack(">I", org + HINT)),
        (g["S_SR_BOOT"], sr2500, w(0x46FC, 0x2300)),                          # boot
        (g["S_SR_SOUND"], sr2500, w(0x46FC, 0x2300)),                         # after sound driver calls
        (g["S_SR_LINK"], sr2500, w(0x46FC, 0x2300)),                          # link cable off
        (g["S_SR_LINK_SAVE"], w(0x3D7C, 0x2500), w(0x3D7C, 0x2300)),          # (stored copy of the above)
    ]
    h += [(a, vdp_reg(0x8164), jsr(org + DISP_ON) + NOP) for a in g["S_DISP_ON"]]
    h += [(a, vdp_reg(0x8124), jsr(org + DISP_OFF) + NOP) for a in g["S_DISP_OFF"]]
    return h

# Steam release (QUByte Classics: Zero Tolerance Collection). Its ROM is Rev A plus QUByte changes,
# including a 15 fps limiter at the main loop top; its emulator (ew_core.dll, Mednafen MD) has a
# 68000 clock divider (7 = normal, 3 with -turbo) that we set to 1 (7x).
STEAM_ROM_SHA1 = "0a91c2b49330c5cc8be9c248845567417d0b41cc"
STEAM_DLL_SHA1 = "8df8a1f7270bad6dfbac86d46fd1ce94e090c300"
STEAM_ROM_HOOKS = [
    (0x143E, w(0x4EB8, 0x01C4, 0x4EB8, 0x01B0), w(0x426E, 0xA916, 0x4A6E, 0xA72C)),  # limiter -> original code
]
STEAM_DLL_PATCHES = [  # (file offset, original, replacement)
    (0x1669C8, b"\x07\x00\x00\x00", b"\x01\x00\x00\x00"),   # default CPU divider 7 -> 1
    (0x4E61, b"\xB9\x03\x00\x00\x00", b"\xB9\x01\x00\x00\x00"),  # -turbo divider 3 -> 1
]

def assemble(game):
    g = game["addr"]
    syms = {k: v for k, v in g.items() if type(v) is int and not k.startswith("S_") and k not in ("HINT_OLD", "RENDER_CALL")}
    syms.update(ORG_ADDR=game["org"], GAME_ID=game["id"],
                LOGIC_PERIOD_NTSC=round(60 / TICK_HZ), LOGIC_PERIOD_PAL=round(50 / TICK_HZ))
    vasm = str(VASM) if VASM.exists() else (shutil.which("vasmm68k_mot") or sys.exit("vasmm68k_mot not found: put it in tools/ or on PATH"))
    subprocess.run([vasm, "-quiet", "-Fbin", "-m68000", *("-D%s=%d" % kv for kv in syms.items()),
                    "-o", str(BIN), str(ASM)], check=True)
    return BIN.read_bytes()

def build(rom, game, extra_hooks=()):
    org = game["org"]
    out = bytearray(rom)
    if len(out) < org:                  # the code goes past the end: pad to a whole number of 128 KB
        out += b"\xFF" * (org - len(out))
    code = assemble(game)
    size = max(len(out), org + len(code))
    out += b"\xFF" * (((size + 0x1FFFF) & ~0x1FFFF) - len(out))
    assert all(b == 0xFF for b in out[org:org + len(code)]), "target ROM space not free"
    out[org:org + len(code)] = code
    for addr, orig, new in hooks(game["addr"], org) + list(extra_hooks):
        assert out[addr:addr + len(orig)] == orig, "unexpected bytes at %#x: %s, expected %s" % (
            addr, out[addr:addr + len(orig)].hex(), orig.hex())
        assert len(new) == len(orig)
        out[addr:addr + len(new)] = new
    return out

def fix_checksum(rom):
    s = sum(struct.unpack(">%dH" % ((len(rom) - 0x200) // 2), rom[0x200:])) & 0xFFFF
    rom[0x18E:0x190] = struct.pack(">H", s)

def ips(orig, new):
    orig = orig + b"\xFF" * (len(new) - len(orig))     # a grown ROM: the new tail is written whole
    out, i = bytearray(b"PATCH"), 0
    while i < len(orig):
        if orig[i] != new[i]:
            j = i
            while j < len(orig) and orig[j] != new[j] and j - i < 0xFFFF:
                j += 1
            if i == 0x454F46:               # "EOF" as an offset would end the patch: start one byte earlier
                i -= 1
            out += struct.pack(">I", i)[1:] + struct.pack(">H", j - i) + new[i:j]
            i = j
        else:
            i += 1
    return bytes(out + b"EOF")

def build_steam(steam_dir):
    steam_dir = pathlib.Path(steam_dir)
    rom = (steam_dir / "res" / "game").read_bytes()
    dll = (steam_dir / "ew_core.dll").read_bytes()
    if hashlib.sha1(rom).hexdigest() != STEAM_ROM_SHA1:
        sys.exit("unexpected Steam res/game (sha1 %s)" % STEAM_ROM_SHA1)
    if hashlib.sha1(dll).hexdigest() != STEAM_DLL_SHA1:
        sys.exit("unexpected Steam ew_core.dll (sha1 %s)" % STEAM_DLL_SHA1)
    new = build(rom, GAMES["zt"], STEAM_ROM_HOOKS)
    fix_checksum(new)
    new_dll = bytearray(dll)
    for off, orig, rep in STEAM_DLL_PATCHES:
        assert new_dll[off:off + len(orig)] == orig, "unexpected DLL bytes at %#x" % off
        new_dll[off:off + len(rep)] = rep
    out = HERE / "steam"
    (out / "res").mkdir(parents=True, exist_ok=True)
    (out / "res" / "game").write_bytes(new)
    (out / "ew_core.dll").write_bytes(new_dll)
    (out / "zt_high_fps_steam.ips").write_bytes(ips(rom, new))
    print("wrote steam/res/game, steam/ew_core.dll and steam/zt_high_fps_steam.ips")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz", type=float, default=TICK_HZ, help="game logic rate (default %(default)s)")
    ap.add_argument("--steam", metavar="DIR", help="build for the Steam release installed in DIR")
    ap.add_argument("games", nargs="*", metavar="GAME", help="games to build: %s (default: all found)" % ", ".join(GAMES))
    args = ap.parse_args()
    for key in args.games:
        if key not in GAMES:
            ap.error("unknown game %s" % key)
    TICK_HZ = args.hz
    if args.steam:
        build_steam(args.steam)
        sys.exit(0)
    built = 0
    for key in args.games or GAMES:
        game = GAMES[key]
        src = ROOT / game["file"]
        if not src.exists():
            if args.games:
                sys.exit("%s: %s not found" % (key, src))
            continue
        rom = src.read_bytes()
        if hashlib.sha1(rom).hexdigest() != game["sha1"]:
            sys.exit("%s: unexpected ROM (sha1 %s)" % (src.name, game["sha1"]))
        new = build(rom, game)
        fix_checksum(new)
        (HERE / game["out"]).write_bytes(new)
        (HERE / game["ips"]).write_bytes(ips(rom, new))
        print("%s: wrote %s and %s" % (game["title"], game["out"], game["ips"]))
        built += 1
    if not built:
        sys.exit("no ROMs found (see games.py for the file names)")
