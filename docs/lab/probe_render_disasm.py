"""Disassemble ngps_render_tutorial (0x0023d780) and resolve its call graph.

READ-ONLY. Does not touch the game or the build. Adds nothing but its own output.

Purpose (see the task brief): find WHICH jal inside ngps_render_tutorial is the
popup-box draw call, so it could be nop'd to remove only the popup while leaving
the scene/flag work intact. The `hide_tutorials` patch currently early-returns the
WHOLE render function; if render also does real work (early-returning it froze the
opening), we need to be surgical instead.

Strategy:
  1. Disassemble ngps_render_tutorial from 0x0023d780 to the next function boundary.
     Boundary = first of: the next known 0x0023d... symbol above the start, OR a
     `jr $ra` + delay slot epilogue.
  2. Resolve every jal target (absolute = (instr & 0x03FFFFFF) << 2) and jalr.
  3. Disassemble each distinct callee's first ~6 instructions and estimate its size.
  4. Flag callees whose prologue builds an address in the tutorial string block
     (~0x0012f39000..0x0012f3a900) via a lui/addiu pair -> popup-text draw.

Minimal inline MIPS (r5900, LE) decoder; uses capstone if importable.
"""
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")

# Known ngps_tutorial.o symbols (from the embedded ELF map file).
SYMBOLS = {
    0x0023c868: "do_basic_controls_tutorial",
    0x0023ccc0: "do_basic_combat_tutorial_part1",
    0x0023d040: "do_chain_attack_tutorial",
    0x0023d0f0: "do_level_up_tutorial_part1",
    0x0023d420: "do_ring_tutorial_part1",
    0x0023d5a8: "ngps_init_tutorial",
    0x0023d618: "ngps_process_tutorial",
    0x0023d780: "ngps_render_tutorial",
}

RENDER_START = 0x0023d780

# Tutorial popup string block (task brief). A lui/addiu pair landing in here near a
# jal is the popup-text draw.
STRBLOCK_LO = 0x0012f39000
STRBLOCK_HI = 0x0012f3a900

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def r(n):
    return "$" + REG[n & 31]


loc = binary.find_elf(ISO)


def read_words(va, n):
    off = binary.va_to_iso_offset(va, loc)
    with ISO.open("rb") as fh:
        fh.seek(off)
        raw = fh.read(4 * n)
    return off, [struct.unpack_from("<I", raw, i * 4)[0] for i in range(n)]


def sx16(imm):
    return imm - 0x10000 if imm & 0x8000 else imm


