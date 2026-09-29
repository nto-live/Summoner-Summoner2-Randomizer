"""Q1/Q2 deep probe: disassemble the tutorial step function(s) that call the
object-removal fn 0x001DBF50 near the "masad_dialogue_tutorial_*" flag names, and
resolve every flag_is_set / flag_set argument in that span.

READ-ONLY. Prints only.

The first probe (probe_invisdoor.py) located:
  - "invis-door02" strings at VA 0x012715d0 and 0x0127dcd0
  - jal 0x001DBF50 (object removal) sites INSIDE the tutorial code at
    0x0023cb6c, 0x0023cc04, 0x0023ce54 (do_* tutorial step range 0x0023c868..)
  - a "masad_dialogue_tutorial_part2b" pointer built @0x23cb2c right before 0x23cb6c

Here we disassemble the whole enclosing function(s) so we can SEE which jal builds the
"invis-door02" pointer, and which flag_is_set gate precedes it. We locate the function
prologue by walking back to `addiu sp,sp,-N`, and the epilogue by `jr $ra`.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

FLAG_IS_SET = 0x001F10A8
FLAG_SET = 0x001F11E8
REMOVE_FN = 0x001DBF50
PROXIMITY = 0x00205608  # per brief: proximity/target helper

NAMED = {
    FLAG_IS_SET: "flag_is_set",
    FLAG_SET: "flag_set",
    REMOVE_FN: "remove_object(0x1DBF50)",
    PROXIMITY: "proximity_helper(0x205608)",
    0x0023c868: "do_basic_controls_tutorial",
    0x0023d618: "ngps_process_tutorial",
    0x0023d780: "ngps_render_tutorial",
    0x0023d5a8: "ngps_init_tutorial",
}

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def rname(n):
    return "$" + REG[n & 31]


def sx16(imm):
    return imm - 0x10000 if imm & 0x8000 else imm


loc = binary.find_elf(ISO)
with ISO.open("rb") as fh:
    fh.seek(loc.iso_offset + loc.seg_offset)
    SEG = fh.read(loc.seg_filesz)
SEG_VA_LO = loc.seg_vaddr
SEG_VA_HI = loc.seg_vaddr + loc.seg_filesz


def word_at(va):
    return struct.unpack_from("<I", SEG, va - loc.seg_vaddr)[0]


def iso_off(va):
    return binary.va_to_iso_offset(va, loc)


def read_cstr(va, maxlen=80):
    if not (SEG_VA_LO <= va < SEG_VA_HI):
        return None
    off = va - loc.seg_vaddr
    end = SEG.find(b"\x00", off, off + maxlen)
    if end < 0:
        return None
    try:
        return SEG[off:end].decode("ascii")
    except UnicodeDecodeError:
        return None


def jal_target(va, w):
    if (w >> 26) != 0x03:
        return None
    t = (w & 0x03FFFFFF) << 2
    return t | ((va + 4) & 0xF0000000)


def find_prologue(va_in_fn, limit=800):
    """Walk back to the nearest `addiu sp,sp,-N` (function entry)."""
    for va in range(va_in_fn, va_in_fn - limit * 4, -4):
        w = word_at(va)
        # addiu sp,sp,-N : op=0x09 rs=29 rt=29 imm<0
        if (w >> 26) == 0x09 and ((w >> 21) & 31) == 29 and ((w >> 16) & 31) == 29 \
                and (w & 0x8000):
            return va
    return None


def find_epilogue(start_va, limit=1200):
    """Walk forward to `jr $ra`; return VA of the delay slot after it."""
    for va in range(start_va, start_va + limit * 4, 4):
        w = word_at(va)
        if w == 0x03E00008:  # jr $ra
            return va + 4
    return None


def disasm_line(va, w, regfile, lui):
    """Decode + track lui/addiu/ori address builds; return (text, note)."""
    op = w >> 26
    rs = (w >> 21) & 31
    rt = (w >> 16) & 31
    rd = (w >> 11) & 31
    imm = w & 0xFFFF
    simm = sx16(imm)
    note = ""
    if w == 0:
        return "nop", ""
    if w == 0x03E00008:
        return "jr $ra", ""
    if op == 0x00:
        funct = w & 0x3F
        sa = (w >> 6) & 31
        if funct == 0x08:
            return f"jr {rname(rs)}", ""
        if funct == 0x09:
            return f"jalr {rname(rd)}, {rname(rs)}", "  -> (indirect)"
        if funct == 0x21:
            return f"addu {rname(rd)}, {rname(rs)}, {rname(rt)}", ""
        if funct == 0x25:
            return f"or {rname(rd)}, {rname(rs)}, {rname(rt)}", ""
        if funct == 0x00 and w != 0:
            return f"sll {rname(rd)}, {rname(rt)}, {sa}", ""
        if funct == 0x2A:
            return f"slt {rname(rd)}, {rname(rs)}, {rname(rt)}", ""
        if funct == 0x2B:
            return f"sltu {rname(rd)}, {rname(rs)}, {rname(rt)}", ""
        return f"special funct={funct:#x}", ""
    if op == 0x02:
        t = (w & 0x03FFFFFF) << 2 | ((va + 4) & 0xF0000000)
        return f"j {t:#010x}", ""
    if op == 0x03:
        t = jal_target(va, w)
        nm = NAMED.get(t, f"sub_{t:08x}")
        note = f"  -> {nm}"
        # annotate current arg regs
        args = []
        for ar in (4, 5, 6, 7):
            if ar in regfile:
                addr, _bva = regfile[ar]
                s = read_cstr(addr)
                if s is not None:
                    args.append(f'{rname(ar)}="{s}"')
                else:
                    args.append(f"{rname(ar)}=0x{addr:08X}")
        if args:
            note += "   [" + ", ".join(args) + "]"
        return f"jal {t:#010x}", note
    if op == 0x01:
        tva = va + 4 + (simm << 2)
        sub = {0x00: "bltz", 0x01: "bgez"}.get(rt, f"regimm{rt:#x}")
        return f"{sub} {rname(rs)}, {tva:#010x}", ""
    if op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15):
        tva = va + 4 + (simm << 2)
        nm = {0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz",
              0x14: "beql", 0x15: "bnel"}[op]
        if op in (0x04, 0x05, 0x14, 0x15):
            return f"{nm} {rname(rs)}, {rname(rt)}, {tva:#010x}", ""
        return f"{nm} {rname(rs)}, {tva:#010x}", ""
    if op == 0x08:
        return f"addi {rname(rt)}, {rname(rs)}, {simm:#x}", ""
    if op == 0x09:  # addiu
        if rs in lui:
            addr = (lui[rs] + simm) & 0xFFFFFFFF
            regfile[rt] = (addr, va)
            s = read_cstr(addr)
            note = f"  ; {rname(rt)}=0x{addr:08X}" + (f' "{s}"' if s else "")
        return f"addiu {rname(rt)}, {rname(rs)}, {simm:#x}", note
    if op == 0x0C:
        return f"andi {rname(rt)}, {rname(rs)}, {imm:#x}", ""
    if op == 0x0D:  # ori
        if rs in lui:
            addr = (lui[rs] | imm) & 0xFFFFFFFF
            regfile[rt] = (addr, va)
            note = f"  ; {rname(rt)}=0x{addr:08X}"
        return f"ori {rname(rt)}, {rname(rs)}, {imm:#x}", note
    if op == 0x0F:  # lui
        lui[rt] = imm << 16
        regfile.pop(rt, None)
        return f"lui {rname(rt)}, {imm:#x}", ""
    if op == 0x0A:
        return f"slti {rname(rt)}, {rname(rs)}, {simm:#x}", ""
    if op == 0x0B:
        return f"sltiu {rname(rt)}, {rname(rs)}, {simm:#x}", ""
    loads = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu",
             0x27: "lwu", 0x37: "ld", 0x1F: "lq"}
    stores = {0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x3F: "sd", 0x1E: "sq"}
    if op in loads:
        return f"{loads[op]} {rname(rt)}, {simm:#x}({rname(rs)})", ""
    if op in stores:
        return f"{stores[op]} {rname(rt)}, {simm:#x}({rname(rs)})", ""
    return f"op={op:#x} raw=0x{w:08X}", ""


def dump_function(name, entry, end):
    print("\n" + "=" * 78)
    print(f"{name}  entry {entry:#010x}  end {end:#010x}  (ISOoff {iso_off(entry):#x})")
    print("=" * 78)
    regfile = {}
    lui = {}
    for va in range(entry, end, 4):
        w = word_at(va)
        text, note = disasm_line(va, w, regfile, lui)
        marker = ""
        t = jal_target(va, w)
        if t in (FLAG_IS_SET, FLAG_SET, REMOVE_FN):
            marker = "  <<<"
        print(f"  {va:#010x}  {word_at(va):08X}  {text}{note}{marker}")


# The three tutorial-region removal call sites and their neighbours.
for site in (0x0023cb6c, 0x0023cc04, 0x0023ce54):
    pro = find_prologue(site)
    epi = find_epilogue(pro) if pro else None
    pro_s = f"{pro:#010x}" if pro else "None"
    epi_s = f"{epi:#010x}" if epi else "None"
    print(f"\n### removal call at {site:#010x}: prologue={pro_s}, epilogue_end={epi_s}")

# Instead of per-site, dump the whole contiguous span that contains all three,
# from the prologue before the first to the epilogue after the last.
p0 = find_prologue(0x0023cb6c)
e2 = find_epilogue(0x0023ce54)
print(f"\nspanning prologue {p0:#010x} .. epilogue_end {e2:#010x}")
dump_function("do_*_dialogue_tutorial span", p0, e2)
