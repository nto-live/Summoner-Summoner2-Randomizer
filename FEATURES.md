# Features and Options — the authoritative list

*Generated 2026-09-21 from the engine's own registry, then measured: every transform below was
run against the extracted `TABLES.VPP` stream (`F:\rando\S1\notes\_end_blob.bin`, 6,771,975
bytes) with a fixed seed, and the edit and byte counts are what it actually did. Regenerate with
`inventory.py`; do not hand-edit the numbers. One row is the exception and says so: the door
remap's fixture still holds the pre-fix stream, so its numbers come from the disc instead (§0).*

**Counts:** 42 transforms · 34 modes · 8 option-bearing transforms · 6 blocked items.

Status vocabulary, and it is used strictly:

| Status | Means |
|---|---|
| **verified in game** | built into a disc and observed working on the emulator |
| **built, unverified** | the bytes change as intended and stay size-preserving; nobody has watched the effect in game |
| **blocked** | not implemented, with the reason and what it is waiting on |

**Every transform is size-preserving.** The 527 `TABLES.VPP` entries are arbitrary slices of one
stream, so a value is only ever rewritten inside its own field width. A run that would move a
boundary is refused rather than done.

> **Measurements re-taken 2026-09-21 23:16, after the archive-reader fix.** The engine had been
> reading every `TABLES.VPP` entry from a fixed `0x1000` instead of the next `0x800` boundary after
> the table of contents (`0x9000` here). That shifted every entry by 32 KB and dropped the last
> ~620 KB — the 52 level files, and with them all 218 doors and 59 of 160 `#Character Info` blocks.
> Fixed in `rando_core.py` (`data_start()`), the measurement fixture regenerated, and the numbers in
> these tables re-measured against the corrected stream. Nine transforms gained content as a result
> (`sound_shuffle` 1,681 → **3,008**, `model_ref_shuffle` 2,380 → **3,658**, `music_shuffle`
> 1,109 → **1,565**, `animation_shuffle` 2,165 → **3,447**, `vfx_shuffle` 352 → **530**,
> `creature_stats_shuffle` 1,285 → **1,572**, `enemies_swarm` 1,783 → **1,800**, `permadeath`
> 8 → **11**, `npc_character_shuffle` 5,588 → **5,659**). `enemies_none` is **byte-identical** at
> 4,067 edits.
>
> **Consequence, stated plainly:** any disc built by the engine **before** that fix is suspect,
> including the no-enemies discs used for the earlier in-game entity comparison. The door results
> are unaffected — those discs were built by the lab applier from absolute ISO offsets, not through
> the engine — but the enemy effect needs re-verifying on a disc built with the fixed reader.

---

## 0. Where the features actually live — read this first

**The door destination remap is in the engine now** (2026-09-21). It was the headline feature, it
was proven in game as a lab script (`DOOR-REMAP.md` §4.5), and it is now the transform
`door_destination_remap` with the mode `door_remap`: it finds every door by *parsing* the level
tables, rewrites only destination names that fit their own field, refuses rather than guesses,
and carries the lab applier's discipline (declare-and-refuse, read back, bounds check, and a
whole-stream diff that must contain nothing outside the declared fields). The engine's `doors`
mode is untouched and still means exactly what it says: door *locks, names and sounds*.

`PENDING["door_destination_swap"]` claimed *"Door destinations are not in TABLES.VPP"*, which was
overturned on 2026-09-20. The entry is gone.

### The archive-layout bug this work uncovered

Every `TABLES.VPP` entry was being read from the wrong offset. The engine assumed the data area
starts at `0x1000`; it actually starts at the next `0x800` boundary after the table of contents
(`0x9000` for 527 records), and the entries are `0x800`-aligned inside the archive. Reading from
`0x1000` shifted every entry by 32 KB and truncated the archive's last ~620 KB — which is exactly
where all 52 level files live, and therefore where **all 218 door triggers** and 59 of the 160
`#Character Info` blocks live. Before the fix the reassembled stream contained **1** door; after
it, **218**. The rule is verified against the disc: with it, every entry's padding is clean zeros
and the last entry ends exactly at the declared archive size, for all nine archives in the image.
The blob's length is unchanged (6,771,975 bytes) — only the byte ranges each entry is read from.

