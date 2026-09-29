"""Bisect the opening freeze, step 1: the KNOWN-GOOD CHAOS recipe with ONE change — enemy scope
flipped from 'broad' (works) to 'per_level' (the request setting, present on the frozen discs).

CHAOS2 (broad) is play-verified playable. The frozen discs used per_level. If this freezes, the
enemy scope on the starting masad level is the culprit. If it stays playable, the freeze is one of
the other differences (xp_scale, drops_always, or the hide_tutorials patch) and we bisect on.

Everything else identical to build_chaos.py. Uses skip_tutorial v3 (the known-good tutorial patch),
not hide_tutorials, to hold that variable fixed for now.
"""
import json
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-BISECT1.iso"
SEED = "CHAOS2"

transforms = [
    "enemy_hp_set", "door_destination_remap", "item_scatter", "chest_items",
    "weapon_attack_max", "armor_protect_max", "enemy_drops_random", "enemy_drops_always",
    "enemy_xp_set", "enemies_random", "enemy_damage_set",
]
options = {
    "enemy_hp_set": {"value": 1},
    "door_destination_remap": {"how": "shuffle", "require_script": False},
    "weapon_attack_max": {"value": 999},
    "armor_protect_max": {"value": 999},
    "enemy_xp_set": {"value": 9999},
    "enemies_random": {"scope": "per_level"},   # <-- THE ONE CHANGE (was "broad")
    "enemy_damage_set": {"value": 0},
}
binary_patches = [["skip_intro", {}], ["skip_tutorial", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
