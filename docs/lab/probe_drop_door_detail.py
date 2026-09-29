"""Detail: +Drop record structure, and why door_destination_remap skips some transitions."""
import os
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

    print("=== +Drop: sample contexts ===")
    for m in list(re.finditer(rb'\+Drop\s*:?\s*("?[^\r\n]{0,40})', blob))[:12]:
        s = max(0, m.start() - 90)
        ctx = blob[s:m.end() + 5].replace(b"\r", b"").replace(b"\t", b" ").replace(b"\n", b" | ")
        print("  ", ctx.decode("latin-1", "replace"))

    print("\n=== door transform: what it finds vs. what it changes ===")
    recs = rc._door_records(blob)
    print(f"  _door_records found: {len(recs)} doors (+Id 'load level')")
    # how many have candidates (i.e. would actually be rewritten) at shuffle
    import random
    rng = random.Random(1)
    changeable = 0
    no_cand = 0
    by_type = {}
    for r in recs:
        old_len = len(r["name"])
        cands = rc._door_candidates(old_len, r.get("src"))
        if cands:
            changeable += 1
        else:
            no_cand += 1
    print(f"  doors with >=1 legal candidate: {changeable}")
    print(f"  doors left alone (no candidate fits width / same level): {no_cand}")

    # +Type distribution among the found door records (look 200 bytes after each trigger)
    for r in recs:
        seg = blob[r["off"]:r["off"] + 400]
        tm = re.search(rb'\+Type:\s*"([^"]+)"', seg)
        ty = tm.group(1).decode() if tm else "(none)"
        by_type[ty] = by_type.get(ty, 0) + 1
    print("  door records by +Type:", by_type)

    # Are there 'location' triggers with +Id 'load level' that we might mishandle?
    loc_triggers = len(re.findall(rb'\+Type:\s*"location"', blob))
    print(f"  total +Type 'location': {loc_triggers}")


if __name__ == "__main__":
    main()