# --------------------------------------------------------------------------- #
# minimal MIPS decoder
# --------------------------------------------------------------------------- #
def decode(va, w):
    """Return (text, kind, target) for one instruction.

    kind in {'jal','jalr','jr','branch','lui','addiu','load','store','nop','other'}
    target is the absolute jal target VA, or None.
    """
    if w == 0:
        return "nop", "nop", None
    op = w >> 26
    rs = (w >> 21) & 31
    rt = (w >> 16) & 31
    rd = (w >> 11) & 31
    imm = w & 0xFFFF
    simm = sx16(imm)
    target = None

    if op == 0x00:  # SPECIAL
        funct = w & 0x3F
        sa = (w >> 6) & 31
        if funct == 0x08:
            return f"jr {r(rs)}", ("jr" if rs == 31 else "jr_reg"), None
        if funct == 0x09:
            return f"jalr {r(rd)}, {r(rs)}", "jalr", None
        if funct == 0x21:
            return f"addu {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        if funct == 0x20:
            return f"add {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        if funct == 0x23:
            return f"subu {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        if funct == 0x25:
            return f"or {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        if funct == 0x24:
            return f"and {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        if funct == 0x00:
            return f"sll {r(rd)}, {r(rt)}, {sa}", "other", None
        if funct == 0x02:
            return f"srl {r(rd)}, {r(rt)}, {sa}", "other", None
        if funct == 0x2A:
            return f"slt {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        if funct == 0x2B:
            return f"sltu {r(rd)}, {r(rs)}, {r(rt)}", "other", None
        return f"special funct={funct:#x}", "other", None

    if op == 0x02:  # j
        target = (w & 0x03FFFFFF) << 2
        target |= (va + 4) & 0xF0000000
        return f"j {target:#010x}", "branch", None
    if op == 0x03:  # jal
        target = (w & 0x03FFFFFF) << 2
        target |= (va + 4) & 0xF0000000
        return f"jal {target:#010x}", "jal", target
    if op == 0x01:  # REGIMM (bltz/bgez ...)
        tva = va + 4 + (simm << 2)
        sub = {0x00: "bltz", 0x01: "bgez", 0x10: "bltzal", 0x11: "bgezal"}.get(rt, f"regimm{rt:#x}")
        return f"{sub} {r(rs)}, {tva:#010x}", "branch", None
    if op == 0x04:
        tva = va + 4 + (simm << 2)
        if rs == 0 and rt == 0:
            return f"b {tva:#010x}", "branch", None
        return f"beq {r(rs)}, {r(rt)}, {tva:#010x}", "branch", None
    if op == 0x05:
        tva = va + 4 + (simm << 2)
        return f"bne {r(rs)}, {r(rt)}, {tva:#010x}", "branch", None
    if op == 0x06:
        tva = va + 4 + (simm << 2)
        return f"blez {r(rs)}, {tva:#010x}", "branch", None
    if op == 0x07:
        tva = va + 4 + (simm << 2)
        return f"bgtz {r(rs)}, {tva:#010x}", "branch", None
    if op == 0x14:
        tva = va + 4 + (simm << 2)
        return f"beql {r(rs)}, {r(rt)}, {tva:#010x}", "branch", None
    if op == 0x15:
        tva = va + 4 + (simm << 2)
        return f"bnel {r(rs)}, {r(rt)}, {tva:#010x}", "branch", None

    if op == 0x08:
        return f"addi {r(rt)}, {r(rs)}, {simm:#x}", "other", None
    if op == 0x09:
        return f"addiu {r(rt)}, {r(rs)}, {simm:#x}", "addiu", None
    if op == 0x0A:
        return f"slti {r(rt)}, {r(rs)}, {simm:#x}", "other", None
    if op == 0x0B:
        return f"sltiu {r(rt)}, {r(rs)}, {simm:#x}", "other", None
    if op == 0x0C:
        return f"andi {r(rt)}, {r(rs)}, {imm:#x}", "other", None
    if op == 0x0D:
        return f"ori {r(rt)}, {r(rs)}, {imm:#x}", "other", None
    if op == 0x0E:
        return f"xori {r(rt)}, {r(rs)}, {imm:#x}", "other", None
    if op == 0x0F:
        return f"lui {r(rt)}, {imm:#x}", "lui", None

    loads = {0x20: "lb", 0x21: "lh", 0x23: "lw", 0x24: "lbu", 0x25: "lhu",
             0x27: "lwu", 0x37: "ld", 0x1F: "lq"}
    stores = {0x28: "sb", 0x29: "sh", 0x2B: "sw", 0x3F: "sd", 0x1E: "sq"}
    if op in loads:
        return f"{loads[op]} {r(rt)}, {simm:#x}({r(rs)})", "load", None
    if op in stores:
        return f"{stores[op]} {r(rt)}, {simm:#x}({r(rs)})", "store", None
    if op == 0x31:
        return f"lwc1 $f{rt}, {simm:#x}({r(rs)})", "load", None
    if op == 0x39:
        return f"swc1 $f{rt}, {simm:#x}({r(rs)})", "store", None
    if op == 0x11:
        return f"cop1 (fpu) raw=0x{w:08X}", "other", None

    return f"op={op:#x} raw=0x{w:08X}", "other", None


def sym(va):
    if va in SYMBOLS:
        return SYMBOLS[va]
    return f"sub_{va:08x}"


# --------------------------------------------------------------------------- #
# 1. disassemble ngps_render_tutorial to the boundary
# --------------------------------------------------------------------------- #
def next_symbol_boundary(start):
    higher = [a for a in SYMBOLS if a > start]
    return min(higher) if higher else None


def disasm_range(start, max_words, stop_at=None):
    """Disassemble from start; stop at stop_at VA, or one word after jr $ra."""
    off, ws = read_words(start, max_words)
    rows = []
    saw_jr_ra = False
    for i, w in enumerate(ws):
        va = start + i * 4
        if stop_at is not None and va >= stop_at:
            break
        ioff = off + i * 4
        text, kind, tgt = decode(va, w)
        rows.append((va, ioff, w, text, kind, tgt))
        if saw_jr_ra:  # this was the delay slot; end here
            break
        if kind == "jr":
            saw_jr_ra = True
    return rows


print("=" * 78)
print("ELF:", loc.as_dict())
print("=" * 78)

boundary = next_symbol_boundary(RENDER_START)
if boundary is None:
    print(f"\nngps_render_tutorial @ {RENDER_START:#010x}  (no higher known symbol; "
          f"stopping at the jr $ra epilogue)\n")
else:
    print(f"\nngps_render_tutorial @ {RENDER_START:#010x}  (next symbol boundary: "
          f"{boundary:#010x} = {sym(boundary)})\n")

rows = disasm_range(RENDER_START, 512, stop_at=boundary)

