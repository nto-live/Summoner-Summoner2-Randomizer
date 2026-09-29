"""Focused build per user request (fresh disc):
- tutorial off (skip_tutorial, binary) + skip_intro (free)
- enemies randomized but kept within the same area (enemies_random scope=per_level)
- random transitions (door_destination_remap)
- boosted XP (xp_scale 200% = double)
- all enemies drop something, every item on their list (enemy_drops_always)

NOTE on "10x items per drop": a +Drop entry is `"Item" <chance>` with NO quantity field, so a
per-drop count is not expressible. enemy_drops_always (every listed item guaranteed to drop) is
the closest the data allows to "lots of loot per kill".
"""
from _paths import SRC_ISO, OUT_DIR, progress, summarize
import rando_core as rc

OUT = OUT_DIR / "Summoner-REQUEST.iso"
SEED = "REQ1"

transforms = [
    "enemies_random",
    "door_destination_remap",
    "xp_scale",
    "enemy_drops_always",
]
options = {
    "enemies_random": {"scope": "per_level"},   # keep swaps inside the same area
    "door_destination_remap": {"how": "shuffle", "require_script": False},
    "xp_scale": {"percent": 200},                # boosted XP (double)
}
binary_patches = [["skip_intro", {}], ["skip_tutorial", {}]]


def main():
    res = rc.randomize_iso(SRC_ISO, OUT, SEED, transforms, progress=progress,
                           options=options, binary_patches=binary_patches)
    summarize(res, OUT, SEED)


if __name__ == "__main__":
    main()
