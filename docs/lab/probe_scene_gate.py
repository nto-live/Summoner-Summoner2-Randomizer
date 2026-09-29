"""Q1/Q2 follow-up: the popup-dismiss helper sub_0023d5f0 has THREE callers.
Two are OUTSIDE the tutorial file, in the 0x0022xxxx scene/boot state machine
(0x002294b0, 0x0022a1e0). Those are the ones that make the OPENING SCENE wait on
the tutorial. Disassemble the context around each caller, and around the
gp-0x44cc reads at 0x0022a3ec/0x0022a3f4 (the scene polling the tutorial state
counter), to show what the scene checks and how the dispatcher's every-frame
advance (PATCH A) satisfies it while a hidden popup (PATCH B) does not.

Also decode pad_poll (0x0011aac0) enough to state its return contract.

READ-ONLY. Prints only.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

NAMED = {
    0x001F10A8: "flag_is_set", 0x001F11E8: "flag_set", 0x001DBF50: "remove_object",
    0x0023d618: "ngps_process_tutorial", 0x0023d780: "ngps_render_tutorial",
    0x0023d5a8: "ngps_init_tutorial", 0x0023d5b0: "popup_activate",
    0x0023d5f0: "popup_dismiss/advance", 0x0011aac0: "pad_poll", 0x001b36e0: "ui_sound",
}

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def rn(n):
    return "$" + REG[n & 31]


def sx16(i):
    return i - 0x10000 if i & 0x8000 else i


loc = binary.find_elf(ISO)
with ISO.open("rb") as fh:
    fh.seek(loc.iso_offset + loc.seg_offset)
    SEG = fh.read(loc.seg_filesz)
LO, HI = loc.seg_vaddr, loc.seg_vaddr + loc.seg_filesz


def word_at(va):
    return struct.unpack_from("<I", SEG, va - loc.seg_vaddr)[0]


def iso_off(va):
    return binary.va_to_iso_offset(va, loc)


def cstr(va, n=48):
    if not (LO <= va < HI):
        return None
    o = va - loc.seg_vaddr
    e = SEG.find(b"\x00", o, o + n)
    if e < 0:
        return None
    try:
        return SEG[o:e].decode("ascii")
    except UnicodeDecodeError:
        return None


def line(va, w, regf, lui):
    op = w >> 26
    rs, rt, rd = (w >> 21) & 31, (w >> 16) & 31, (w >> 11) & 31
    imm = w & 0xFFFF
    simm = sx16(imm)
    if w == 0:
        return "nop", ""
    if w == 0x03E00008:
        return "jr $ra", ""
    if op == 0x00:
        f = w & 0x3F
        sa = (w >> 6) & 31
        if f == 0x08:
            return f"jr {rn(rs)}", ""
        if f == 0x09:
            return f"jalr {rn(rd)}, {rn(rs)}", "  -> (indirect)"
        if f == 0x21:
            return f"addu {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        if f == 0x25:
            return f"or {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        if f == 0x2D:
            return f"daddu {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        if f == 0x00:
            return f"sll {rn(rd)}, {rn(rt)}, {sa}", ""
        if f == 0x2A:
            return f"slt {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        if f == 0x2B:
            return f"sltu {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        if f == 0x0A:
            return f"movz {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        if f == 0x0B:
            return f"movn {rn(rd)}, {rn(rs)}, {rn(rt)}", ""
        return f"special funct={f:#x}", ""
    if op == 0x02:
        t = ((w & 0x03FFFFFF) << 2) | ((va + 4) & 0xF0000000)
        return f"j {t:#010x}", ""
    if op == 0x03:
        t = ((w & 0x03FFFFFF) << 2) | ((va + 4) & 0xF0000000)
        nm = NAMED.get(t, f"sub_{t:08x}")
        return f"jal {t:#010x}", f"  -> {nm}"
    if op == 0x01:
        tva = va + 4 + (simm << 2)
        sub = {0x00: "bltz", 0x01: "bgez", 0x11: "bgezal"}.get(rt, f"regimm{rt:#x}")
        return f"{sub} {rn(rs)}, {tva:#010x}", ""
    if op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15):
        tva = va + 4 + (simm << 2)
        nm = {0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz",
              0x14: "beql", 0x15: "bnel"}[op]
        if op in (0x06, 0x07):
            return f"{nm} {rn(rs)}, {tva:#010x}", ""
        return f"{nm} {rn(rs)}, {rn(rt)}, {tva:#010x}", ""
    if op == 0x09:
        note = ""
        if rs in lui:
            a = (lui[rs] + simm) & 0xFFFFFFFF
            regf[rt] = a
            s = cstr(a)
            note = f"  ; {rn(rt)}=0x{a:08X}" + (f' "{s}"' if s else "")
        return f"addiu {rn(rt)}, {rn(rs)}, {simm:#x}", note
    if op == 0x0F:
        lui[rt] = imm << 16
        return f"lui {rn(rt)}, {imm:#x}", ""
    if op == 0x0D:
        return f"ori {rn(rt)}, {rn(rs)}, {imm:#x}", ""
    if op == 0x0C:
        return f"andi {rn(rt)}, {rn(rs)}, {imm:#x}", ""
    if op == 0x0A:
        return f"slti {rn(rt)}, {rn(rs)}, {simm:#x}", ""
    if op == 0x0B:
        return f"sltiu {rn(rt)}, {rn(rs)}, {simm:#x}", ""
    if op == 0x08:
        return f"addi {rn(rt)}, {rn(rs)}, {simm:#x}", ""
    loads = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu",
             0x27: "lwu", 0x37: "ld"}
    stores = {0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x3F: "sd"}
    if op in loads:
        gp = f"   ; gp{simm:+#x}" if rs == 28 else ""
        return f"{loads[op]} {rn(rt)}, {simm:#x}({rn(rs)})", gp
    if op in stores:
        gp = f"   ; gp{simm:+#x} WRITE" if rs == 28 else ""
        return f"{stores[op]} {rn(rt)}, {simm:#x}({rn(rs)})", gp
    return f"op={op:#x} raw=0x{w:08X}", ""


def dump(name, entry, end, marks=None):
    marks = marks or {}
    print("\n" + "=" * 84)
    print(f"{name}  {entry:#010x}..{end:#010x}  (ISOoff {iso_off(entry):#x})")
    print("=" * 84)
    regf, lui = {}, {}
    for va in range(entry, end, 4):
        w = word_at(va)
        text, note = line(va, w, regf, lui)
        mark = ("   <<< " + marks[va]) if va in marks else ""
        print(f"  {va:#010x}  {w:08X}  {text}{note}{mark}")


# context around the two non-tutorial callers of popup_dismiss/advance
dump("scene caller #1 of popup_dismiss/advance", 0x00229478, 0x002294d0,
     {0x002294b0: "jal popup_dismiss/advance"})
dump("scene caller #2 of popup_dismiss/advance", 0x0022a1a8, 0x0022a220,
     {0x0022a1e0: "jal popup_dismiss/advance"})

# the scene reads gp-0x44cc (tutorial state counter) at 0x0022a3ec / 0x0022a3f4
dump("scene poll of gp-0x44cc (tutorial state counter)", 0x0022a3c8, 0x0022a430,
     {0x0022a3ec: "lw gp-0x44cc", 0x0022a3f4: "lw gp-0x44cc"})

# pad_poll return contract
dump("pad_poll", 0x0011aac0, 0x0011ab30)
