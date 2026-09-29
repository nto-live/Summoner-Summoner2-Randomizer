"""What did the masad boat door actually become in the built CHAOS disc? Read it byte-for-byte,
and check the target's +Index slot + +Script safety. No assumptions."""
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
        return f.read(t.total_size), t.base


def main():
    a, base = load(SRC)
    b, _ = load(OUT)
    recs = rc._door_records(a)
    slots = rc._level_start_slots(a)
    safe = rc._no_script_safe_targets(a)

    print("=== every masad-source door in the BUILT disc ===")
    for r in recs:
        if (r.get("src") or "").lower().find("masad") < 0:
            continue
        off = r["off"]; ln = len(r["name"])
        old = a[off:off + ln].decode("latin-1")
        # read the full field incl trailing bytes up to the quote to see any corruption
        raw = b[off:off + ln + 2]
        new = b[off:off + ln].decode("latin-1", "replace")
        newkey = rc._door_key(new.strip().rstrip('"'))
        idx = r["index"]
        provides = sorted(slots.get(newkey, set()))
        print(f"  {old!r} -> field={raw!r}  +Index={idx}  has_script={r['has_script']}")
        print(f"      target key={newkey!r}  provides slots={provides}  slot_ok={idx in slots.get(newkey,set()) if idx is not None else '?'}  script_safe={newkey in safe}")


if __name__ == "__main__":
    main()
