"""Boss Rush disc per request:
- boss_rush: gather each level's +Boss placements onto one navpoint (per-level arena)
- all bosses have 1 HP: enemy_hp_set value=1  (NOTE: HP is per creature DEFINITION, there is no
  boss-only HP field, so this sets EVERY hostile creature to 1 HP - bosses included. For a boss
  rush that is on-theme: everything dies in one hit.)
- tutorial off: skip_tutorial (the working input-gate NOP) + skip_intro (free)
- random drops: enemy_drops_random (shuffles which item each +Drop yields)

Seed BOSS1. Written in the workspace; ISO goes to the external out dir (see _paths.py).
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-BOSSRUSH.iso"
SEED = "BOSS1"

transforms = [
    "boss_rush",
    "enemy_hp_set",
    "enemy_drops_random",
]
options = {
    "boss_rush": {"arena": "auto"},
    "enemy_hp_set": {"value": 1},
}
binary_patches = [["skip_intro", {}], ["skip_tutorial", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
