"""Does _door_records' 'src' (the 'Level file for X' comment) match the VPP-member level names of
the gauntlet chain? The transform only gets the blob, so it must identify a door's source level by
_door_records['src']. Confirm the 7 chain levels appear as door 'src' values (via _door_key), so
the transform can select the right door without needing the VPP TOC. Read-only.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
info = discover.identify(str(ISO))
t = discover.find_tables(info.vpps)
with open(ISO, "rb") as f:
    f.seek(t.base)
    blob = f.read(t.total_size)

chain = ["khosanilab2", "khosanilab", "rand-hills01", "IonaExt02", "sewerboss", "masad", "TempleInt"]
recs = rc._door_records(blob)
src_keys = {}
for r in recs:
    src_keys.setdefault(rc._door_key(r["src"] or ""), r["src"])

print("=== chain level -> matching door 'src' comment ===")
for lv in chain:
    k = rc._door_key(lv)
    match = src_keys.get(k)
    # also allow prefix match (worldmap1 vs worldmap style)
    if match is None:
        for sk, disp in src_keys.items():
            if sk and k and min(len(sk), len(k)) >= 8 and (sk.startswith(k) or k.startswith(sk)):
                match = disp + " (prefix)"
                break
    doors = [r for r in recs if rc._door_key(r["src"] or "") == k]
    print(f"  {lv:16} key={k:16} src_comment={match!r:34} doors={len(doors)}")
