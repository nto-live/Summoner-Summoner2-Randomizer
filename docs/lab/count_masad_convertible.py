"""Using the engine's own placement analysis, how many placements are in the masad area and
how many peaceful ones are convertible to monsters (same-length hostile name exists)?"""
import os
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402
import rando_core as rc  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    monsters, peaceful = rc._analyse_enemies(blob)
    print(f"WHOLE GAME: {len(monsters)} monster placements, {len(peaceful)} peaceful placements")

    # attribute each placement to a source level via the nearest preceding "Level file for X"
    heads = [(m.start(), m.group(1).strip().decode("latin-1", "replace"))
             for m in re.finditer(rb"Level file for ([^\r\n*]{1,40})", blob)]
    import bisect
    hs = [h[0] for h in heads]

    def level_of(off):
        i = bisect.bisect_right(hs, off) - 1
        return heads[i][1] if i >= 0 else "?"

    # count masad placements
    masad_mon = [r for r in monsters if "masad" in level_of(r["start"]).lower()]
    masad_peace = [r for r in peaceful if "masad" in level_of(r["start"]).lower()]
    print(f"MASAD: {len(masad_mon)} monsters, {len(masad_peace)} peaceful placements")

    # of the masad peaceful, how many have a same-length hostile name available (convertible)?
    pool = rc._hostile_name_pool(blob, monsters)
    conv = 0
    for r in masad_peace:
        namelen = len(r["char"])
        if pool.get(namelen):
            conv += 1
    print(f"MASAD convertible peaceful (same-length hostile name exists): {conv}")
    print(f"So max enemies achievable in masad = {len(masad_mon)} existing + {conv} converted "
          f"= {len(masad_mon) + conv}")


if __name__ == "__main__":
    main()
