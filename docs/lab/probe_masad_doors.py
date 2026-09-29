"""Show masad's doors: original vs CHAOS destination, plus each door's +Index and +Type,
to diagnose the 'unknown -> back to menu' bounce (likely a destination with no matching
player-start navpoint for that +Index)."""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-CHAOS.iso")


def load(iso):
    info = discover.identify(str(iso))
    t = discover.find_tables(info.vpps)
    with open(iso, "rb") as f:
        f.seek(t.base)
        return f.read(t.total_size)


def main():
    a = load(SRC)
    b = load(OUT)
    recs = rc._door_records(a)

    print("=== doors whose SOURCE level is masad ===")
    for r in recs:
        if (r.get("src") or "").lower().find("masad") < 0:
            continue
        off = r["off"]
        ln = len(r["name"])
        old = a[off:off + ln].decode("latin-1", "replace")
        new = b[off:off + ln].decode("latin-1", "replace").rstrip()
        # find this door's +Index and +Type within its block
        seg = b[off:off + 400]
        idx = re.search(rb'\+Index:\s*(\d+)', seg)
        ty = re.search(rb'\+Type:\s*"([^"]+)"', seg)
        print(f"  {old!r:16} -> {new!r:16}  +Index={idx.group(1).decode() if idx else '?'}  +Type={ty.group(1).decode() if ty else '?'}")

    # For each unique NEW masad destination, does that level have a $player<Index> navpoint?
    print("\n=== does each new destination have the required player-start navpoint? ===")
    dests = set()
    for r in recs:
        if (r.get("src") or "").lower().find("masad") < 0:
            continue
        off = r["off"]; ln = len(r["name"])
        new = b[off:off + ln].decode("latin-1", "replace").rstrip().rstrip('"').strip()
        seg = b[off:off + 400]
        idx = re.search(rb'\+Index:\s*(\d+)', seg)
        dests.add((new, idx.group(1).decode() if idx else "?"))
    for name, index in sorted(dests):
        # look for a "$player<index>" or "$playerstart" navpoint name string in the blob
        needles = [f'$player{index}'.encode(), b'$player_start', f'"player{index}"'.encode()]
        found = any(b.find(n) >= 0 for n in needles)
        # also check the level even exists as a chunk name
        lvl_present = b.lower().find(name.lower().encode()) >= 0
        print(f"  dest {name!r:16} needs +Index {index}: level_present={lvl_present} playerstart_seen={found}")


if __name__ == "__main__":
    main()
