"""Count the live entities in the running game.

Two intrusive lists matter:
  * `Living_entity_list` @ 0x003AE0C8 - sentinel; each entity's next pointer is at +0x31C
  * `Player_list`        @ 0x0125C080 - sentinel; each node's next pointer is at +0x00

The count is the cheapest in-game signal for "are there monsters here": a level whose monster
placements have been disarmed should hold noticeably fewer living entities than vanilla.
"""
import sys
import time

sys.path.insert(0, r"F:\rando\S1\notes")
from pine import Pine  # noqa: E402

LIVING_HEAD = 0x003AE0C8
LIVING_NEXT = 0x31C
PLAYER_HEAD = 0x0125C080
PLAYER_NEXT = 0x00
LEVEL_NAME = 0x1245410
NUM_TRIGGERS = 0x12844FC


def walk(p, head, next_off, maxn=512):
    nodes = []
    cur = p.read(head, 4)
    seen = set()
    while cur and cur not in seen and len(nodes) < maxn:
        seen.add(cur)
        nodes.append(cur)
        cur = p.read(cur + next_off, 4)
    return nodes


def sample(p):
    living = walk(p, LIVING_HEAD, LIVING_NEXT)
    players = walk(p, PLAYER_HEAD, PLAYER_NEXT)
    return {
        "level": p.read_string(LEVEL_NAME, 32),
        "triggers": p.read(NUM_TRIGGERS, 4),
        "living": len(living),
        "players": len(players),
    }


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    with Pine(timeout=20.0) as p:
        end = time.time() + seconds
        last = None
        while time.time() < end:
            s = sample(p)
            line = (f"[{time.strftime('%H:%M:%S')}] level={s['level']!r:14} "
                    f"triggers={s['triggers']:<3} living_entities={s['living']:<4} "
                    f"players={s['players']}")
            if line[10:] != (last or "")[10:]:
                print(line, flush=True)
                last = line
            time.sleep(2)


if __name__ == "__main__":
    main()
