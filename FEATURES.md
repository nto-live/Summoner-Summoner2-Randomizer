# Features and Options — the authoritative list

*Generated 2026-09-21 from the engine's own registry, then measured: every transform below was
run against the retail `TABLES.VPP` stream (6,771,975 bytes) with a fixed seed, and the edit and
byte counts are what it actually did. Regenerate with `inventory.py`; do not hand-edit the
numbers.*

**Counts:** 37 transforms · 29 modes · 6 option-bearing transforms · 7 blocked items.

Status vocabulary, and it is used strictly:

| Status | Means |
|---|---|
| **verified in game** | built into a disc and observed working on the emulator |
| **built, unverified** | the bytes change as intended and stay size-preserving; nobody has watched the effect in game |
| **blocked** | not implemented, with the reason and what it is waiting on |

**Every transform is size-preserving.** The 527 `TABLES.VPP` entries are arbitrary slices of one
stream, so a value is only ever rewritten inside its own field width. A run that would move a
boundary is refused rather than done.

---

## 0. Where the features actually live — read this first

**The door destination remap is not in the engine.** It is the headline feature, it is proven in
game (see `DOOR-REMAP.md` §4.5), and it is currently a *lab script*: `make_door_test_iso.py` /
`apply_door_remap.py` write `$Trigger:` names into a copy of the disc. The engine's `doors` mode
shuffles `$Door` names, locks and sounds — cosmetics — and nothing in `cli.py` can remap a door
destination.

That is the top item of work, and the blocked list was lying about it: `PENDING["door_destination_swap"]`
still claims *"Door destinations are not in TABLES.VPP"*, which is exactly the conclusion that
was overturned on 2026-09-20. The entry needs to go, and the transform needs to exist.

### Three bugs the inventory found, all fixed and re-measured

| Bug | Before | After |
|---|---|---|
| `impossible` mode did nothing | 0 edits (dial left at `normal` = vanilla) | **803 edits**, `{"level": "impossible"}` |
| `easy_enemies` mode did nothing | 0 edits | **803 edits**, `{"level": "easy"}` |
| `progression` mode did nothing *from the CLI* | 0 edits (`xp_scale`/`levelcap_set` left at 100%) | **198 edits**, 200% each |

Root cause for all three: a mode's own option values (`MODES[x]["options"]`) were never merged
into the request. The engine now resolves them in one place (`rando_core.mode_options`), so the
CLI, the app and any harness agree — and the rule is written down in the code: **every mode that
uses a dial must set a value, and mode values are defaults, not overrides.**

---

## 1. Content features

| Transform | Edits | Bytes | Status | Notes |
|---|---:|---:|---|---|
| `npc_character_shuffle` | 5,588 | 60,659 | built, unverified | 6,256 `$Character` values across 25 length classes — who stands where |
| `enemies_swarm` | 1,783 | 23,280 | built, unverified | 1,783 peaceful placements re-pointed at hostile creatures; 234 skipped (no same-length name). Eats quest NPCs — chaos tier |
| `enemies_random` | 1,697 | 14,277 | built, unverified | swaps which creature stands on each of 2,220 placements + shuffles `+Level:` |
| `model_ref_shuffle` | 2,380 | 26,130 | built, unverified | 2,426 `.mvf` model refs |
| `item_scatter` | 155 | 1,944 | built, unverified | which item sits at which loose pickup (177 `$Item`) |
| `shop_shuffle` | 348 | 423 | built, unverified | 479 `$Value` prices |
| `chest_shuffle` | 23 | 24 | built, unverified | weak by nature: most single-digit `+Give` values are item counts |
| `spawn_shuffle` | 4,467 | 9,737 | built, unverified | 4,594 `$Start position` anchors — relocates who stands where |
| `material_shuffle` | 76 | 272 | built, unverified | 337 `$Material`, 5 length classes |
| `sound_shuffle` | 1,681 | 24,425 | built, unverified | 1,808 `.wav` refs |
| `music_shuffle` | 1,109 | 14,725 | built, unverified | `$Soundtrack` + `$Sound` |
| `icon_shuffle` | 478 | 2,492 | built, unverified | `$Icon` + `.vbm` refs |
| `vfx_shuffle` | 352 | 3,719 | built, unverified | 412 `.vfx` refs |
| `camera_shuffle` | 150 | 750 | built, unverified | `$Camera` + `.csc` |
| `fog_shuffle` | 53 | 58 | built, unverified | 101 `$Fog` |
| `slot_shuffle` | 104 | 436 | built, unverified | 280 `+Slot` |
| `dialogue_shuffle` | 4,938 | 554,905 | built, unverified | 5,452 `+NPCText` + 201 `+Messagebox`; topic ids deliberately untouched |
| `action_shuffle` | 5,155 | 35,301 | built, unverified | 11,606 `+Action` verbs across 12 length classes — **can break scripted sequences** |
| `animation_shuffle` | 2,165 | 24,404 | built, unverified | `$Animation` + `+Animation class` |
| `cutscene_shuffle` | 72 | 733 | built, unverified | 84 `$Cutscene` names |

