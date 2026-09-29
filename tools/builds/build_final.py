"""Candidate shippable disc: the full CHAOS transform stack, but with hide_tutorials (the clean
tutorial-off that leaves the fire-clearing step intact) instead of skip_tutorial v3, and with the
door_name_shuffle pin fix now protecting invis-door0N.

This tests the last open question: does hide_tutorials + the full transform stack still freeze the
opening (as an earlier hide_tutorials disc did), or was that freeze a red herring like the per_level
scare? We now know from the disassembly that no transform touches the tutorial flags, so if it
freezes it is a different interaction to isolate.

Seed CHAOS2 to match the known-good content.
"""
import json
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-FINAL.iso"
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
    "enemies_random": {"scope": "per_level"},   # the request setting, proven safe for the fire
    "enemy_damage_set": {"value": 0},
}
binary_patches = [["skip_intro", {}], ["hide_tutorials", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
