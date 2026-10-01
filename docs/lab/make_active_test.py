"""DEFINITIVE experiment: does swapping a masad NPC to a creature masad ACTIVELY spawns
(Orenian Scout - a live +Monster placement, def loaded) work without freezing?
EQUAL-LENGTH, no padding, no door hop, no unlinks - the minimal clean test. masad has a width-13
clean NPC slot? If 'Orenian Scout' (13) fits an equal-width clean masad peaceful slot, swap exactly
one. Standing test rules: skip_tutorial + 1 HP so you can reach/fight fast. You START in masad, so
no transition needed to see it.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-ACTIVETEST.iso")
PAC=(b"+Hidden",b'"turn hostile"\t0',b'"wait for go"',b'"show/hide"\t0')

def _ranges(): return rc._BOSS_GAUNTLET_RANGES

def t_active(blob, rng):
    rep=rc.Report("active_test")
    ranges=_ranges()
    def lvl_at(off):
        for name,s,e in ranges:
            if s<=off<e: return name
        return None
    out=bytearray(blob)
    _m,peaceful=rc._analyse_enemies(blob)
    NEW=b"Orenian Scout"   # 13, an ACTIVE +Monster creature in masad (def loaded)
    for r in peaceful:
        if lvl_at(r['start'])!="masad": continue
        seg=blob[r['start']:r['end']]
        if any(p in seg for p in PAC): continue
        if len(r['char'])!=len(NEW): continue   # EQUAL LENGTH, no padding
        a,b=r['char_abs']
        if bytes(out[a:b])!=r['char']: continue
        was=r['char'].decode('latin-1')
        out[a:b]=NEW
        rep.changed+=1
        rep.notes.append(f"masad: '{was}' -> 'Orenian Scout' (equal len 13, active creature)")
        break
    if rep.changed==0:
        rep.notes.append("no equal-width-13 clean masad slot found")
    return bytes(out),rep

rc.TRANSFORMS["active_test"]=t_active
res=rc.randomize_iso(SRC,OUT,"ACT1",["active_test","enemy_hp_set"],
                     progress=lambda m:print(" ",m),
                     options={"enemy_hp_set":{"value":1}},
                     binary_patches=[["skip_intro",{}],["skip_tutorial",{}]])
print("size preserved:",res.get("size_preserved"))
for rp in res.get("reports",[]):
    for n in rp.get("notes",[]): print("   ",n)
print("OUT:",OUT)