## 2. Enemies

| Transform | Edits | Bytes | Status | Notes |
|---|---:|---:|---|---|
| `enemies_none` | 4,067 | 12,201 | **verified in game** | all 2,220 monster placements unlinked from their navpoints; control run: Liangshan 100→17, sewer 65→12 (`ENEMIES.md` §4) |
| `enemy_difficulty` | 803 | 1,685 | built, unverified | 51 hostile stat sheets + 293 placement levels; dial `trivial/easy/normal/hard/brutal/deadly/impossible` |
| `creature_stats_shuffle` | 1,285 | 1,781 | built, unverified | 337 `$Speed`, 337 `$Weight`, 306 `$Attack Radius` |

## 3. Progression — how the game ends, and how fast you get there

| Transform | Edits | Bytes | Status | Notes |
|---|---:|---:|---|---|
| `ring_hunt` | 1–4 | 13–48 | built, unverified | renames a 13-character `+Event:` flag to `ready_for_end`; `any-ring` uses 4 anchors, `safe` end-of-act only |
| `xp_scale` | 172 @200% | 321 | built, unverified | 248 `+AddXP:` rewards, deterministic |
| `levelcap_set` | 26 @200% | 40 | built, unverified | 26 `+Levelcap:` values |
| `xp_boost` / `xp_nerf` | 172 / 248 | 587 / 777 | built, unverified | fixed-factor versions of the same dial |
| `levelcap_raise` | 25 | 38 | built, unverified | pushes caps toward 50 |
| `permadeath` | 8 | 62 | built, unverified | revive ability renamed; grant sites orphaned, definition left intact |
| `economy_squeeze` | 534 | 1,533 | built, unverified | prices up, gold down |
| `endgame_gate` *(binary)* | 1 word | 1 byte | **verified in game** | lowers the gamestage threshold that arms the ending; the emulator's CRC changes as proof |

## 4. Presentation and pacing

| Transform | Edits | Bytes | Status | Notes |
|---|---:|---:|---|---|
| `dialogue_blank` | 5,694 | 595,878 | built, unverified | 2.6 M characters of reading removed, length exact, newlines kept |
| `cutscene_bypass` | 84 | 84 | built, unverified | `$Cutscene` → `$Xutscene`, single-byte revert |
| `fade_instant` | 184 | 225 | built, unverified | zeroes fade durations |
| `lock_shuffle` | 79 | 81 | built, unverified | 146 `+Locked` values |
| `door_name_shuffle` | 260 | 2,014 | built, unverified | 292 `$Door` names — cosmetic, **not** destinations |
| `door_sound_shuffle` | 109 | 1,134 | built, unverified | 256 door sounds |

## 5. Modes (29)

Every mode is a named preset over the transforms above. Risk is the honest reading of what it
does, not a promise.

