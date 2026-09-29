"""Map each level -> the set of start-ids (slot numbers) it provides as $player<N>-<slot>
navpoints. A door with +Index K can only safely target a level that provides slot K."""
import os
import re
import sys
from collections import defaultdict
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

    # Segment the blob by "Level file for X" comments (same anchor _door_records uses),
    # and within each segment collect the start-ids from $player<N>-<slot> navpoints.
    heads = [(m.start(), m.group(1).strip().decode("latin-1", "replace"))
             for m in re.finditer(rb"Level file for ([^\r\n*]+)", blob)]
    heads.sort()
    slots_by_level = defaultdict(set)
    for i, (pos, name) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(blob)
        seg = blob[pos:end]
        for m in re.finditer(rb'\$player\d+-(\d+)', seg):
            slots_by_level[name.lower()].add(int(m.group(1)))

    print("=== start-ids (slots) each level provides ===")
    for name in sorted(slots_by_level):
        print(f"  {name:<28} slots={sorted(slots_by_level[name])}")

    # Which DOOR_TARGET_NAMES have no slots at all (never a safe target)?
    known = {n.lower(): n for n in rc.DOOR_TARGET_NAMES}
    print("\n=== DOOR_TARGET_NAMES with NO detected player-start slots ===")
    for low, disp in sorted(known.items()):
        if not any(low in lvl or lvl in low for lvl in slots_by_level):
            print(f"  {disp}")


if __name__ == "__main__":
    main()