lui_state = {}  # rt -> (va, upper<<16)
jal_targets = []       # list of (va, target)
jalr_sites = []        # list of va
strblock_hits = []     # (jal_va, addr, built_from_va)

print(f"{'VA':>10}  {'ISOoff':>8}  {'word':>8}  disasm")
print("-" * 78)
for idx, (va, ioff, w, text, kind, tgt) in enumerate(rows):
    note = ""
    # track lui/addiu pairs to reconstruct addresses
    if kind == "lui":
        rt = (w >> 16) & 31
        lui_state[rt] = (va, (w & 0xFFFF) << 16)
    elif kind == "addiu":
        rs = (w >> 21) & 31
        rt = (w >> 16) & 31
        simm = sx16(w & 0xFFFF)
        if rs in lui_state:
            base_va, upper = lui_state[rs]
            addr = (upper + simm) & 0xFFFFFFFF
            note = f"  ; addr=0x{addr:08X} (lui@{base_va:#x})"
            if STRBLOCK_LO <= addr <= STRBLOCK_HI:
                note += "  <<< TUTORIAL STRING BLOCK"
            if rt != rs:
                lui_state.pop(rs, None)
            lui_state.pop(rt, None) if rt in lui_state and rt != rs else None
    if kind == "jal":
        jal_targets.append((va, tgt))
        note = f"  -> {sym(tgt)}" + note
    if kind == "jalr":
        jalr_sites.append(va)
        note = "  -> (indirect)" + note

    print(f"{va:#010x}  {ioff:8X}  {w:08X}  {text}{note}")

print("-" * 78)
print(f"{len(rows)} instructions, {len(jal_targets)} jal, {len(jalr_sites)} jalr\n")

# --------------------------------------------------------------------------- #
# 2 + 3. distinct callees, prologue peek, string-block detection
# --------------------------------------------------------------------------- #
distinct = []
seen = set()
for va, tgt in jal_targets:
    if tgt not in seen:
        seen.add(tgt)
        distinct.append(tgt)

print("=" * 78)
print("DISTINCT jal CALLEES (first 6 insns each, + string-block scan)")
print("=" * 78)


def guess_role(callee_rows, references_strblock):
    kinds = [k for (_v, _w, _t, k, _tg) in callee_rows]
    if references_strblock:
        return "references TUTORIAL STRING BLOCK -> likely popup text/box draw"
    return None


callee_reports = {}
for tgt in distinct:
    off, ws = read_words(tgt, 6)
    crows = []
    refs_strblock = False
    lstate = {}
    for i, w in enumerate(ws):
        va = tgt + i * 4
        text, kind, ct = decode(va, w)
        if kind == "lui":
            rt = (w >> 16) & 31
            lstate[rt] = (w & 0xFFFF) << 16
        elif kind == "addiu":
            rs = (w >> 21) & 31
            if rs in lstate:
                addr = (lstate[rs] + sx16(w & 0xFFFF)) & 0xFFFFFFFF
                if STRBLOCK_LO <= addr <= STRBLOCK_HI:
                    refs_strblock = True
        crows.append((va, w, off + i * 4, kind, text))
    callee_reports[tgt] = (crows, refs_strblock)

    print(f"\n{sym(tgt)} @ {tgt:#010x}:")
    for (va, w, ioff, kind, text) in crows:
        print(f"  {va:#010x}  {ioff:8X}  {w:08X}  {text}")
    if refs_strblock:
        print("  >>> builds an address inside the tutorial string block")

# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
print("\n" + "=" * 78)
print("SUMMARY: callee list with role guess")
print("=" * 78)
call_order = [(va, tgt) for (va, tgt) in jal_targets]
for va, tgt in call_order:
    crows, refs = callee_reports[tgt]
    role = guess_role(crows, refs) or "(unclassified - inspect)"
    print(f"  jal@{va:#010x} -> {tgt:#010x} {sym(tgt):32} {role}")

print("\nCandidate popup-draw jal sites (reference the tutorial string block, or")
print("their callee does):")
found_any = False
for va, tgt in call_order:
    crows, refs = callee_reports[tgt]
    if refs:
        found_any = True
        print(f"  * jal@{va:#010x} -> {tgt:#010x} {sym(tgt)}")
if not found_any:
    print("  (none via direct lui/addiu in callee prologue - see inline notes above")
    print("   for lui/addiu pairs INSIDE ngps_render_tutorial that hit the block)")

print("\nInline string-block address builds inside ngps_render_tutorial are annotated")
print("with '<<< TUTORIAL STRING BLOCK' in the disassembly above; the jal that")
print("immediately follows such a build is the popup-box draw candidate.")
