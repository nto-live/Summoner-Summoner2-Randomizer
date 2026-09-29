"""What happened to masad's monster placements in the built disc? Compare source vs CHAOS:
how many monsters in the masad segment, what creatures, and did the count/variety collapse?"""
import os, re, sys, bisect
from collections import Counter
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover, rando_core as rc  # noqa: E402

SRC = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
OUT = Path(r"C:\temp\NTO_Live_Code\out\Summoner-CHAOS.iso")


def load(iso):
    info = discover.identify(str(iso)); t = discover.find_tables(info.vpps)
    with open(iso, "rb") as f:
        f.seek(t.base); return f.read(t.total_size)


def masad_segment(blob):
    # find the masad level object chunk: the #Objects block whose nearby text mentions masad assets
    obj = [m.start() for m in re.finditer(rb"\n#Objects\b", blob)]
    # masad's automap/hud strings mark its level file
    mk = blob.find(b"hud-map-masad")
    if mk < 0:
        mk = blob.find(b"map-masad")
    if mk < 0:
        return None
    # the #Objects block for masad is the nearest one before mk (or the segment containing mk)
    i = bisect.bisect_right(obj, mk) - 1
    s = obj[i] if i >= 0 else 0
    e = obj[i+1] if i+1 < len(obj) else len(blob)
    return s, e


def main():
    a = load(SRC); b = load(OUT)
    seg = masad_segment(a)
    if not seg:
        print("could not locate masad segment"); return
    s, e = seg
    print(f"masad #Objects segment: 0x{s:X}..0x{e:X} ({e-s} bytes)")
    for tag, blob in (("SOURCE", a), ("CHAOS", b)):
        segb = blob[s:e]
        # monster placements = $Name records in this segment with +Monster and $Character
        names = re.findall(rb'\$Character:\s*"([^"]+)"', segb)
        mons = re.findall(rb'\+Monster\b', segb)
        chars_with_monster = []
        # crude: count $Character occurrences that have a +Monster within 120 bytes after
        for m in re.finditer(rb'\$Character:\s*"([^"]+)"', segb):
            if b"+Monster" in segb[m.end():m.end()+140]:
                chars_with_monster.append(m.group(1).decode("latin-1"))
        print(f"\n{tag}: {len(names)} $Character, {len(mons)} +Monster markers, "
              f"{len(chars_with_monster)} monster placements")
        print("  monster creatures:", dict(Counter(chars_with_monster)))


if __name__ == "__main__":
    main()
