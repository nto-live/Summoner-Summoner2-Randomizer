"""Which levels have a base script whose name == the level name? A door with NO +Script:
uses the destination NAME as its script (door-mechanism.md 5b caveat 2), so it can only
safely target such levels. Build that set from the $Level:/+Script: table."""
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

    # script_filenames.tbl style: $Level: "name" ... +Script: "scriptbase" (one or more)
    # Walk $Level: blocks and collect the scripts each declares.
    lvls = list(re.finditer(rb'\$Level:\s*"([^"]+)"', blob))
    print(f"$Level: declarations: {len(lvls)}")
    name_eq_script = []
    detail = []
    for i, m in enumerate(lvls):
        name = m.group(1).decode("latin-1")
        end = lvls[i + 1].start() if i + 1 < len(lvls) else min(m.end() + 600, len(blob))
        seg = blob[m.end():end]
        scripts = [s.group(1).decode("latin-1") for s in re.finditer(rb'\+Script:\s*"([^"]+)"', seg)]
        # does any script base equal the level name (case-insensitive)?
        eq = any(s.lower() == name.lower() or s.lower().startswith(name.lower()) for s in scripts)
        if eq:
            name_eq_script.append(name)
        detail.append((name, scripts[:4]))

    print("\n=== $Level: -> declared scripts (first 30) ===")
    for name, scripts in detail[:30]:
        print(f"  {name:<22} {scripts}")

    print(f"\nlevels whose script matches their name: {len(name_eq_script)}")
    print(" ", sorted(name_eq_script))


if __name__ == "__main__":
    main()