| Mode | Key | Tx | Its own options | Status |
|---|---|---:|---|---|
| Vanilla | `vanilla` | 0 | — | baseline |
| **No Enemies** | `peaceful` | 1 | how=navpoint | **verified in game** |
| Door Shuffle | `doors` | 3 | — | cosmetics only — *the name overpromises until the remap lands* |
| Chaos | `chaos` | 5 | — | unverified |
| Short Run | `short` | 2 | — | unverified |
| One Hour | `one_hour` | 3 | — | unverified |
| **Enemy Swarm** | `invasion` | 2 | — | unverified, high risk |
| **Impossible Enemies** | `impossible` | 1 | level=impossible | fixed today; unverified |
| **Easy Enemies** | `easy_enemies` | 1 | level=easy | fixed today; unverified |
| Everything | `everything` | 24 | — | unverified |
| Ring Hunt | `ring_hunt` | 1 | — | unverified, changes the ending |
| Ring Hunt · Any Ring | `ring_hunt_any` | 1 | anchor=any-ring | unverified |
| Ring Hunt · Short | `ring_hunt_short` | 4 | — | unverified |
| **Progression** | `progression` | 2 | 200% / 200% | fixed today; unverified |
| Item Scatter | `item_scatter` | 1 | — | unverified |
| Shop Shuffle | `shop_shuffle` | 1 | — | unverified |
| Chest Shuffle | `chest_shuffle` | 1 | — | unverified |
| Dialogue Chaos | `dialogue_chaos` | 1 | — | unverified |
| Sound Chaos | `sound_chaos` | 2 | — | unverified |
| Monster Chaos | `monster_chaos` | 2 | — | unverified |
| Behaviour Chaos | `behaviour_chaos` | 2 | — | unverified, can break scripts |
| Visual Chaos | `visual_chaos` | 4 | — | unverified |
| Total Chaos | `total_chaos` | 26 | — | unverified |
| Fast Start | `fast_start` | 4 | — | unverified |
| No Dialogue | `no_dialogue` | 2 | — | unverified |
| Roguelike | `roguelike` | 12 | — | unverified |
| Roguelike · Short | `roguelike_short` | 12 | — | unverified |
| Hardcore | `hardcore` | 13 | — | unverified |
| Endgame Gate (binary) | `endgame_gate` | 0 (+1 word) | stage=5 | **verified in game** |

## 6. Options (6 option-bearing transforms)

| Transform | Option | Values | Default |
|---|---|---|---|
| `enemy_difficulty` | `level` | trivial · easy · normal · hard · brutal · deadly · impossible | normal |
| `enemy_difficulty` | `level_shift` | −20…+20 creature levels | 0 |
| `enemies_none` | `how` | navpoint · both · team *(blocked)* | navpoint |
| `ring_hunt` | `anchor` | any-ring · safe · 11 named flags | seeded pick |
| `ring_hunt` | `count`, `safe_only` | 1…11 anchors, flag | 1, true |
| `xp_scale` | `percent` | 5…999 | 100 |
| `levelcap_set` | `percent` | 5…999 | 100 |
| `permadeath` | `block_ability`, `block_items` | true/false | both true |

## 7. Blocked, with reasons

| Item | Waiting on |
|---|---|
| Encounter-rate scaling | the `#Resistances` block layout is unmapped |
| Character colours | `.peg` texture format undecoded |
| Item relocation (proper) | the blob's segmentation map |
| Level order | the runtime level-id → name table |
| One Hour (true version) | a flag graph + reachability solver |
| Character models | `.mvf` format |
| **Door destination remap** | *nothing — this is implementable now and is next* |

## 8. The test plan this catalogue sets up

Every row above is a checklist item. The testing phase runs down it and moves rows from **built,
unverified** to **verified in game** — or files what broke. Highest value first:

1. **Door destination remap in the engine** — implement, then re-run the A/B that already passes
   for the lab script (`DOOR-REMAP.md` §4.5).
2. **Ring Hunt** — does the ending really open at the renamed flag.
3. **Enemy Swarm, Enemy Difficulty** — the dial's effect on a fight; swarm's effect on quests.
4. **Progression dials** — XP at 200%, caps, permadeath.
5. **Fast Start / No Dialogue / cutscene bypass / instant fades** — the pacing stack.
6. **Cosmetics** — sound, music, models, icons, cameras, fog: cheap to confirm, and they are the
   features that make a run feel different.
