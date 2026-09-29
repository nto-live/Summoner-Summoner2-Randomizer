"""Test disc for the NEW tutorial fix: hide_tutorials (early-return ngps_render_tutorial) instead
of the unreliable skip_tutorial (v3 auto-advance).

Same feature set as build_request.py so it's a like-for-like retest of the burning-village firewall:
- hide_tutorials + skip_intro (binary)
- enemies_random scope=per_level (same-area swaps)
- door_destination_remap (random transitions)
- xp_scale 200 (boosted XP)
- enemy_drops_always (guaranteed loot)

Seed REQ1 so the non-tutorial content matches the discs already tested.
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-HIDETUT.iso"
SEED = "REQ1"

transforms = [
    "enemies_random",
    "door_destination_remap",
    "xp_scale",
    "enemy_drops_always",
]
options = {
    "enemies_random": {"scope": "per_level"},
    "door_destination_remap": {"how": "shuffle", "require_script": False},
    "xp_scale": {"percent": 200},
}
binary_patches = [["skip_intro", {}], ["hide_tutorials", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
