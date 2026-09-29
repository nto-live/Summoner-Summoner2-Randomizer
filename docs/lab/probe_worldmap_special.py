"""Why does worldmap1 -> IonaExt (valid by our checks) still bounce? Compare a worldmap door
block against a normal level's door block - look for fields we're not accounting for
(+Spline name, +Location, extra tokens). The overworld may load levels differently."""
import os
import re
import sys
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

    recs = rc._door_records(blob)
    print("=== FULL block of the masad/worldmap boat door (worldmap1 dest) ===")
    for r in recs:
        if (r.get("src") or "").lower().find("masad") >= 0:
            off = r["off"]
            # dump ~360 bytes of the trigger block
            s = max(0, off - 30)
            chunk = blob[s:off + 340].replace(b"\r", b"").replace(b"\t", b" ")
            print(chunk.decode("latin-1", "replace"))
            print("-----")
            break

    print("\n=== a NORMAL working door block for comparison (source not worldmap/masad) ===")
    for r in recs:
        src = (r.get("src") or "").lower()
        if "world" not in src and "masad" not in src and r["index"] == 2:
            off = r["off"]
            s = max(0, off - 30)
            chunk = blob[s:off + 340].replace(b"\r", b"").replace(b"\t", b" ")
            print(f"[src={r.get('src')}]")
            print(chunk.decode("latin-1", "replace"))
            print("-----")
            break

    # How many doors are sourced from the worldmap/overworld? (candidates to exclude)
    wm = [r for r in recs if "world" in (r.get("src") or "").lower()]
    print(f"\nworldmap-source doors: {len(wm)}")


if __name__ == "__main__":
    main()
