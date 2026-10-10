"""Extract the original's per-height wall column routines (tables at $4392 / $4436):
for each even height, the rows it writes as (texture 1=top/2=bottom, byte offset, shade index or None)."""
import struct, capstone, re, os
ROM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Zero Tolerance (USA, Europe) (Rev A).gen")
rom = open(ROM, "rb").read()
md = capstone.Cs(capstone.CS_ARCH_M68K, capstone.CS_MODE_M68K_000)

def interpret(addr):
    rows, shade, ptr, d0 = [], None, {1: 0, 2: 0}, None
    started = False
    for ins in md.disasm(rom[addr:addr + 6000], addr):
        m, op = ins.mnemonic, ins.op_str
        if m == "jsr" and not started:          # background fill above the wall
            continue
        if m.startswith("movea") and "(a7), a3" in op: continue
        if m.startswith("movea") and "(a6), a3" in op:
            shade = (0x7176 - int(re.search(r"-\$([0-9a-f]+)\(a6\)", op).group(1), 16)) // 4; continue
        if m in ("rts", "jmp") or (m == "jsr" and started): break
        r = re.match(r"(addq|subq|adda|suba)\.[wl]$", m)
        if r:
            mm = re.match(r"#\$?([0-9a-f]+), a([12])$", op)
            if mm:
                v = int(mm.group(1), 16) if "$" in op else int(mm.group(1))
                ptr[int(mm.group(2))] += v if r.group(1) in ("addq", "adda") else -v
            continue
        if m.startswith("lea"):
            mm = re.match(r"\$?(-?[0-9a-f]+)\(a([12])\), a([12])$", op)
            if mm and mm.group(2) == mm.group(3):
                ptr[int(mm.group(2))] += int(mm.group(1), 16)
            continue
        if not m.startswith("move.b"): continue
        src, dst = op.rsplit(", ", 1)
        def read(s):
            r = re.match(r"(?:\$([0-9a-f]+))?\(a([12])\)(\+?)$", s)
            if not r: return None
            n = int(r.group(2)); off = int(r.group(1) or "0", 16) + ptr[n]
            if r.group(3): ptr[n] += 1
            return (n, off)
        if dst == "d0":
            d0 = read(src); continue
        if dst == "(a0)":
            started = True
            if src == "d0": rows.append((*d0, None))
            elif src.startswith("(a3, d0"): rows.append((*d0, shade))
            else:
                r = read(src)
                if r: rows.append((*r, None))
    return rows

def extract(table):
    return {h: interpret(struct.unpack(">I", rom[table + h * 2:table + h * 2 + 4])[0]) for h in range(2, 81, 2)}

if __name__ == "__main__":
    t = extract(0x4392)
    print("heights where rows != h:", [(h, len(r)) for h, r in t.items() if len(r) != h])
    for h in (24, 42, 64, 80):
        r = t[h]; print(h, len(r), r[:5], "...", r[-3:])
