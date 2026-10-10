#!/usr/bin/env python3
"""Zero Tolerance (USA, Europe) (Rev A) - high frame rate patch builder.

Assembles zt_high_fps.asm into free ROM space and hooks it into the game:
fixed-rate logic with interpolated rendering, single-VBlank framebuffer DMA,
and a constant blank band at the top of the screen during gameplay.
See zt_high_fps.asm for details.

Writes the patched ROM and an IPS patch next to this script.

  python3 make_patch.py [--hz 10]                  cartridge ROM (Rev A) for RetroArch etc.
  python3 make_patch.py --steam DIR [--hz 10]      Steam release (QUByte Classics), from its install DIR:
                                                   writes steam/res/game and steam/ew_core.dll to copy over
"""
import argparse, hashlib, shutil, struct, subprocess, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parent / "Zero Tolerance (USA, Europe) (Rev A).gen"
OUT = HERE / "Zero Tolerance (high fps).gen"
IPS = HERE / "zt_high_fps.ips"
ASM = HERE / "zt_high_fps.asm"
BIN = HERE / "zt_high_fps.bin"
VASM = HERE / "tools" / "vasmm68k_mot"         # or vasmm68k_mot on PATH (http://sun.hasenbraten.de/vasm/)
SHA1 = "d6d9733a619ba6be0dd76591d8dec621e4fdc17e"
ORG = 0x1D0000                          # free (0xFF-filled) ROM space

# Entry points: the asm starts with a table of bra.w at 4-byte steps.
(DECIDE, LOGIC_RENDER, INIT_RENDER, SKY, CELL,
 VBLANK, HINT, DISP_ON, DISP_OFF, QDMA_ON, QDMA_OFF,
 EXIT_CHECK, DEATH_EXIT) = (ORG + 4 * i for i in range(13))
TICK_HZ = 10                            # game logic rate; the original runs ~7-11 fps in play

def w(*words):
    return b"".join(struct.pack(">H", x) for x in words)

def jsr(addr): return w(0x4EB9) + struct.pack(">I", addr)
def jmp(addr): return w(0x4EF9) + struct.pack(">I", addr)
NOP = w(0x4E71)

DISP_ON_SITES = [0x134E, 0x1432, 0x1624, 0x199C, 0x2E3E]    # move.w #$8164,$C00004
DISP_OFF_SITES = [0x11A6, 0x139A, 0x1830, 0x29DE, 0x2CF4]   # move.w #$8124,$C00004

HOOKS = [  # (address, original bytes, replacement)
    # main loop
    (0x162C, w(0x6100, 0xF16C, 0x6100, 0xF704), jmp(DECIDE) + NOP),       # bsr $79A; bsr $D36
    (0x16CE, jsr(0xB9A6), jsr(LOGIC_RENDER)),                             # render in logic block
    (0x13F6, jsr(0xB9A6), jsr(INIT_RENDER)),                              # level start render
    (0x1964, jsr(0xB9A6), jsr(INIT_RENDER)),                              # respawn render
    (0x1470, w(0x342E, 0x8E04, 0x4442), jsr(SKY)),                        # sky scroll angle
    (0xBAE6, w(0x6100, 0xF9FC, 0x302E, 0x916E), jsr(CELL) + NOP),         # floor-cell logic in RENDER
    # VBlank: keep the counters at $AA2, replace the framebuffer upload
    (0x0AC2, w(0x4A79, 0x00FF, 0x0002), jmp(VBLANK)),                     # tst.w $FF0002
    # main loop exits (level exit, death): band off
    (0x173A, w(0x4A6E, 0xA722, 0x6600, 0x0300), jsr(EXIT_CHECK) + NOP),
    (0x1788, w(0x3E2E, 0xA4E8, 0x6720), jsr(DEATH_EXIT)),
    # HUD DMA queue: don't end the band early
    (0x07A4, w(0x33FC, 0x8174, 0x00C0, 0x0004), jsr(QDMA_ON) + NOP),
    (0x07F6, w(0x33FC, 0x8164, 0x00C0, 0x0004), jsr(QDMA_OFF) + NOP),
    # line interrupt vector, and let level 4 through (was $2500)
    (0x0070, struct.pack(">I", 0xBAC), struct.pack(">I", HINT)),
    (0x0A18, w(0x46FC, 0x2500), w(0x46FC, 0x2300)),                       # boot
    (0xD7AE, w(0x46FC, 0x2500), w(0x46FC, 0x2300)),                       # after sound driver calls
    (0x1C016, w(0x46FC, 0x2500), w(0x46FC, 0x2300)),                      # link cable off
    (0x1C010, w(0x3D7C, 0x2500), w(0x3D7C, 0x2300)),                      # (stored copy of the above)
] + [(a, w(0x33FC, 0x8164, 0x00C0, 0x0004), jsr(DISP_ON) + NOP) for a in DISP_ON_SITES] \
  + [(a, w(0x33FC, 0x8124, 0x00C0, 0x0004), jsr(DISP_OFF) + NOP) for a in DISP_OFF_SITES]

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

def assemble():
    periods = ["-DLOGIC_PERIOD_NTSC=%d" % round(60 / TICK_HZ), "-DLOGIC_PERIOD_PAL=%d" % round(50 / TICK_HZ)]
    vasm = str(VASM) if VASM.exists() else (shutil.which("vasmm68k_mot") or sys.exit("vasmm68k_mot not found: put it in tools/ or on PATH"))
    subprocess.run([vasm, "-quiet", "-Fbin", "-m68000", *periods, "-o", str(BIN), str(ASM)], check=True)
    return BIN.read_bytes()

def build(rom, extra_hooks=()):
    out = bytearray(rom)
    code = assemble()
    assert all(b == 0xFF for b in out[ORG:ORG + len(code)]), "target ROM space not free"
    out[ORG:ORG + len(code)] = code
    for addr, orig, new in HOOKS + list(extra_hooks):
        assert out[addr:addr + len(orig)] == orig, "unexpected bytes at %#x" % addr
        assert len(new) == len(orig)
        out[addr:addr + len(new)] = new
    return out

def fix_checksum(rom):
    s = sum(struct.unpack(">%dH" % ((len(rom) - 0x200) // 2), rom[0x200:])) & 0xFFFF
    rom[0x18E:0x190] = struct.pack(">H", s)

def ips(orig, new):
    out, i = bytearray(b"PATCH"), 0
    while i < len(orig):
        if orig[i] != new[i]:
            j = i
            while j < len(orig) and orig[j] != new[j] and j - i < 0xFFFF:
                j += 1
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
    new = build(rom, STEAM_ROM_HOOKS)
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
    args = ap.parse_args()
    TICK_HZ = args.hz
    if args.steam:
        build_steam(args.steam)
        sys.exit(0)
    rom = SRC.read_bytes()
    if hashlib.sha1(rom).hexdigest() != SHA1:
        sys.exit("unexpected ROM (need Rev A, sha1 %s)" % SHA1)
    new = build(rom)
    fix_checksum(new)
    OUT.write_bytes(new)
    IPS.write_bytes(ips(rom, new))
    print("wrote", OUT.name, "and", IPS.name)
