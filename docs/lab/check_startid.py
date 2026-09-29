"""Check whether a destination level actually has the player-start navpoint for a given
+Index (start id). This is the reachability gap that makes a door bounce to menu.

The loader (level_script_set_player_starts) needs a '$player<N>' navpoint in the destination
matching the door's +Index. If it's missing the load fails."""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(SRC))
    t = discover.find_tables(info.vpps)
    with open(SRC, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    # What do player-start navpoints actually look like? sample $Name entries that look like starts
    print("=== sample navpoint names containing 'player' or 'start' ===")
    seen = set()
    for m in re.finditer(rb'"(\$?[Pp]layer[^"]{0,20})"', blob):
        v = m.group(1).decode("latin-1")
        if v not in seen:
            seen.add(v)
            print("  ", v)
        if len(seen) > 25:
            break

    print("\n=== how the game names a start id: look near '+Index' usage ===")
    for m in list(re.finditer(rb'\+Index:\s*(\d+)', blob))[:8]:
        s = max(0, m.start() - 120)
        ctx = blob[s:m.end() + 20].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
        print("  ", ctx.decode("latin-1", "replace"))

    # Count how many distinct +Index values doors use vs which start navpoints exist
    idxs = sorted({int(m.group(1)) for m in re.finditer(rb'\+Index:\s*(\d+)', blob)})
    print("\n  distinct +Index values used by doors:", idxs)


if __name__ == "__main__":
    main()