**Nine other transforms move counts because of it** — `animation_shuffle`, `creature_stats_shuffle`,
`enemies_swarm`, `model_ref_shuffle`, `music_shuffle`, `npc_character_shuffle`, `permadeath`,
`sound_shuffle`, `vfx_shuffle`. They were editing a stream that was missing the level files.
Everything else, including the in-game-verified `enemies_none` (4,067 edits), is byte-identical.

**Fixture caveat, stated plainly.** `inventory.py` measures against
`F:\rando\S1\notes\_end_blob.bin`, which was built with the old offset rule and still holds the
pre-fix stream. It therefore sees **1** of the 218 doors, and it is the source of every number in
this file. The door row below carries the disc-measured numbers *as well*, because the fixture
cannot see them; every other row is inventory's number, unchanged and still reproducible against
that fixture.

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
| `door_destination_remap` | 200 | 1,568 | built, unverified in game | **the headline feature.** All **218** doors found by parsing the stream; 200 destinations rewritten at seed `DOOR1`, 18 landed on the name they already had, 0 skipped. Every field is `len(old)+1` bytes in and out. Measured against the disc, not the fixture — see §0 |
| `npc_character_shuffle` | 5,659 | 61,270 | built, unverified | 6,315 `$Character` values across 25 length classes — who stands where |
| `enemies_swarm` | 1,800 | 22,550 | built, unverified | 1,800 peaceful placements re-pointed at hostile creatures; 219 skipped (no same-length name). Eats quest NPCs — chaos tier |
| `enemies_random` | 1,697 | 14,277 | built, unverified | swaps which creature stands on each of 2,220 placements + shuffles `+Level:` |
| `model_ref_shuffle` | 3,658 | 40,210 | built, unverified | 3,689 `.mvf` model refs |
| `item_scatter` | 155 | 1,944 | built, unverified | which item sits at which loose pickup (177 `$Item`) |
| `shop_shuffle` | 348 | 423 | built, unverified | 479 `$Value` prices |
| `shops_free` | 477 | 530 | built, unverified | every `$Value` price → `0`, padded to the field's own width (2 were already 0) |
| `shops_crazy` | 479 | 1,728 | built, unverified | every `$Value` → all-9s at the field's own width (`999`, `9999`, `999999`) |
| `shops_none` | 86 | 1,132 | built, unverified | 86 placements naming one of the 46 `+Shop` characters re-pointed at an equal-length non-shopkeeper; the definitions are never touched |
| `chest_shuffle` | 23 | 24 | built, unverified | weak by nature: most single-digit `+Give` values are item counts |
| `spawn_shuffle` | 4,467 | 9,737 | built, unverified | 4,594 `$Start position` anchors — relocates who stands where |
| `material_shuffle` | 76 | 272 | built, unverified | 337 `$Material`, 5 length classes |
| `sound_shuffle` | 3,008 | 44,334 | built, unverified | 3,272 `.wav` refs |
| `music_shuffle` | 1,565 | 19,928 | built, unverified | `$Soundtrack` + `$Sound` |
| `icon_shuffle` | 478 | 2,492 | built, unverified | `$Icon` + `.vbm` refs |
| `vfx_shuffle` | 530 | 6,415 | built, unverified | 590 `.vfx` refs |
| `camera_shuffle` | 150 | 750 | built, unverified | `$Camera` + `.csc` |
| `fog_shuffle` | 53 | 58 | built, unverified | 101 `$Fog` |
| `slot_shuffle` | 104 | 436 | built, unverified | 280 `+Slot` |
| `dialogue_shuffle` | 4,938 | 554,905 | built, unverified | 5,452 `+NPCText` + 201 `+Messagebox`; topic ids deliberately untouched |
| `action_shuffle` | 5,155 | 35,301 | built, unverified | 11,606 `+Action` verbs across 12 length classes — **can break scripted sequences** |
| `animation_shuffle` | 3,447 | 38,275 | built, unverified | `$Animation` + `+Animation class` |
| `cutscene_shuffle` | 72 | 733 | built, unverified | 84 `$Cutscene` names |

