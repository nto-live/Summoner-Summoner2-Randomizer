"""Find every instruction in SLUS_200.74 that touches a gp-relative global.

The game addresses its globals as `op rt, imm(gp)`. A symbol like `iGpffffb224` is
gp + (int32)0xFFFFB224, i.e. the instruction's 16-bit immediate is 0xB224 with rs == $gp (28).
So a whole-image scan for those immediates finds every reader/writer.

  python gp_xref.py b224 b218 b21c b220
"""
import struct
import sys

from dis_va import ISO, find_file

GP = 28
OPS = {0x23: "lw", 0x2B: "sw", 0x21: "lh", 0x25: "lhu", 0x29: "sh", 0x2D: "ld", 0x3F: "sd",
       0x20: "lb", 0x24: "lbu", 0x28: "sb", 0x31: "lwc1", 0x39: "swc1", 0x35: "ldc1", 0x3D: "sdc1"}


def main():
    words = [int(a, 16) for a in sys.argv[1:]] or [0xB224]
    name, elf_off, size = find_file(ISO, "SLUS")
    data = open(ISO, "rb").read(0)  # placeholder, we read slices below
    f = open(ISO, "rb")
    # the ELF's single PT_LOAD: vaddr 0x00100000 -> file offset 0x1000
    seg_off, seg_va, seg_len = elf_off + 0x1000, 0x00100000, size - 0x1000
    print(f"{name}: seg vaddr 0x{seg_va:08X} off 0x{seg_off:X} len {seg_len}")
    f.seek(seg_off)
    code = f.read(seg_len)
    f.close()
    for target in words:
        imm = target & 0xFFFF
        print(f"\n=== gp-relative 0x{target:04X} (imm 0x{imm:04X}, offset {imm - 0x10000}) ===")
        hits = 0
        for off in range(0, len(code) - 4, 4):
            w = struct.unpack("<I", code[off:off + 4])[0]
            op = w >> 26
            rs = (w >> 21) & 0x1F
            if rs != GP or (w & 0xFFFF) != imm:
                continue
            va = seg_va + off
            kind = OPS.get(op)
            if op == 0x03:          # jal - not a gp access, skip
                continue
            if kind is None:
                continue
            rt = (w >> 16) & 0x1F
            print(f"  {va:08X}  {kind:5} ${rt}, {imm - 0x10000}(gp)     0x{w:08X}")
            hits += 1
        print(f"  {hits} hit(s)")


if __name__ == "__main__":
    main()
