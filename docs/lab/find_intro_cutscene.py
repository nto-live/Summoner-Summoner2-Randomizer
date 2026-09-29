"""List $Cutscene: names in TABLES.VPP and flag the ones near 'masad' / intro assets,
so we can neuter ONLY the opening cinematic instead of all 84 (which hangs the boot)."""
import os
import re
import sys
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

    cuts = [(m.start(), m.group(1).decode("latin-1", "replace"))
            for m in re.finditer(rb'\$Cutscene:\s*"([^"]+)"', blob)]
    print(f"total $Cutscene tokens: {len(cuts)}")

    # unique names
    names = {}
    for off, name in cuts:
        names.setdefault(name, []).append(off)
    print(f"unique names: {len(names)}")

    # find where 'masad' script chunk sits, and which cutscenes are nearby
    masad_positions = [m.start() for m in re.finditer(rb"masad", blob)]
    print(f"'masad' occurrences: {len(masad_positions)}")

    HINTS = ("intro", "pre", "open", "logo", "start", "title", "begin", "narr", "cam", "story")
    print("\n-- cutscene names matching opening hints --")
    for name in sorted(names):
        low = name.lower()
        if any(h in low for h in HINTS):
            print(f"  {name!r}  x{len(names[name])}  first@0x{t.base + names[name][0]:X}")

    # cutscenes physically closest to a masad chunk
    print("\n-- cutscenes within 4KB of a 'masad' string --")
    seen = set()
    for off, name in cuts:
        for mp in masad_positions:
            if abs(off - mp) < 4096:
                if name not in seen:
                    print(f"  {name!r}  @0x{t.base + off:X}  (masad @0x{t.base + mp:X}, d={off - mp})")
                    seen.add(name)
                break


if __name__ == "__main__":
    main()