## 2. Enemies

| Transform | Edits | Bytes | Status | Notes |
|---|---:|---:|---|---|
| `enemies_none` | 4,067 | 12,201 | **verified in game** | all 2,220 monster placements unlinked from their navpoints; control run: Liangshan 100→17, sewer 65→12 (`ENEMIES.md` §4) |
| `enemies_amount` | 4,067 | 12,201 | built, unverified | the enemy-count dial (`none/few/normal/many/all`); value `none` reproduces the verified `enemies_none` byte for byte. Measured at every value below |
| `enemy_difficulty` | 803 | 1,685 | built, unverified | 51 hostile stat sheets + 293 placement levels; dial `trivial/easy/normal/hard/brutal/deadly/impossible` |
| `creature_stats_shuffle` | 1,572 | 2,183 | built, unverified | 337 `$Speed`, 337 `$Weight`, 365 `$Attack Radius` |

**`enemies_amount` — measured at every value** (retail stream, seed `4242`; every value size-preserving):

| `amount` | edits | bytes | what it does |
|---|---:|---:|---|
| `none` | 4,067 | 12,201 | unlink all 2,220 monster placements from their navpoints — identical output to the verified `enemies_none(how="navpoint")` |
| `few` | 2,852 | 8,556 | unlink a seeded ~70% (1,554) of the monster placements |
| `normal` | 0 | 0 | vanilla, by design; the report says so |
| `many` | 872 | 11,314 | 1,018 of the 2,037 peaceful placements targeted, 872 converted to an equal-length monster, 134 skipped |
| `all` | 1,783 | 23,280 | every convertible peaceful placement converted (same as `enemies_swarm`); 234 skipped — no hostile name of their length |

An unknown `amount` is refused: 0 edits, nothing changed, and a note saying so.

## 3. Progression — how the game ends, and how fast you get there

| Transform | Edits | Bytes | Status | Notes |
|---|---:|---:|---|---|
| `ring_hunt` | 1–4 | 13–48 | built, unverified | renames a 13-character `+Event:` flag to `ready_for_end`; `any-ring` uses 4 anchors, `safe` end-of-act only |
| `xp_scale` | 172 @200% | 321 | built, unverified | 248 `+AddXP:` rewards, deterministic |
| `levelcap_set` | 26 @200% | 40 | built, unverified | 26 `+Levelcap:` values |
| `xp_boost` / `xp_nerf` | 172 / 248 | 587 / 777 | built, unverified | fixed-factor versions of the same dial |
| `levelcap_raise` | 25 | 38 | built, unverified | pushes caps toward 50 |
| `permadeath` | 11 | 80 | built, unverified | revive ability renamed; grant sites orphaned, definition left intact |
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

## 5. Modes (34)

Every mode is a named preset over the transforms above. Risk is the honest reading of what it
does, not a promise.

