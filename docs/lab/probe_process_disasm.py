"""Disassemble ngps_process_tutorial (0x0023d618..0x0023d780) to understand EXACTLY what the
skip_tutorial v3 NOP at 0x0023D74C changes.

v3 = NOP the `beq s0,zero,0x0023d760` at 0x0023D74C. In game v3 = no popups, player CAN move, scene
progresses (desired). hide_tutorials (render-only) = player stays gated. Why? Need to see what s0
is, what the branch skipped, and what now always runs.

Minimal MIPS r5900 LE decoder: enough for branches, jal/jalr/jr, loads/stores, immediates, shifts,
and the gp-relative loads that matter. Read-only.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
loc = binary.find_elf(ISO)

REG = ["zero","at","v0","v1","a0","a1","a2","a3","t0","t1","t2","t3","t4","t5","t6","t7",
       "s0","s1","s2","s3","s4","s5","s6","s7","t8","t9","k0","k1","gp","sp","fp","ra"]


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def dis(va, w):
    op = w >> 26
    rs = (w >> 21) & 31; rt = (w >> 16) & 31; rd = (w >> 11) & 31
    sa = (w >> 6) & 31; fn = w & 63; imm = w & 0xFFFF; simm = s16(imm)
    tgt = ((va + 4) & 0xF0000000) | ((w & 0x03FFFFFF) << 2)
    if w == 0: return "nop"
    if op == 0:
        if fn == 0x08: return f"jr ${REG[rs]}"
        if fn == 0x09: return f"jalr ${REG[rd]},${REG[rs]}"
        if fn == 0x21: return f"addu ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x20: return f"add ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x23: return f"subu ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x25: return f"or ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x24: return f"and ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x2a: return f"slt ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x2b: return f"sltu ${REG[rd]},${REG[rs]},${REG[rt]}"
        if fn == 0x00: return f"sll ${REG[rd]},${REG[rt]},{sa}"
        if fn == 0x02: return f"srl ${REG[rd]},${REG[rt]},{sa}"
        if fn == 0x04: return f"sllv ${REG[rd]},${REG[rt]},${REG[rs]}"
        return f"special fn=0x{fn:02x}"
    if op == 0x02: return f"j 0x{tgt:08x}"
    if op == 0x03: return f"jal 0x{tgt:08x}"
    if op == 0x04: return f"beq ${REG[rs]},${REG[rt]},0x{va+4+(simm<<2):08x}"
    if op == 0x05: return f"bne ${REG[rs]},${REG[rt]},0x{va+4+(simm<<2):08x}"
    if op == 0x06: return f"blez ${REG[rs]},0x{va+4+(simm<<2):08x}"
    if op == 0x07: return f"bgtz ${REG[rs]},0x{va+4+(simm<<2):08x}"
    if op == 0x14: return f"beql ${REG[rs]},${REG[rt]},0x{va+4+(simm<<2):08x}"
    if op == 0x15: return f"bnel ${REG[rs]},${REG[rt]},0x{va+4+(simm<<2):08x}"
    if op == 0x01:
        sub = {0:"bltz",1:"bgez",2:"bltzl",3:"bgezl"}.get(rt, f"regimm{rt}")
        return f"{sub} ${REG[rs]},0x{va+4+(simm<<2):08x}"
    if op == 0x08: return f"addi ${REG[rt]},${REG[rs]},{simm}"
    if op == 0x09: return f"addiu ${REG[rt]},${REG[rs]},{simm}"
    if op == 0x0a: return f"slti ${REG[rt]},${REG[rs]},{simm}"
    if op == 0x0c: return f"andi ${REG[rt]},${REG[rs]},0x{imm:x}"
    if op == 0x0d: return f"ori ${REG[rt]},${REG[rs]},0x{imm:x}"
    if op == 0x0f: return f"lui ${REG[rt]},0x{imm:x}"
    if op == 0x23: return f"lw ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x2b: return f"sw ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x20: return f"lb ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x24: return f"lbu ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x28: return f"sb ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x37: return f"ld ${REG[rt]},{simm}(${REG[rs]})"
    if op == 0x3f: return f"sd ${REG[rt]},{simm}(${REG[rs]})"
    return f"op=0x{op:02x}"


def dump(lo, hi, mark=()):
    off = binary.va_to_iso_offset(lo, loc)
    with ISO.open("rb") as fh:
        fh.seek(off)
        raw = fh.read(hi - lo)
    for i in range(0, hi - lo, 4):
        va = lo + i
        w = struct.unpack_from("<I", raw, i)[0]
        m = "  <== v3 NOPs this" if va in mark else ""
        print(f"  0x{va:08x}: 0x{w:08X}  {dis(va, w)}{m}")


print("=== ngps_process_tutorial 0x0023d618 .. 0x0023d780 ===")
dump(0x0023d618, 0x0023d780, mark=(0x0023d74c,))
