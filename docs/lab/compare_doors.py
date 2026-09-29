"""Show door destination before/after between the source ISO and the CHAOS build."""
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
    ra = rc._door_records(a)
    changed = same = 0
    shown = 0
    for r in ra:
        off = r["off"]
        ln = len(r["name"])
        old = a[off:off + ln].decode("latin-1", "replace")
        new = b[off:off + ln].decode("latin-1", "replace")
        if old != new:
            changed += 1
            if shown < 20:
                print(f"  [{r.get('src')}]  {old!r} -> {new!r}")
                shown += 1
        else:
            same += 1
    print(f"\n  total doors: {len(ra)}  changed: {changed}  unchanged: {same}")


if __name__ == "__main__":
    main()