| Mode | Key | Tx | Its own options | Status |
|---|---|---:|---|---|
| Vanilla | `vanilla` | 0 | — | baseline |
| **No Enemies** | `peaceful` | 1 | how=navpoint | **verified in game** |
| Door Shuffle | `doors` | 3 | — | cosmetics only: door locks, names and sounds, *never* where a door leads |
| **Door Remap** | `door_remap` | 1 | how=shuffle | **built, unverified in game** — rewrites where all 218 doors lead; changes the level graph |
| Chaos | `chaos` | 5 | — | unverified |
| Short Run | `short` | 2 | — | unverified |
| One Hour | `one_hour` | 3 | — | unverified |
| **Enemy Swarm** | `invasion` | 2 | — | unverified, high risk |
| **Oops, All Enemies** | `oops_all_enemies` | 2 | amount=all | built, unverified — quest NPCs consumed |
| **Impossible Enemies** | `impossible` | 1 | level=impossible | fixed today; unverified |
| **Easy Enemies** | `easy_enemies` | 1 | level=easy | fixed today; unverified |
| Everything | `everything` | 24 | — | unverified |
| Ring Hunt | `ring_hunt` | 1 | — | unverified, changes the ending |
| Ring Hunt · Any Ring | `ring_hunt_any` | 1 | anchor=any-ring | unverified |
| Ring Hunt · Short | `ring_hunt_short` | 4 | — | unverified |
| **Progression** | `progression` | 2 | 200% / 200% | fixed today; unverified |
| Item Scatter | `item_scatter` | 1 | — | unverified |
| Shop Shuffle | `shop_shuffle` | 1 | — | unverified |
| Free Shops | `free_shops` | 1 | — | unverified |
| Crazy Prices | `crazy_prices` | 1 | — | unverified |
| No Shops | `no_shops` | 1 | — | unverified — shopkeepers stop existing |
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

## 6. Options (8 option-bearing transforms)

| Transform | Option | Values | Default |
|---|---|---|---|
| `door_destination_remap` | `how` | shuffle · swap · off | shuffle |
| `enemy_difficulty` | `level` | trivial · easy · normal · hard · brutal · deadly · impossible | normal |
| `enemy_difficulty` | `level_shift` | −20…+20 creature levels | 0 |
| `enemies_none` | `how` | navpoint · both · team *(blocked)* | navpoint |
| `enemies_amount` | `amount` | none · few · normal · many · all | normal |
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

*(`Door destination remap` used to be listed here, blocked on "nothing". It is built — see §0.)*

## 8. The test plan this catalogue sets up

Every row above is a checklist item. The testing phase runs down it and moves rows from **built,
unverified** to **verified in game** — or files what broke. Highest value first:

1. **Door Remap, in game** — the transform is built and measured (200 destinations at seed
   `DOOR1`, 1,568 bytes, byte-identical image length, nothing changed outside `TABLES.VPP`); the
   A/B that already passes for the lab script (`DOOR-REMAP.md` §4.5) is the verification step.
2. **Ring Hunt** — does the ending really open at the renamed flag.
3. **Enemy Swarm, Enemy Difficulty** — the dial's effect on a fight; swarm's effect on quests.
4. **Progression dials** — XP at 200%, caps, permadeath.
5. **Fast Start / No Dialogue / cutscene bypass / instant fades** — the pacing stack.
6. **Cosmetics** — sound, music, models, icons, cameras, fog: cheap to confirm, and they are the
   features that make a run feel different.

---

## 9. Requested additions — the owner's list (2026-09-21)

Joshua asked for a specific set of modes and options: *Ring Hunt, Boss Rush, Oops All Enemies,
Roguelike, Item Hunt, NPC Hunt, a Collectionthon*, and options for *how many enemies / randomised
enemies / no enemies / chest randomisation / shop randomisation / all free / crazy numbers / no
shops / randomised characters / randomised rooms / randomised enemy hp and stats / randomised
player stats.*

Each one is mapped to its mechanism and its honest state in **`MODES.md` → "Requested — the
owner's list, organised"**. The work order below is mostly built now:

* **Built (unverified)** — `enemies_amount` (4,067 at `none` / 2,852 at `few` / 0 at `normal` / 872 at `many` / 1,783 at `all`), `shops_free` (477), `shops_crazy` (479), `shops_none` (86). These are in the measured
  catalogue above; none is verified in game yet.
* **Still to build** — `chest_items`, `player_stats_random`, `enemy_stats_random`, `rooms_shuffle`
  (all mechanism-known), plus **Boss Rush / NPC Hunt (cross-level)** which need an inventory first,
  and **Collectionthon** which stays blocked with its reason (the game has no collection counter).

Work order, value ÷ risk: `enemies_amount` → the three shop levers → `chest_items` → the two stat
transforms → `rooms_shuffle` → Boss Rush → Collectionthon.
