"""Sample the live entity counts while the game plays, and report per-level maxima.

The game walks itself through doors under the test pnach, so this catches each level's window
and records how many entities were alive there. Comparing the same level on two discs - one
with `enemies_none`, one without - is the in-game test for "remove them all".

  python entity_scan.py 150
"""
import collections
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

LEVEL_NAME = 0x1245410
NUM_TRIGGERS = 0x12844FC

LISTS = (
    ("living", 0x003AE0C8, 0x31C),
    ("deadbody", 0x003AE858, 0x31C),
    ("players", 0x0125C080, 0x00),
)


def walk(p, head, next_off, maxn=256):
    """Walk an intrusive circular list whose sentinel *is* `head`.

    Living entities: the sentinel is the head object itself, nodes carry the next pointer at
    +0x31C, and the walk ends when it comes back to `head`. (Player_list uses +0x00.)
    """
    nodes = 0
    cur = p.read(head + next_off, 4)
    seen = set()
    while cur and cur != head and cur not in seen and nodes < maxn:
        seen.add(cur)
        nodes += 1
        cur = p.read(cur + next_off, 4)
    return nodes


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 150.0
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 0.4
    stats = collections.defaultdict(lambda: collections.Counter())
    samples = collections.Counter()
    with Pine(timeout=20.0) as p:
        end = time.time() + seconds
        while time.time() < end:
            try:
                lvl = p.read_string(LEVEL_NAME, 24)
                counts = {name: walk(p, head, off) for name, head, off in LISTS}
                counts["triggers"] = p.read(NUM_TRIGGERS, 4)
            except Exception as e:  # noqa: BLE001
                print(f"[{time.strftime('%H:%M:%S')}] pine error: {e}", flush=True)
                time.sleep(interval)
                continue
            samples[lvl] += 1
            for k, v in counts.items():
                stats[lvl][k] = max(stats[lvl][k], v)
            time.sleep(interval)

    print("\nlevel                samples  " + "  ".join(f"{n:>9}" for n, _, _ in LISTS) + "  triggers")
    for lvl, n in samples.most_common():
        row = "  ".join(f"{stats[lvl][name]:>9}" for name, _, _ in LISTS)
        print(f"{lvl!r:20} {n:>5}  {row}  {stats[lvl]['triggers']}")


if __name__ == "__main__":
    main()
