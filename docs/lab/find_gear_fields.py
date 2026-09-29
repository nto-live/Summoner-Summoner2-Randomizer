"""Scan TABLES.VPP for item/gear stat field names (weapon attack, armour defence),
to see whether a 'buff armour / high weapon attack' transform is even possible."""
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    # every $Field: token and how many times it appears
    fields = Counter(m.group(1).decode("latin-1", "replace")
                     for m in re.finditer(rb'([\$\+][A-Za-z][A-Za-z0-9 _]{1,30})\s*:', blob))
    # show gear/combat-relevant ones
    KEYS = ("damage", "attack", "protect", "defen", "armor", "armour", "power", "value",
            "weapon", "shield", "guard", "resist", "hit", "block", "min", "max", "bonus",
            "strength", "slot", "equip", "range")
    print("=== combat/gear-relevant field tokens (name : count) ===")
    for name, n in sorted(fields.items(), key=lambda kv: -kv[1]):
        low = name.lower()
        if any(k in low for k in KEYS):
            print(f"  {name:<28} {n}")

    # Look at a sample $Damage / $Protection record context (are these on items or creatures?)
    print("\n=== sample $Damage: contexts ===")
    for m in list(re.finditer(rb'\$Damage:\s*([0-9.]+)', blob))[:5]:
        s = max(0, m.start() - 80)
        ctx = blob[s:m.end() + 10].replace(b"\r", b" ").replace(b"\n", b" | ")
        print("  ", ctx.decode("latin-1", "replace"))


if __name__ == "__main__":
    main()
