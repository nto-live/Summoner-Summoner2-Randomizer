"""Which creatures are safe to place ANYWHERE? A creature renders only if its model is loaded
for the level. Find which creatures appear across MANY levels (broadly loaded) vs only one
(level-specific), so we can build a 'safe-anywhere' pool for a wider-scope enemy randomize that
still never causes missing graphics - and that never touches NPC placements.

Approach: for each level segment (#Objects), collect the set of monster creature names placed in
it. A creature that appears as a placed monster in many distinct levels is broadly available; one
that appears in only one is level-specific. The green elemental the user saw is presumably a
broadly-available one.
"""
import os
import re
import sys
import bisect
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO)); t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base); blob = f.read(t.total_size)

    monsters, peaceful = rc._analyse_enemies(blob)
    print(f"monster placements: {len(monsters)}, peaceful (NPC/prop): {len(peaceful)}")
    print("(enemies_random already touches ONLY monster placements, never the peaceful ones)")

    obj = sorted(m.start() for m in re.finditer(rb"\n#Objects\b", blob))
    def seg(off): return bisect.bisect_right(obj, off) - 1

    # creature -> set of level segments it's a placed monster in
    levels_of = defaultdict(set)
    for r in monsters:
        levels_of[r["char"].decode("latin-1")].add(seg(r["start"]))

    spread = Counter()
    for name, segs in levels_of.items():
        spread[len(segs)] += 1
    print("\ncreature 'appears in N distinct level segments' distribution (N: how many creatures):")
    for n, c in sorted(spread.items()):
        print(f"  in {n:3} levels: {c} creatures")

    # the broadly-available ones (appear in >= 5 level segments) = candidate safe-anywhere pool
    broad = sorted([(len(segs), name) for name, segs in levels_of.items() if len(segs) >= 5], reverse=True)
    print(f"\nbroadly-available creatures (>=5 levels) - candidate 'safe anywhere' pool ({len(broad)}):")
    for cnt, name in broad[:40]:
        print(f"  {cnt:3} levels  {name!r} (len {len(name)})")


if __name__ == "__main__":
    main()
