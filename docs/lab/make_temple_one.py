"""Minimal temple boss room:
  - masad exit -> TempleInt (proven to load)
  - unlink SOME TempleInt NPCs (fewest-referenced first, limited count) to thin the crowd
  - place exactly ONE boss (TempleInt owns Pyrul etc; its models are resident)
  - standing rules: skip_tutorial + 1 HP
Keep edits minimal to avoid the mass-unlink/scene freeze. One boss, modest unlinks.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc
SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-TEMPLEONE.iso")
PAC=(b"+Hidden",b'"turn hostile"\t0',b'"wait for go"',b'"show/hide"\t0')
UNLINK_COUNT = 10   # thin the crowd modestly, not all 30

def _ranges(): return rc._BOSS_GAUNTLET_RANGES

def t_templeone(blob, rng):
    rep=rc.Report("temple_one")
    ranges=_ranges()
    def lvl_at(off):
        for name,s,e in ranges:
            if s<=off<e: return name
        return None
    out=bytearray(blob)
    _m,peaceful=rc._analyse_enemies(blob)
    temple=[r for r in peaceful if lvl_at(r['start'])=="TempleInt"]
    # rank by how FEW times the $Name is referenced (fewest refs = safest to unlink)
    def refs(r):
        nm=re.search(rb'\$Name\s*:\s*"([^"]+)"', blob[r['start']:r['end']])
        return len(re.findall(re.escape(nm.group(1)),blob)) if nm else 99
    temple_sorted=sorted(temple,key=refs)

    # 1) place ONE boss on the single least-referenced wide-enough clean slot (equal length if
    # possible; TempleInt bosses: Pyrul5 Titus5 Luminar7 Machival8 'Tiger Rider'11)
    BOSSES=[b"Pyrul",b"Titus",b"Luminar",b"Machival",b"Tiger Rider"]
    placed=False
    for r in temple_sorted:
        seg=blob[r['start']:r['end']]
        if any(p in seg for p in PAC): continue
        w=len(r['char'])
        eq=[b for b in BOSSES if len(b)==w]
        if not eq: continue
        a,b=r['char_abs']
        if bytes(out[a:b])!=r['char']: continue
        out[a:b]=eq[0]
        rep.notes.append(f"placed boss {eq[0].decode()} (equal len {w})")
        placed=True
        placed_rec=r
        break
    if not placed:
        # fall back: pad one boss into the least-referenced clean slot (padding render-safe per padtest)
        for r in temple_sorted:
            seg=blob[r['start']:r['end']]
            if any(p in seg for p in PAC): continue
            w=len(r['char'])
            fit=[b for b in BOSSES if len(b)<=w]
            if not fit: continue
            a,b=r['char_abs']
            if bytes(out[a:b])!=r['char']: continue
            out[a:b]=fit[0]+b" "*(w-len(fit[0]))
            rep.notes.append(f"placed boss {fit[0].decode()} (padded into w={w})")
            placed=True; placed_rec=r
            break

    # 2) unlink a MODEST number of other NPCs (fewest-referenced), skipping the boss slot
    unlinked=0
    for r in temple_sorted:
        if unlinked>=UNLINK_COUNT: break
        if placed and r is placed_rec: continue
        seg=blob[r['start']:r['end']]
        sp=rc.START_POS_RE.search(seg)
        if not sp: continue
        val=sp.group(2)
        if not val.startswith(b"$npc"): continue
        a=r['start']+sp.start(2); b=r['start']+sp.end(2)
        newv=b"$zzz"+val[4:]
        if len(newv)==len(val) and bytes(out[a:b])==val:
            out[a:b]=newv; unlinked+=1
    rep.changed=(1 if placed else 0)+unlinked
    rep.notes.append(f"unlinked {unlinked} NPCs; boss placed={placed}")
    return bytes(out),rep

def t_masad_door(blob, rng):
    rep=rc.Report("masad_door"); ranges=_ranges()
    def lvl_at(off):
        for name,s,e in ranges:
            if s<=off<e: return name
        return None
    out=bytearray(blob)
    for r in rc._door_records(blob):
        if lvl_at(r['off'])=="masad":
            old=r['name']; off=r['off']
            if len("TempleInt")>len(old): continue
            exp=old+b'"'
            if bytes(out[off:off+len(exp)])!=exp: continue
            out[off:off+len(exp)]=b"TempleInt"+b" "*(len(old)-9)+b'"'
            rep.changed+=1; break
    return bytes(out),rep

rc.TRANSFORMS["temple_one"]=t_templeone
rc.TRANSFORMS["masad_door"]=t_masad_door
res=rc.randomize_iso(SRC,OUT,"T1",["temple_one","masad_door","enemy_hp_set"],
                     progress=lambda m:print(" ",m),
                     options={"enemy_hp_set":{"value":1}},
                     binary_patches=[["skip_intro",{}],["skip_tutorial",{}]])
print("size preserved:",res.get("size_preserved"))
for rp in res.get("reports",[]):
    for n in rp.get("notes",[]): print("   ",n)
print("OUT:",OUT)
