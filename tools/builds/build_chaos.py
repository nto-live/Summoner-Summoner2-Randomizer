"""The big combined "CHAOS" disc: the full feature stack, for broad testing.

Lives in the workspace; writes the ISO to the external out dir (see _paths.py). Game data never
enters git."""
import json
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-CHAOS.iso"
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
    "enemies_random": {"scope": "broad"},
    "enemy_damage_set": {"value": 0},
}
binary_patches = [["skip_intro", {}], ["skip_tutorial", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    (OUT_DIR / "chaos-report.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
