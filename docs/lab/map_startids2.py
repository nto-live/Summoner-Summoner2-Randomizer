"""Correctly map each level -> start-id slots it provides, by segmenting the blob on the
per-level script chunk boundary the game actually uses, then collecting $player<N>-<slot>.

We find level chunks by the '$Level: "name"' declarations AND by '<name>_script'/level file
markers; then within each level's byte span, collect slots from $player navpoints. Also report
the +Index distribution of doors so we can judge a 'restrict to safe start-ids' policy."""
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(SRC))
    t = discover.find_tables(info.vpps)
    with open(SRC, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    # Global picture first: how many $player navpoints exist and their slot spread
    all_slots = Counter(int(m.group(1)) for m in re.finditer(rb'\$player\d+-(\d+)', blob))
    print("global $player<N>-<slot> slot distribution:", dict(sorted(all_slots.items())))
    print("total $player navpoints:", sum(all_slots.values()))

    # Door +Index distribution
    idxs = Counter(int(m.group(1)) for m in re.finditer(rb'\+Index:\s*(\d+)', blob))
    print("door +Index distribution:", dict(sorted(idxs.items())))

    # Try segmenting by the many "#Navpoints" blocks: each level has one. Find the nearest
    # preceding "Level file for X" OR "$Level: X" to name it. Then collect slots per span.
    # Simpleribbon: find all $player navpoints, and for each, the nearest preceding level name.
    lvlmarks = [(m.start(), m.group(1).decode("latin-1", "replace").strip())
                for m in re.finditer(rb'Level file for ([^\r\n*]{1,40})', blob)]
    lvlmarks += [(m.start(), m.group(1).decode("latin-1", "replace").strip())
                 for m in re.finditer(rb'\$Level:\s*"([^"]{1,40})"', blob)]
    lvlmarks.sort()
    starts = [p for p, _ in lvlmarks]
    names = [n for _, n in lvlmarks]

    import bisect
    slots_by_level = defaultdict(set)
    for m in re.finditer(rb'\$player\d+-(\d+)', blob):
        i = bisect.bisect_right(starts, m.start()) - 1
        if i >= 0:
            slots_by_level[names[i].lower()].add(int(m.group(1)))

    print("\n=== slots per level (via nearest preceding level marker) ===")
    for name in sorted(slots_by_level):
        print(f"  {name:<30} {sorted(slots_by_level[name])}")


if __name__ == "__main__":
    main()
