"""Disassemble the faulting PCs (0x112ce0 reading 'char'/'mod' text as a pointer; 0x152e5c/0x152f38
walking a placement array) to understand what my $Character edits break. Minimal MIPS decode around
each PC. Read-only (reads the ELF via binary.py)."""
import os, struct, sys
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import binary
ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
loc = binary.find_elf(ISO)
REG=["zero","at","v0","v1","a0","a1","a2","a3","t0","t1","t2","t3","t4","t5","t6","t7","s0","s1","s2","s3","s4","s5","s6","s7","t8","t9","k0","k1","gp","sp","fp","ra"]
def s16(x): return x-0x10000 if x&0x8000 else x
def dis(va,w):
    op=w>>26; rs=(w>>21)&31; rt=(w>>16)&31; rd=(w>>11)&31; sa=(w>>6)&31; fn=w&63; imm=w&0xFFFF; s=s16(imm)
    if w==0: return "nop"
    if op==0:
        return {0x08:f"jr ${REG[rs]}",0x09:f"jalr ${REG[rd]},${REG[rs]}",0x21:f"addu ${REG[rd]},${REG[rs]},${REG[rt]}",0x20:f"add ${REG[rd]},${REG[rs]},${REG[rt]}",0x25:f"or ${REG[rd]},${REG[rs]},${REG[rt]}",0x00:f"sll ${REG[rd]},${REG[rt]},{sa}",0x2a:f"slt ${REG[rd]},${REG[rs]},${REG[rt]}",0x2b:f"sltu ${REG[rd]},${REG[rs]},${REG[rt]}"}.get(fn,f"special fn=0x{fn:02x}")
    if op==0x02: return f"j 0x{(((va+4)&0xF0000000)|((w&0x3FFFFFF)<<2)):08x}"
    if op==0x03: return f"jal 0x{(((va+4)&0xF0000000)|((w&0x3FFFFFF)<<2)):08x}"
    if op==0x04: return f"beq ${REG[rs]},${REG[rt]},0x{va+4+(s<<2):08x}"
    if op==0x05: return f"bne ${REG[rs]},${REG[rt]},0x{va+4+(s<<2):08x}"
    if op==0x09: return f"addiu ${REG[rt]},${REG[rs]},{s}"
    if op==0x0f: return f"lui ${REG[rt]},0x{imm:x}"
    if op==0x23: return f"lw ${REG[rt]},{s}(${REG[rs]})"
    if op==0x2b: return f"sw ${REG[rt]},{s}(${REG[rs]})"
    if op==0x24: return f"lbu ${REG[rt]},{s}(${REG[rs]})"
    if op==0x20: return f"lb ${REG[rt]},{s}(${REG[rs]})"
    if op==0x28: return f"sb ${REG[rt]},{s}(${REG[rs]})"
    if op==0x0c: return f"andi ${REG[rt]},${REG[rs]},0x{imm:x}"
    if op==0x0d: return f"ori ${REG[rt]},${REG[rs]},0x{imm:x}"
    return f"op=0x{op:02x}"
def dump(center,n=10):
    lo=center-16
    off=binary.va_to_iso_offset(lo,loc)
    with ISO.open("rb") as fh: fh.seek(off); raw=fh.read(4*(n+8))
    for i in range(n+8):
        va=lo+i*4; w=struct.unpack_from("<I",raw,i*4)[0]
        mark="  <== FAULT" if va==center else ""
        print(f"  0x{va:08x}: {dis(va,w)}{mark}")
for pc in (0x112ce0, 0x152e5c, 0x152f38):
    print(f"\n=== around pc=0x{pc:x} ===")
    dump(pc)
