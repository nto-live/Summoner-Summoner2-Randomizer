"""Replace masad's non-story NPCs with active masad hostiles (prefer Barbarian Fighter), EQUAL
LENGTH only (no padding - padding caused the 'char' TLB freeze). Active masad creatures by width:
  Barbarian Fighter(17), Orenian Soldier1/2(16), Orenian Archer(14), Orenian Scout(13), Village Man3(12)
A non-story NPC = clean (no pacifier) peaceful placement whose $Name is NOT referenced elsewhere
(so no script breaks). For each such slot, swap $Character to an active hostile of EXACT same width.
Standing rules: skip_tutorial + 1 HP. You start in masad.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-MASADBARB.iso")
PAC=(b"+Hidden",b'"turn hostile"\t0',b'"wait for go"',b'"show/hide"\t0')
# active masad hostiles by width (model loaded in masad), hostile team
ACTIVE_BY_W = {17:b"Barbarian Fighter",16:b"Orenian Soldier1",14:b"Orenian Archer",13:b"Orenian Scout"}

def _ranges(): return rc._BOSS_GAUNTLET_RANGES

def t_masadbarb(blob, rng):
    rep=rc.Report("masad_barb")
    ranges=_ranges()
    def lvl_at(off):
        for name,s,e in ranges:
            if s<=off<e: return name
        return None
    out=bytearray(blob)
    _m,peaceful=rc._analyse_enemies(blob)
    swapped=0; skipped_scene=0; skipped_width=0
    for r in peaceful:
        if lvl_at(r['start'])!="masad": continue
        seg=blob[r['start']:r['end']]
        if any(p in seg for p in PAC): continue
        nm=re.search(rb'\$Name\s*:\s*"([^"]+)"', seg)
        if not nm: continue
        # non-story = $Name referenced only by its own placement
        if len(re.findall(re.escape(nm.group(1)), blob))>1:
            skipped_scene+=1; continue
        w=len(r['char'])
        new=ACTIVE_BY_W.get(w)
        if not new:
            skipped_width+=1; continue
        a,b=r['char_abs']
        if bytes(out[a:b])!=r['char']: continue
        out[a:b]=new
        swapped+=1
        rep.notes.append(f"'{nm.group(1).decode()}' ({r['char'].decode()}) -> {new.decode()}")
    rep.changed=swapped
    rep.notes.insert(0,f"masad: {swapped} non-story NPCs -> active hostiles; "
                       f"{skipped_scene} scene-critical skipped; {skipped_width} no-equal-width-creature")
    return bytes(out),rep

rc.TRANSFORMS["masad_barb"]=t_masadbarb
res=rc.randomize_iso(SRC,OUT,"BARB1",["masad_barb","enemy_hp_set"],
                     progress=lambda m:print(" ",m),
                     options={"enemy_hp_set":{"value":1}},
                     binary_patches=[["skip_intro",{}],["skip_tutorial",{}]])
print("size preserved:",res.get("size_preserved"))
for rp in res.get("reports",[]):
    for n in rp.get("notes",[]): print("   ",n)
print("OUT:",OUT)
