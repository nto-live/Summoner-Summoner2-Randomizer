"""TempleInt as a boss room, 'just enemies' version:
  - UNLINK every peaceful (NPC) placement in TempleInt from its navpoint ($npcNNN/$Start -> $zzz),
    the proven enemies_none trick: the record stays (so scripts that reference it still resolve)
    but no NPC spawns. This clears the ceremony crowd.
  - Then RE-POINT a few of those unlinked placements to TempleInt's OWN bosses (model-safe), by
    rewriting $Character to a boss name padded to the field width (padding proven safe - TempleInt
    rendered fine with a padded 'Pyrul').
  - masad exit -> TempleInt so it's reachable in one hop.
  - standing test rules: skip_tutorial + enemy_hp_set=1.

Tests whether unlinking the scene NPCs stops the dialogue-script freeze while leaving a few bosses.
Writes to external out dir.
"""
import os, re, sys, bisect
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-TEMPLETEST.iso")

TGT = "TempleInt"
# TempleInt owns these bosses (models resident); use the short ones padded into wide NPC slots.
TEMPLE_BOSSES = [b"Pyrul", b"Titus", b"Luminar", b"Machival", b"Tiger Rider"]


def _ranges():
    return rc._BOSS_GAUNTLET_RANGES


def t_templeroom(blob, rng):
    rep = rc.Report("templeroom")
    ranges = _ranges()
    def lvl_at(off):
        for name, s, e in ranges:
            if s <= off < e: return name
        return None
    out = bytearray(blob)
    _m, peaceful = rc._analyse_enemies(blob)
    temple_npcs = [r for r in peaceful if lvl_at(r['start']) == TGT]
    unlinked = 0
    bossed = 0
    for i, r in enumerate(temple_npcs):
        seg = blob[r['start']:r['end']]
        # every Nth placement becomes a boss; the rest get unlinked (no spawn)
        if i % 3 == 0:
            # place a boss: rewrite $Character to a boss that fits (padded)
            w = len(r['char'])
            fit = [b for b in TEMPLE_BOSSES if len(b) <= w]
            if fit:
                a, b = r['char_abs']
                if bytes(out[a:b]) == r['char']:
                    new = fit[rng.randrange(len(fit))]
                    out[a:b] = new + b" " * (w - len(new))
                    bossed += 1
                    continue
        # otherwise unlink: $Start position "$npcNNN" -> "$zzzNNN", and $Name suffix likewise
        sp = rc.START_POS_RE.search(seg)
        if sp:
            val = sp.group(2)
            if val.startswith(b"$npc"):
                a = r['start'] + sp.start(2); b = r['start'] + sp.end(2)
                newv = b"$zzz" + val[4:]
                if len(newv) == len(val) and bytes(out[a:b]) == val:
                    out[a:b] = newv
                    unlinked += 1
    rep.changed = unlinked + bossed
    rep.notes.append(f"TempleInt: {bossed} placements -> bosses, {unlinked} NPCs unlinked ($zzz)")
    return bytes(out), rep


def t_masad_door(blob, rng):
    rep = rc.Report("masad_door")
    ranges = _ranges()
    def lvl_at(off):
        for name, s, e in ranges:
            if s <= off < e: return name
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
            break
    return bytes(out), rep


rc.TRANSFORMS["templeroom"] = t_templeroom
rc.TRANSFORMS["masad_door"] = t_masad_door
res = rc.randomize_iso(SRC, OUT, "TMP1", ["templeroom", "masad_door", "enemy_hp_set"],
                       progress=lambda m: print(" ", m),
                       options={"enemy_hp_set": {"value": 1}},
                       binary_patches=[["skip_intro", {}], ["skip_tutorial", {}]])
print("size preserved:", res.get("size_preserved"))
for rp in res.get("reports", []):
    for n in rp.get("notes", []): print("   ", n)
print("OUT:", OUT)
