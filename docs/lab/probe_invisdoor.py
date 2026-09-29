"""Q1/Q2 probe: trace what removes the burning-village fire barrier "invis-door02".

READ-ONLY. Touches neither the game nor the build; only prints analysis.

Plan:
  1. Locate every occurrence of the ASCII string "invis-door02" inside the loadable
     segment of SLUS_200.74. Report VA + ISO offset for each.
  2. Scan the whole code segment for `jal 0x001DBF50` (the door/object removal fn the
     brief names) and for `jal` sites whose lui/addiu address-build points AT an
     "invis-door02" string. Correlate the two: the call site that builds the string
     pointer in $a0..$a3 shortly before a `jal 0x001DBF50` is the removal call.
  3. For each such call site, walk BACKWARD to the function prologue (addiu sp,sp,-N)
     to name the containing function span, and forward/backward collect every
     `jal 0x001F10A8` (flag_is_set) and `jal 0x001F11E8` (flag_set) in that function,
     resolving the string argument each one is handed (the flag name).

Everything uses src/binary.py exactly like probe_render_bytes.py / probe_render_disasm.py.
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

REG = ["zero", "at", "v0", "v1", "a0", "a1", "a2", "a3",
       "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
       "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
       "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"]


def rname(n):
    return "$" + REG[n & 31]


def sx16(imm):
    return imm - 0x10000 if imm & 0x8000 else imm


loc = binary.find_elf(ISO)
SEG_VA_LO = loc.seg_vaddr
SEG_VA_HI = loc.seg_vaddr + loc.seg_filesz


def load_segment():
    with ISO.open("rb") as fh:
        fh.seek(loc.iso_offset + loc.seg_offset)
        return fh.read(loc.seg_filesz)


SEG = load_segment()


def va_of_seg_index(i):
    return loc.seg_vaddr + i


def word_at_va(va):
    off = va - loc.seg_vaddr
    return struct.unpack_from("<I", SEG, off)[0]


def iso_off(va):
    return binary.va_to_iso_offset(va, loc)


# --------------------------------------------------------------------------- #
# 1. find the string(s)
# --------------------------------------------------------------------------- #
def find_string_vas(needle: bytes):
    hits = []
    start = 0
    while True:
        i = SEG.find(needle, start)
        if i < 0:
            break
        # require NUL-terminated (a real C string), preceded by NUL or printable
        end = i + len(needle)
        term_ok = end < len(SEG) and SEG[end] == 0
        hits.append((va_of_seg_index(i), i, term_ok))
        start = i + 1
    return hits


TARGET = b"invis-door02"
str_hits = find_string_vas(TARGET)

print("=" * 78)
print("ELF:", loc.as_dict())
print(f"segment VA range: {SEG_VA_LO:#010x} .. {SEG_VA_HI:#010x}")
print("=" * 78)
print(f'\n[1] occurrences of "{TARGET.decode()}":')
str_va_set = set()
for va, idx, term in str_hits:
    print(f"  VA {va:#010x}  ISOoff {iso_off(va):#x}  nul_terminated={term}")
    str_va_set.add(va)
if not str_hits:
    print("  (none found as a contiguous NUL-region string)")


# --------------------------------------------------------------------------- #
# 2. scan the code for jal REMOVE_FN and for address-builds of the string
# --------------------------------------------------------------------------- #
def jal_target(va, w):
    if (w >> 26) != 0x03:
        return None
    t = (w & 0x03FFFFFF) << 2
    t |= (va + 4) & 0xF0000000
    return t


def scan_jal(target_fn):
    sites = []
    # scan word-aligned over the segment
    for off in range(0, len(SEG) - 3, 4):
        w = struct.unpack_from("<I", SEG, off)[0]
        va = loc.seg_vaddr + off
        t = jal_target(va, w)
        if t == target_fn:
            sites.append(va)
    return sites


print(f"\n[2] scanning code segment for jal {REMOVE_FN:#010x} ...")
remove_sites = scan_jal(REMOVE_FN)
print(f"  {len(remove_sites)} call site(s) to {REMOVE_FN:#010x}:")
for va in remove_sites:
    print(f"    jal@{va:#010x}  (ISOoff {iso_off(va):#x})")


# --------------------------------------------------------------------------- #
# helper: reconstruct address builds (lui rt, hi ; addiu rt, rt, lo) preceding a VA
# --------------------------------------------------------------------------- #
def track_addr_builds(start_va, back_words=40):
    """Walk back from start_va, emulate lui/addiu/ori into a register file,
    return {reg: (addr, built_at_va)} snapshot as it stood entering start_va."""
    regs = {}
    lui = {}
    lo = start_va - back_words * 4
    for va in range(lo, start_va, 4):
        w = word_at_va(va)
        op = w >> 26
        rs = (w >> 21) & 31
        rt = (w >> 16) & 31
        imm = w & 0xFFFF
        if op == 0x0F:  # lui
            lui[rt] = imm << 16
            regs[rt] = (imm << 16, va)
        elif op == 0x09:  # addiu
            if rs in lui:
                addr = (lui[rs] + sx16(imm)) & 0xFFFFFFFF
                regs[rt] = (addr, va)
        elif op == 0x0D:  # ori
            if rs in lui:
                addr = (lui[rs] | imm) & 0xFFFFFFFF
                regs[rt] = (addr, va)
    return regs


def read_cstr(va, maxlen=64):
    if not (SEG_VA_LO <= va < SEG_VA_HI):
        return None
    off = va - loc.seg_vaddr
    end = SEG.find(b"\x00", off, off + maxlen)
    if end < 0:
        return None
    raw = SEG[off:end]
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError:
        return None


# For each remove-fn call site, what string address is in a0 (reg 4) entering it?
print(f"\n[3] argument to each jal {REMOVE_FN:#010x} (address built in registers just before):")
for va in remove_sites:
    regs = track_addr_builds(va, back_words=30)
    a0 = regs.get(4)
    note = ""
    if a0:
        s = read_cstr(a0[0])
        note = f"a0=0x{a0[0]:08X}"
        if s is not None:
            note += f'  -> "{s}"'
        if a0[0] in str_va_set:
            note += "   <<< invis-door02"
    else:
        note = "a0 not built via lui/addiu in the preceding 30 words (maybe passed in / from stack)"
    print(f"  jal@{va:#010x}: {note}")
    # dump all register builds for context
    for rg in sorted(regs):
        addr, bva = regs[rg]
        s = read_cstr(addr)
        extra = f'  "{s}"' if s else ""
        print(f"      {rname(rg):>5} = 0x{addr:08X} (built @{bva:#x}){extra}")
