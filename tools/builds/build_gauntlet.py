"""Boss GAUNTLET test disc:
- boss_gauntlet: chain boss levels' exit doors into a sequence (7 levels / 16 of 25 bosses):
  khosanilab2 -> khosanilab -> rand-hills01 -> IonaExt02 -> sewerboss -> masad -> TempleInt
- boss_rush: cluster each level's bosses onto one spot so every stop is a single fight
- enemy_hp_set=1: everything dies in one hit
- enemy_drops_random: random drops
- chest_items: random chest contents
- enemy_xp_set=9999: max XP per kill
- skip_tutorial + skip_intro: tutorials off, intro skipped

EXPERIMENTAL: 4 of the 6 gauntlet hops reuse overworld 'worldmap1' doors that have historically
bounced to the title screen. This disc is NOT play-verified - the whole point is to test whether
those hops hold. If a hop bounces, we know which link to rework.

Seed GAUNT1.
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-GAUNTLET.iso"
SEED = "GAUNT1"

transforms = [
    "boss_gauntlet",
    "boss_rush",
    "enemy_hp_set",
    "enemy_drops_random",
    "chest_items",
    "enemy_xp_set",
]
options = {
    "boss_rush": {"arena": "auto"},
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
