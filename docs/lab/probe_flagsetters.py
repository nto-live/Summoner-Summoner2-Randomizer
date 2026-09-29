"""Q3 support: find every code site that BUILDS a pointer to the
masad_dialogue_tutorial_part2a / part2b / part3 flag strings, and classify each
site as a flag_is_set call vs a flag_set call vs other, by looking at the nearest
following jal.

Uses a single linear pass over the code region (fast). READ-ONLY, prints only.

Purpose: prove whether the dialogue flag part2b (which gates the invis-door02
removal) is set by the tutorial code itself or by the dialogue/conversation system
elsewhere. That distinguishes "talk sets a flag the tutorial polls" from "tutorial
sets the flag when it detects a talk".
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

loc = binary.find_elf(ISO)
with ISO.open("rb") as fh:
    fh.seek(loc.iso_offset + loc.seg_offset)
    SEG = fh.read(loc.seg_filesz)
LO = loc.seg_vaddr


def iso_off(va):
    return binary.va_to_iso_offset(va, loc)


def sx16(i):
    return i - 0x10000 if i & 0x8000 else i


def find_str(needle):
    out, s = [], 0
    while True:
        i = SEG.find(needle, s)
        if i < 0:
            break
        out.append(LO + i)
        s = i + 1
    return out


def jtarget(va, w):
    if (w >> 26) != 0x03:
        return None
    return ((w & 0x03FFFFFF) << 2) | ((va + 4) & 0xF0000000)


# Precompute address builds, but ONLY over the code region (VA < 0x00300000) and only
# retaining builds whose completed address lands in the data range where the flag
# strings live (0x01200000..0x01300000). This keeps the pass cheap.
CODE_END_OFF = 0x00300000 - LO   # scan code only
STR_LO, STR_HI = 0x01200000, 0x01300000
builds = {}  # va_of_addiu -> address
lui = {}
for off in range(0, min(CODE_END_OFF, len(SEG) - 3), 4):
    w = struct.unpack_from("<I", SEG, off)[0]
    op = w >> 26
    if op == 0x0F:
        lui[(w >> 16) & 31] = (w & 0xFFFF) << 16
    elif op == 0x09:  # addiu
        rs = (w >> 21) & 31
        if rs in lui:
            a = (lui[rs] + sx16(w & 0xFFFF)) & 0xFFFFFFFF
            if STR_LO <= a < STR_HI:
                builds[LO + off] = a
    elif op == 0x0D:  # ori
        rs = (w >> 21) & 31
        if rs in lui:
            a = (lui[rs] | (w & 0xFFFF)) & 0xFFFFFFFF
            if STR_LO <= a < STR_HI:
                builds[LO + off] = a


def next_jal_after(va, span=8):
    for k in range(1, span + 1):
        w = struct.unpack_from("<I", SEG, (va - LO) + k * 4)[0]
        t = jtarget(va + k * 4, w)
        if t is not None:
            return va + k * 4, t
    return None, None


NAMES = {FLAG_IS_SET: "flag_is_set", FLAG_SET: "flag_set"}

for label in (b"masad_dialogue_tutorial_part2a\x00", b"masad_dialogue_tutorial_part2b\x00",
              b"masad_dialogue_tutorial_part3\x00"):
    name = label.rstrip(b"\x00").decode()
    svas = set(find_str(label))
    print(f'\n=== "{name}" string at {[hex(v) for v in svas]} ===')
    hits = [(bva, addr) for bva, addr in builds.items() if addr in svas]
    hits.sort()
    if not hits:
        print("  (no lui/addiu pointer build found)")
        continue
    for bva, addr in hits:
        jva, jt = next_jal_after(bva)
        role = NAMES.get(jt, f"sub_{jt:08x}" if jt else "(no jal nearby)")
        print(f"  build @ {bva:#010x} (ISOoff {iso_off(bva):#x}) -> addr {addr:#010x};"
              f" next jal @ {jva if jva is None else hex(jva)} = {role}")
