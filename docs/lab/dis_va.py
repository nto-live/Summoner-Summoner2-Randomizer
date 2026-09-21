"""Dump instruction words at EE virtual addresses from the ISO's boot ELF.

Address translation (per COMPILED-CODE.md): a single PT_LOAD segment with
vaddr 0x00100000 -> file offset 0x1000. So file offset inside the ELF =
va - 0x00100000 + 0x1000, and the ISO offset = elf_iso_offset + that.
"""
import struct
import sys
from pathlib import Path

ISO = Path(r"F:\rando\S1\iso\Summoner.iso")


def find_file(iso, wanted_prefix):
    with open(iso, "rb") as f:
        f.seek(16 * 2048)
        pvd = f.read(2048)
    root_lba = struct.unpack("<I", pvd[156 + 2:156 + 6])[0]
    root_len = struct.unpack("<I", pvd[156 + 10:156 + 14])[0]
    with open(iso, "rb") as f:
        f.seek(root_lba * 2048)
        data = f.read(root_len)
    i = 0
    while i < len(data):
        ln = data[i]
        if ln == 0:
            i = (i // 2048 + 1) * 2048
            continue
        rec = data[i:i + ln]
        lba = struct.unpack("<I", rec[2:6])[0]
        size = struct.unpack("<I", rec[10:14])[0]
        namelen = rec[32]
        name = rec[33:33 + namelen].decode("latin-1")
        if name.startswith(wanted_prefix):
            return name, lba * 2048, size
        i += ln
    return None, None, None


def main():
    va_list = [int(a, 0) for a in sys.argv[1:]] or [0x0011AAC0]
    name, elf_off, elf_size = find_file(ISO, "SLUS")
    print(f"{name}  iso_off=0x{elf_off:X}  size={elf_size}")
    seg_va, seg_off = 0x00100000, 0x1000
    with open(ISO, "rb") as f:
        for va in va_list:
            fo = elf_off + (va - seg_va) + seg_off
            f.seek(fo)
            raw = f.read(40)
            words = [struct.unpack("<I", raw[i * 4:i * 4 + 4])[0] for i in range(10)]
            print(f"\nva 0x{va:08X}  iso 0x{fo:X}")
            for i, w in enumerate(words):
                print(f"  +0x{i * 4:02X}  0x{w:08X}  {decode(w)}")
            print(f"  raw: {b''.join(struct.pack('<I', w) for w in words).hex()}")


def decode(w):
    """Very small MIPS/R5900 decoder - enough to sanity-check a prologue."""
    op = w >> 26
    rs = (w >> 21) & 0x1F
    rt = (w >> 16) & 0x1F
    rd = (w >> 11) & 0x1F
    sa = (w >> 6) & 0x1F
    fn = w & 0x3F
    imm = w & 0xFFFF
    simm = imm - 0x10000 if imm & 0x8000 else imm
    names = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3",
             "t4", "t5", "t6", "t7", "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
             "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]
    if w == 0:
        return "nop"
    if op == 0x0F:
        return f"lui ${names[rt]}, 0x{imm:04X}"
    if op == 0x09:
        return f"addiu ${names[rt]}, ${names[rs]}, {simm}"
    if op == 0x0D:
        return f"ori ${names[rt]}, ${names[rs]}, 0x{imm:04X}"
    if op == 0x0C:
        return f"andi ${names[rt]}, ${names[rs]}, 0x{imm:04X}"
    if op == 0x23:
        return f"lw ${names[rt]}, {simm}(${names[rs]})"
    if op == 0x2B:
        return f"sw ${names[rt]}, {simm}(${names[rs]})"
    if op == 0x27:
        return f"lwu/ld? ${names[rt]}, {simm}(${names[rs]})"
    if op == 0x2F:
        return f"sd? ${names[rt]}, {simm}(${names[rs]})"
    if op == 0x03:
        return f"jal 0x{(w & 0x3FFFFFF) << 2 | 0x00100000:08X}"
    if op == 0x02:
        return f"j 0x{(w & 0x3FFFFFF) << 2 | 0x00100000:08X}"
    if op == 0x04:
        return f"beq ${names[rs]}, ${names[rt]}, {simm}"
    if op == 0x05:
        return f"bne ${names[rs]}, ${names[rt]}, {simm}"
    if op == 0x06:
        return f"blez ${names[rs]}, {simm}"
    if op == 0x07:
        return f"bgtz ${names[rs]}, {simm}"
    if op == 0x08:
        return f"addi ${names[rt]}, ${names[rs]}, {simm}"
    if op == 0x0A:
        return f"slti ${names[rt]}, ${names[rs]}, {simm}"
    if op == 0x0B:
        return f"sltiu ${names[rt]}, ${names[rs]}, {simm}"
    if op == 0:
        special = {
            0x00: "sll", 0x02: "srl", 0x03: "sra", 0x08: "jr", 0x09: "jalr",
            0x21: "addu", 0x23: "subu", 0x24: "and", 0x25: "or", 0x26: "xor",
            0x27: "nor", 0x2A: "slt", 0x2B: "sltu", 0x18: "mult", 0x1A: "div",
            0x10: "mfhi", 0x12: "mflo", 0x0C: "syscall", 0x0D: "break",
        }
        nm = special.get(fn, f"special(0x{fn:X})")
        if fn == 0x08:
            return f"jr ${names[rs]}"
        if fn in (0x10, 0x12):
            return f"{nm} ${names[rd]}"
        return f"{nm} ${names[rd]}, ${names[rs]}, ${names[rt]}"
    return f"op 0x{op:X}"


if __name__ == "__main__":
    main()
