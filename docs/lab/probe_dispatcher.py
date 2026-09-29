"""Q3 probe: disassemble ngps_process_tutorial (0x0023d618) end-to-end so we can
reason about what the skip_tutorial v3 NOP at 0x0023D74C changes vs retail.

Also: find who SETS the masad_dialogue_tutorial_part2a/part2b/part3 flags — i.e.
scan the whole code segment for flag_set (jal 0x001F11E8) sites whose $a2 argument
resolves to one of those flag-name strings. That tells us whether the dialogue flag
is set by the tutorial code or by the dialogue system elsewhere.

READ-ONLY. Prints only.
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
PROC = 0x0023d618
RENDER = 0x0023d780

NAMED = {
    FLAG_IS_SET: "flag_is_set", FLAG_SET: "flag_set",
    REMOVE_FN: "remove_object", PROC: "ngps_process_tutorial",
    RENDER: "ngps_render_tutorial", 0x0023d5a8: "ngps_init_tutorial",
    0x0023c868: "do_basic_controls_tutorial", 0x0023ccc0: "do_basic_combat_tutorial_part1",
    0x0023d040: "do_chain_attack_tutorial", 0x0023d0f0: "do_level_up_tutorial_part1",
    0x0023d420: "do_ring_tutorial_part1",
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


def cstr(va, n=80):
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


def jtarget(va, w):
    if (w >> 26) != 0x03:
        return None
    return ((w & 0x03FFFFFF) << 2) | ((va + 4) & 0xF0000000)


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
        return f"j {jtarget(va, w | (2 << 26)) if False else ((w & 0x03FFFFFF) << 2) | ((va + 4) & 0xF0000000):#010x}", ""
    if op == 0x03:
        t = jtarget(va, w)
        nm = NAMED.get(t, f"sub_{t:08x}")
        args = []
        for ar in (4, 5, 6, 7):
            if ar in regf:
                a, _ = regf[ar]
                s = cstr(a)
                args.append(f'{rn(ar)}="{s}"' if s else f"{rn(ar)}=0x{a:08X}")
        note = f"  -> {nm}" + ("   [" + ", ".join(args) + "]" if args else "")
        return f"jal {t:#010x}", note
    if op == 0x01:
        tva = va + 4 + (simm << 2)
        sub = {0x00: "bltz", 0x01: "bgez", 0x11: "bgezal"}.get(rt, f"regimm{rt:#x}")
        return f"{sub} {rn(rs)}, {tva:#010x}", ""
    if op in (0x04, 0x05, 0x06, 0x07, 0x14, 0x15):
        tva = va + 4 + (simm << 2)
        nm = {0x04: "beq", 0x05: "bne", 0x06: "blez", 0x07: "bgtz", 0x14: "beql", 0x15: "bnel"}[op]
        if op in (0x06, 0x07):
            return f"{nm} {rn(rs)}, {tva:#010x}", ""
        return f"{nm} {rn(rs)}, {rn(rt)}, {tva:#010x}", ""
    if op == 0x09:
        note = ""
        if rs in lui:
            a = (lui[rs] + simm) & 0xFFFFFFFF
            regf[rt] = (a, va)
            s = cstr(a)
            note = f"  ; {rn(rt)}=0x{a:08X}" + (f' "{s}"' if s else "")
        return f"addiu {rn(rt)}, {rn(rs)}, {simm:#x}", note
    if op == 0x0F:
        lui[rt] = imm << 16
        regf.pop(rt, None)
        return f"lui {rn(rt)}, {imm:#x}", ""
    if op == 0x0D:
        note = ""
        if rs in lui:
            a = (lui[rs] | imm) & 0xFFFFFFFF
            regf[rt] = (a, va)
            note = f"  ; {rn(rt)}=0x{a:08X}"
        return f"ori {rn(rt)}, {rn(rs)}, {imm:#x}", note
    if op == 0x0C:
        return f"andi {rn(rt)}, {rn(rs)}, {imm:#x}", ""
    if op == 0x0A:
        return f"slti {rn(rt)}, {rn(rs)}, {simm:#x}", ""
    if op == 0x0B:
        return f"sltiu {rn(rt)}, {rn(rs)}, {simm:#x}", ""
    if op == 0x08:
        return f"addi {rn(rt)}, {rn(rs)}, {simm:#x}", ""
    loads = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu", 0x27: "lwu", 0x37: "ld", 0x1F: "lq"}
    stores = {0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x3F: "sd", 0x1E: "sq"}
    if op in loads:
        return f"{loads[op]} {rn(rt)}, {simm:#x}({rn(rs)})", ""
    if op in stores:
        return f"{stores[op]} {rn(rt)}, {simm:#x}({rn(rs)})", ""
    return f"op={op:#x} raw=0x{w:08X}", ""


def dump(entry, end):
    print("\n" + "=" * 78)
    print(f"ngps_process_tutorial  {entry:#010x}..{end:#010x}  (ISOoff {iso_off(entry):#x})")
    print("=" * 78)
    regf, lui = {}, {}
    for va in range(entry, end, 4):
        w = word_at(va)
        text, note = line(va, w, regf, lui)
        mark = "   <<< V3 NOP TARGET" if va == 0x0023D74C else ""
        print(f"  {va:#010x}  {w:08X}  {text}{note}{mark}")


# process runs from 0x0023d618 to the render prologue 0x0023d780
dump(PROC, RENDER)


# --------------------------------------------------------------------------- #
# who SETS masad_dialogue_tutorial_part2a/2b/3 ?
# --------------------------------------------------------------------------- #
def find_str(needle):
    out = []
    s = 0
    while True:
        i = SEG.find(needle, s)
        if i < 0:
            break
        out.append(loc.seg_vaddr + i)
        s = i + 1
    return out


print("\n" + "=" * 78)
print("Who references the dialogue-tutorial flag strings (all lui/addiu builds)?")
print("=" * 78)
for nm in (b"masad_dialogue_tutorial_part2a\x00", b"masad_dialogue_tutorial_part2b\x00",
           b"masad_dialogue_tutorial_part3\x00"):
    for sva in find_str(nm):
        label = nm.rstrip(b"\x00").decode()
        print(f'\n"{label}" @ {sva:#010x} (ISOoff {iso_off(sva):#x})')
        hi16 = (sva >> 16) & 0xFFFF
        lo16 = sva & 0xFFFF
        # a matching addiu low would be sva&0xffff possibly with +1 to hi if lo>=0x8000
        # scan for lui rX,hi followed within a few words by addiu rY,rX,lo
        want_hi = hi16 + (1 if lo16 >= 0x8000 else 0)
        want_lo = sx16(lo16)
        refs = []
        for off in range(0, len(SEG) - 3, 4):
            w = struct.unpack_from("<I", SEG, off)[0]
            if (w >> 26) == 0x0F and (w & 0xFFFF) == want_hi:
                lreg = (w >> 16) & 31
                base = loc.seg_vaddr + off
                for k in range(1, 6):
                    w2 = struct.unpack_from("<I", SEG, off + k * 4)[0]
                    if (w2 >> 26) == 0x09 and ((w2 >> 21) & 31) == lreg \
                            and sx16(w2 & 0xFFFF) == want_lo:
                        refs.append(loc.seg_vaddr + off + k * 4)
                        break
        for r in refs:
            print(f"    built @ {r:#010x} (ISOoff {iso_off(r):#x})")
