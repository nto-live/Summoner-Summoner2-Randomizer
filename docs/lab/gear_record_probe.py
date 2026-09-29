"""Examine item/gear record structure: what header/delimiter starts a weapon or armour
record, and whether $Damage / $Protection can be scoped to gear vs creatures."""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def show(blob, m, back=160, fwd=40, label=""):
    s = max(0, m.start() - back)
    ctx = blob[s:m.end() + fwd].replace(b"\r", b"").replace(b"\t", b" ")
    lines = ctx.split(b"\n")
    print(f"--- {label} @0x{m.start():X} ---")
    for ln in lines:
        print("   ", ln.decode("latin-1", "replace").rstrip())


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    # What block headers exist? (#Something)
    heads = {}
    for m in re.finditer(rb'#([A-Za-z][A-Za-z0-9 _]{1,30})', blob):
        h = m.group(1).decode("latin-1", "replace").strip()
        heads[h] = heads.get(h, 0) + 1
    print("=== block headers (#X : count) - gear-ish ones ===")
    for h, n in sorted(heads.items(), key=lambda kv: -kv[1]):
        if any(k in h.lower() for k in ("item", "weapon", "armor", "armour", "equip", "object", "prop", "inventory")):
            print(f"  #{h:<26} {n}")
    print("  (all headers, top 25 by count:)")
    for h, n in sorted(heads.items(), key=lambda kv: -kv[1])[:25]:
        print(f"     #{h:<26} {n}")

    print("\n=== a weapon $Damage record (with header above) ===")
    for m in list(re.finditer(rb'\$Damage:\s*\d+', blob))[:2]:
        show(blob, m, back=260, fwd=20, label="weapon $Damage")

    print("\n=== an armour $Protection / $Armor record ===")
    for m in list(re.finditer(rb'\$Protection:\s*\d+', blob))[:2]:
        show(blob, m, back=260, fwd=20, label="$Protection")
    for m in list(re.finditer(rb'\$Armor:\s*\d+', blob))[:2]:
        show(blob, m, back=260, fwd=20, label="$Armor")


if __name__ == "__main__":
    main()
