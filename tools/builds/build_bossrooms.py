"""Boss ROOMS gauntlet - the WORKING version (NPC->boss swap, no activation gate).

Starting at the opening level, each room's NPC placements are overwritten with hostile boss
creatures (live on arrival - hostility is intrinsic to the creature definition), and each level's
exit door is chained to the next boss room. Walk in, fight a room of bosses, exit to the next.

- boss_rooms: the chain + NPC->boss fill (chain starts at masad)
- enemy_hp_set=1: everything dies in one hit (fast run)
- enemy_drops_random + chest_items: random loot
- enemy_xp_set=9999: max XP
- skip_tutorial + skip_intro: tutorials off, intro skipped

EXPERIMENTAL: some chained door hops may reuse overworld doors that can bounce to the title. This
disc is the play-test to confirm the chain holds and bosses appear on arrival.

Seed ROOMS1.
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-BOSSROOMS.iso"
SEED = "ROOMS1"

transforms = [
    "boss_rooms",
    "enemy_hp_set",
    "enemy_drops_random",
    "chest_items",
    "gold_max",
    "enemy_xp_set",
]
options = {
    "boss_rooms": {"levels": 5, "per_level": 0},   # 0 = fill every clean slot (many bosses)
    "enemy_hp_set": {"value": 1},
    "chest_items": {"how": "shuffle"},
    "enemy_xp_set": {"value": 9999},
}
binary_patches = [["skip_intro", {}], ["skip_tutorial", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
