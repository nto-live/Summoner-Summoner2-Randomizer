"""Q1/Q2 crux probe: find every reader/writer of the tutorial-popup pointer
gp-0x3a58 and the frame timer gp-0x335c / gp-0x3360, and look for a player-input
lock that is held WHILE a popup is active. This is what decides whether NOPing
0x0023d74c (which makes sub_0023d5f0 zero gp-0x3a58 every frame) unfreezes the
player, and why the render-only patch does not.

Also: identify the activation site — which do_* step writes gp-0x3a58 (activates a
popup). The dispatcher's sub_0023d5b0 writes it from an argument; find who calls
sub_0023d5b0 with which step index, and who sets the "waits for input" field +4 of
the popup struct.

READ-ONLY. Prints only.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

loc = binary.find_elf(ISO)
with ISO.open("rb") as fh:
    fh.seek(loc.iso_offset + loc.seg_offset)
    SEG = fh.read(loc.seg_filesz)
LO, HI = loc.seg_vaddr, loc.seg_vaddr + loc.seg_filesz


def iso_off(va):
    return binary.va_to_iso_offset(va, loc)


def sx16(i):
    return i - 0x10000 if i & 0x8000 else i


REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def rn(n):
    return "$" + REG[n & 31]


# --------------------------------------------------------------------------- #
# 1. every gp-relative access to the three tutorial-popup globals
# --------------------------------------------------------------------------- #
# gp-relative load/store: rs==28 (gp). We match on the signed imm.
TARGETS = {
    -0x3a58: "gp-0x3a58  ACTIVE-POPUP pointer",
    -0x335c: "gp-0x335c  popup frame counter (line index)",
    -0x3360: "gp-0x3360  render 'popup drawn this frame' flag",
    -0x44cc: "gp-0x44cc  tutorial state counter",
    -0x3a70: "gp-0x3a70  ignore-tutorial global",
    -0x558c: "gp-0x558c  tutorial-enabled gate",
    -0x55d8: "gp-0x55d8  current-level handle",
}

LOADS = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu",
         0x27: "lwu", 0x37: "ld"}
STORES = {0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x3F: "sd"}

print("=" * 84)
print("Every gp-relative access to the tutorial-popup globals (whole code segment)")
print("=" * 84)
hits = {k: [] for k in TARGETS}
for off in range(0, len(SEG) - 3, 4):
    w = struct.unpack_from("<I", SEG, off)[0]
    op = w >> 26
    rs = (w >> 21) & 31
    if rs != 28:
        continue
    if op not in LOADS and op not in STORES:
        continue
    simm = sx16(w & 0xFFFF)
    if simm not in TARGETS:
        continue
    va = loc.seg_vaddr + off
    rt = (w >> 16) & 31
    mnem = LOADS.get(op) or STORES.get(op)
    kind = "READ " if op in LOADS else "WRITE"
    hits[simm].append((va, mnem, rn(rt), kind))

for simm, label in TARGETS.items():
    rows = hits[simm]
    print(f"\n{label}   ({len(rows)} accesses)")
    for va, mnem, rt, kind in rows:
        print(f"   {kind}  {va:#010x} (iso {iso_off(va):#x})  {mnem} {rt}, {simm:#x}(gp)")

# --------------------------------------------------------------------------- #
# 2. who calls sub_0023d5b0 (popup activate) and sub_0023d5f0 (popup dismiss)?
# --------------------------------------------------------------------------- #
def jal_callers(target):
    out = []
    enc = 0x0C000000 | ((target >> 2) & 0x03FFFFFF)
    for off in range(0, len(SEG) - 3, 4):
        w = struct.unpack_from("<I", SEG, off)[0]
        if w == enc:
            out.append(loc.seg_vaddr + off)
    return out


print("\n" + "=" * 84)
print("Callers of the popup activate/dismiss helpers")
print("=" * 84)
for tgt, name in ((0x0023d5b0, "sub_0023d5b0 (activate: sw v0,-0x3a58(gp))"),
                  (0x0023d5f0, "sub_0023d5f0 (dismiss: sw zero,-0x3a58(gp))"),
                  (0x0011aac0, "pad_poll"),
                  (0x001b36e0, "ui_sound")):
    callers = jal_callers(tgt)
    print(f"\n{name}  @ {tgt:#010x}  -> {len(callers)} caller(s)")
    for c in callers:
        print(f"   jal from {c:#010x} (iso {iso_off(c):#x})")


# --------------------------------------------------------------------------- #
# 3. pad_poll (0x0011aac0) first instructions — does it return "pressed" bool?
# --------------------------------------------------------------------------- #
def mini(va, n):
    print(f"\n--- {va:#010x} (iso {iso_off(va):#x}) first {n} insns ---")
    for i in range(n):
        w = struct.unpack_from("<I", SEG, (va - loc.seg_vaddr) + i * 4)[0]
        print(f"   {va + i*4:#010x}  {w:08X}")


mini(0x0011aac0, 16)
