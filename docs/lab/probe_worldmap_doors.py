"""Are the OVERWORLD (worldmap1) transitions covered by door_destination_remap?
Show every door whose source level is the world map, and whether it currently remaps."""
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    recs = rc._door_records(blob)
    # which source levels exist, and which look like the overworld?
    from collections import Counter
    srcs = Counter((r.get("src") or "(none)") for r in recs)
    print("=== door source levels (count) ===")
    for s, n in sorted(srcs.items(), key=lambda kv: -kv[1]):
        mark = "  <-- overworld?" if "world" in s.lower() or "map" in s.lower() else ""
        print(f"  {n:3}  {s}{mark}")

    # remap once and see what the worldmap doors become
    out, rep = rc.t_door_destination_remap(blob, random.Random(11), how="shuffle")
    print("\n=== doors whose source is the world map ===")
    wm = 0
    for r in recs:
        s = (r.get("src") or "").lower()
        if "world" in s or s == "worldmap1" or "overworld" in s:
            off = r["off"]; ln = len(r["name"])
            old = blob[off:off + ln].decode("latin-1")
            new = out[off:off + ln].decode("latin-1").rstrip().rstrip('"').strip()
            changed = "CHANGED" if old.strip() != new else "unchanged"
            print(f"  [{r.get('src')}] idx={r['index']} script={r['has_script']}  {old!r} -> {new!r}  {changed}")
            wm += 1
    print(f"  worldmap-source doors: {wm}")


if __name__ == "__main__":
    main()
