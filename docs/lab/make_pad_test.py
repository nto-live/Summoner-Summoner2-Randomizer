"""Minimal isolation test: does space-padding a $Character break the load, or was the masad freeze
really an unloaded-model issue? Pad ONE TempleInt clean slot with a boss TempleInt already loads
(Pyrul - its model is resident as a +Boss), size-preserving (Pyrul + spaces + close quote). Write a
test ISO. Pyrul's model IS loaded in TempleInt, so if TempleInt now loads/plays, padding is fine; if
it black-screens/hangs, padding is the culprit.

Writes to the external out dir. Uses randomize_iso with a tiny custom edit via a one-off transform.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-PADTEST.iso")

# register a one-off transform that pads exactly one wide clean TempleInt slot with "Pyrul"
def t_padtest(blob, rng):
    rep = rc.Report("padtest")
    ranges = rc._BOSS_GAUNTLET_RANGES
    def lvl_at(off):
        for name,s,e in ranges:
            if s<=off<e: return name
        return None
    _m, peaceful = rc._analyse_enemies(blob)
    out = bytearray(blob)
    for r in peaceful:
        if lvl_at(r['start']) != "TempleInt": continue
        w = len(r['char'])
        if w < 6: continue  # need room for Pyrul(5)+at least 1 space
        a,b = r['char_abs']
        if bytes(out[a:b]) != r['char']: continue
        out[a:b] = b"Pyrul" + b" "*(w-5)
        rep.changed += 1
        rep.notes.append(f"padded one TempleInt slot (was {r['char'].decode()!r} w={w}) -> 'Pyrul'+pad")
        break
    return bytes(out), rep

def t_padtest_door(blob, rng):
    """Also chain masad's exit -> TempleInt so the padded temple is reachable in one hop."""
    rep = rc.Report("padtest_door")
    ranges = rc._BOSS_GAUNTLET_RANGES
    def lvl_at(off):
        for name,s,e in ranges:
            if s<=off<e: return name
        return None
    out = bytearray(blob)
    for r in rc._door_records(blob):
        if lvl_at(r['off']) == "masad":
            old = r['name']; off = r['off']
            if len("TempleInt") > len(old): continue
            expect = old + b'"'
            if bytes(out[off:off+len(expect)]) != expect: continue
            out[off:off+len(expect)] = b"TempleInt" + b" "*(len(old)-9) + b'"'
            rep.changed += 1
            rep.notes.append(f"masad door {old.decode()!r} -> TempleInt")
            break
    return bytes(out), rep

rc.TRANSFORMS["padtest"] = t_padtest
rc.TRANSFORMS["padtest_door"] = t_padtest_door
# standing test rule: always tutorials off + 1 HP so we can blitz to the thing under test
res = rc.randomize_iso(SRC, OUT, "PAD1", ["padtest","padtest_door","enemy_hp_set"],
                       progress=lambda m: print(" ", m),
                       options={"enemy_hp_set": {"value": 1}},
                       binary_patches=[["skip_intro",{}], ["skip_tutorial",{}]])
print("size preserved:", res.get("size_preserved"))
for rp in res.get("reports", []):
    for n in rp.get("notes", []): print("   ", n)
print("OUT:", OUT)
