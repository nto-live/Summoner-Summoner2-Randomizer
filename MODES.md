# Modes and Options

The full list. Everything here is implemented, size-preserving and reversible.
"Untested in game" means exactly that — the emulator still needs a logged-in desktop
session before any of it can be watched happening.

Run `python build.py --list` for the same thing from the terminal.

---

## Requested — the owner's list, organised (2026-09-21)

Joshua, verbatim: *"I want these modes. Ring hunt, Boss Rush, Oops all enemies, roguelike mode,
item hunt, npc hunt, a collectionthon. Options: How many Enemies? Randomized? No enemies? Chest
Randomization. Shop Randomization / Make it all free / Make it all crazy numbers. No Shops /
randomized characters / Randomized rooms / Randomized enemy hp and stats. Randomized player
stats."*

Below is every requested item, the mechanism it maps onto, and its honest state. Status is one
of: **exists** (shipped), **build now** (mechanism known, size-preserving, no unknowns),
**designed** (needs an inventory or a design decision first), **blocked** (with the reason).

### Modes

| Requested | Mechanism | Status |
|---|---|---|
| **Ring Hunt** | rename a 13-character `+Event:` flag to `ready_for_end`; `any-ring` = 4 anchors with a ring beside them | **exists** (`ring_hunt`) |
| **Boss Rush** | bosses are placements carrying `+Boss`; the first version re-points every boss placement's `$Start position` at navpoints inside one arena level, so they stand together | **designed** — needs the boss inventory (blocks with `+Boss`) and the arena's navpoint list. A true gauntlet (arena → arena chaining) rides on the level graph |
| **Oops All Enemies** | every placement becomes hostile: 2,037 peaceful placements re-pointed at creature names, plus the 2,220 monsters kept and randomised | **built, unverified** — mode `oops_all_enemies`: `enemies_amount` all (1,783 conversions) + `enemies_random` |
| **Roguelike** | the pressure stack: creature stats, spawns, loot, shops, chests scrambled; XP cut; prices up | **exists** (`roguelike`) |
| **Item Hunt** | loose pickups re-scattered (`item_scatter`) *and* items moved out of shop stock and quest rewards into containers, so they have to be found | **partially exists** — the scatter half ships; the "out of shops, into chests" half is `chest_items` + shop-stock work |
| **NPC Hunt** | NPCs stop being where you left them: placement anchors shuffled (`spawn_shuffle`) and identities shuffled (`npc_character_shuffle`), stacked into one mode | **build now** (a mode over two shipped transforms); the stronger version — NPCs relocated across *levels* — is **designed** |
| **Collectionthon** | a run that is about collecting: all pickups + all chest contents relocated, and the ending gated on having collected them | **designed, and partly blocked**: the game has no collection counter. Two candidate mechanisms: (a) rename an unused `+Event:` flag to `ready_for_end` and set it at the last collection point — cheap but only checks one item; (b) a binary patch to gate the ending on a counter — the layer exists, the counter does not. Reason recorded rather than hand-waved |

### Options

| Requested | Mechanism | Status |
|---|---|---|
| **How many enemies?** | one dial over one mechanism set: `none` = navpoint-unlink (already proven in game), `few` = unlink a seeded majority, `normal` = untouched, `many` = convert a seeded share of peaceful placements to monsters, `all` = convert all of them | **built, unverified** — `enemies_amount` (4,067 / 2,852 / 0 / 872 / 1,783 edits across none / few / normal / many / all); subsumes three of the items below |
| **Randomized (enemies)?** | swap which creature stands on each placement, and its `+Level:`, between equal-length values | **exists** (`enemies_random`) — needs exposing as a dial rather than a separate mode |
| **No enemies?** | every monster placement unlinked from its navpoint | **exists and verified in game** (`enemies_none`) — now also `enemies_amount: none`, which reproduces it byte for byte (4,067 edits) |
| **Chest randomisation** | payouts shuffled (`chest_shuffle`, ships) **and** which *item* a container yields (`+Give` names), between equal-length item names | **half exists** — `chest_items` is **build now** |
| **Shop randomisation** | every `$Value` price shuffled among equal widths | **exists** (`shop_shuffle`) |
| **Make it all free** | every `$Value` price → `0`, same field width | **built, unverified** — `shops_free` (477 edits) |
| **Make it all crazy numbers** | every `$Value` → the largest value its field can hold (`999`, `9999`…) | **built, unverified** — `shops_crazy` (479 edits) |
| **No shops** | re-point the placements that name a `+Shop` character at equal-length non-shopkeepers, so the shop does not exist | **built, unverified** — `shops_none` (86 placements across 46 shopkeepers); note the marker lives on the character's dialogue definition, not `#Character Info` |
| **Randomized characters** | shuffle `$Character` values between equal lengths — who stands where | **exists** (`npc_character_shuffle`) |
| **Randomized rooms** | permute what populates a level *within* the level: shuffle `$Start position` anchors between placements of the same kind in the same level, so rooms are furnished differently while the level graph, doors and quests stay intact. This is the safe half of the design fork in `RESEARCH-ENTRANCE-LOGIC.md` §2 | **build now, first version** — `rooms_shuffle`. The deeper version (a level's whole interior swapped with another's) is **designed** |
| **Randomized enemy hp and stats** | two levers, both shipped separately: `enemy_difficulty` *scales* hit points/aggression/ranges; `creature_stats_shuffle` *shuffles* speed/weight/attack radius. Requested form = shuffle the hostile `#Character Info` numbers themselves | **build now** — `enemy_stats_random` |
| **Randomized player stats** | shuffle the numeric fields between **friendly** `#Character Info` blocks (the playable party), equal widths only | **build now** — `player_stats_random` |

### The build queue this produces

Ordered by value ÷ risk, all size-preserving:

1. `enemies_amount` — one dial that covers "how many enemies", "no enemies" and "oops all enemies" — **done**
2. `shops_free`, `shops_crazy`, `shops_none` — three small, self-contained shop levers — **done**
3. `chest_items` — real chest randomisation instead of payout shuffling
4. `player_stats_random`, `enemy_stats_random` — the two stats items
5. `rooms_shuffle` — the safe half of the room idea
6. **Boss Rush** — needs a boss inventory first
7. **Collectionthon** — needs a completion mechanism; the reason is recorded, not skipped

---

## Modes (33)

| Mode | What it changes | Tx | Risk |
|---|---|---|---|
| **Vanilla** | nothing — baseline | 0 | none |
| **Door Shuffle** | door locks, names, sounds — **not** destinations; see the note below | 3 | low |
| **Item Scatter** | which item sits at which pickup | 1 | low |
| **Shop Shuffle** | every shop price | 1 | low |
| **Free Shops** | every shop price → `0`, same field width | 1 | low |
| **Crazy Prices** | every shop price → the largest value its field holds | 1 | low |
| **No Shops** | shopkeeper placements re-pointed so no shop can be reached | 1 | medium |
| **Chest Shuffle** | container payouts | 1 | low |
| **Dialogue Chaos** | NPCs say each other's lines | 1 | low |
| **Sound Chaos** | every sound effect and music cue | 2 | low |
| **Visual Chaos** | item icons, spell effects, fog, cameras | 4 | low |
| **Chaos** | characters, models, cutscenes, materials | 5 | low |
| **Monster Chaos** | creature stats + spawn points | 2 | medium |
| **Short Run** | cutscenes bypassed + XP scaled | 2 | medium |
| **One Hour** | + creature level caps raised | 3 | medium |
| **Fast Start** | cutscenes skipped, dialogue blanked, instant fades, combat scaled | 4 | medium |
| **No Dialogue** | every line and objective blanked | 2 | medium |
| **Ring Hunt** | **which event opens the Forge of Urath** | 1 | medium |
| **Ring Hunt · Any Ring** | **ending opens on any of seven rings** | 1 | medium |
| **Ring Hunt · Short** | Ring Hunt + no cutscenes + no grind | 4 | medium |
| **Progression** | **XP and level-cap dials, set by hand** | 2 | low |
| **No Enemies** | **every monster spawn unlinked from its navpoint; hostile definitions re-teamed** | 1 | medium |
| **Enemy Swarm** | **peaceful placements become monsters, then the monsters are reshuffled** | 2 | **high** |
| **Enemy Difficulty** (Easy / Impossible) | **hostile creature stats and placement levels scaled** | 1 | low / high |
| **Oops, All Enemies** | **every peaceful placement becomes a hostile creature, then the monsters are reshuffled** | 2 | **high** |
| **Roguelike** | the full pressure stack — creatures, spawns, loot, shops, XP, prices | 12 | high |
| **Roguelike · Short** | Roguelike with the length taken out | 12 | high |
| **Hardcore** | **Roguelike + permadeath — death sticks** | 13 | very high |
| **Behaviour Chaos** | NPC actions and animations | 2 | **high** |
| **Everything** | 24 transforms — everything cosmetic/world; behaviour, pacing and the dials excluded | 24 | medium |
| **Total Chaos** | all 26 including behaviour | 26 | very high |
| **Custom** | hand-pick anything | — | varies |
### Fast Start — what it actually fixes

| Component | Effect | Measured |
|---|---|---|
| `cutscene_bypass` | cutscene playback never fires | 84 tokens |
| `dialogue_blank` | all spoken text and objectives emptied | 5,687 lines |
| `fade_instant` | scene-transition pauses removed | 184 fades |
| `xp_boost` | combat stops being a grind | 248 rewards |

**Three honest caveats:**

1. **The startup movie is NOT addressable from the data layer.** There are **zero `.pss`
   references** in the tables — the intro is played by the executable
   (`code/vsdk/ps2_movieplayer/mplayer.o`). Skipping it needs an ELF patch or a PSS
   replacement, not a text edit. `cutscene_bypass` covers the in-game cutscenes, not the
   boot video.
2. **`dialogue_blank` removes the reading, not the key press.** Boxes still appear and may
   still need advancing. It empties 2.6 million characters; it cannot change how the
   dialogue system waits.
3. Nothing here is verified in game yet.

---

## Door Shuffle is *not* destination shuffling

Worth stating plainly, because the name invites the mistake: the shipped **Door Shuffle** mode
shuffles door **locks, names and sounds** (`lock_shuffle`, `door_name_shuffle`,
`door_sound_shuffle`). It never changes where a door *leads*.

**Where a door leads** is a `$Trigger:` name in the level's own `.tbl` — a text-layer field, 218 of
them on the disc. Rewriting it is proven to work: 218 patches applied, size byte-identical, zero
collateral bytes, and the disc **boots**. Full record: **`DOOR-REMAP.md`**.

That capability is **not yet a mode in the app** — the applier is still a standalone script. The
planned modes are:

| Planned mode | What it does | Risk |
|---|---|---|
| **Room Shuffle** | permutes what a level is *made of*, keeping the level graph intact — the safe default | medium |
| **Door Remap** | rewrites `$Trigger:` destinations — changes the graph, so it needs the reachability guard | high |

Both are blocked on work, not on unknowns: `binary.py`'s registry is ELF-word-only, so
`TABLES.VPP` byte-range edits need a sibling `DATA_PATCHES` registry (`DOOR-REMAP.md` §6.1), and
Door Remap additionally needs the flood-fill guard (`RESEARCH-ENTRANCE-LOGIC.md` §4).

---

## Enemies

Full model, measurements and the difficulty dial: **`ENEMIES.md`**. Headlines:

- An enemy in a level is a `#Objects` placement: `$Name: "Bone King#$npc038"`,
  `$Character: "Bone King"`, `+Monster`, `$Start position: "$npc038"`. **2,220** of them, **80**
  distinct creatures, 2,037 peaceful placements alongside.
- A creature's numbers live in one of **101** `#Character Info` blocks (51 hostile): hit points,
  aggressiveness, attack radius, view/detection range, movement rates.
- **No Enemies** — `$npcNNN` → `$zzzNNN` (4,067 edits) and/or re-team the 51 hostile
  definitions (51 edits). Which lever actually empties a level is **not yet verified in game**.
- **Enemy Swarm** — 1,783 of 2,037 peaceful placements can be re-pointed at a hostile creature
  of the same name length. The other 234 have no matching length. Quest NPCs are consumed.
- **Enemy Difficulty** — `trivial 50% → easy 75% → normal 100% → hard 160% → brutal 250% →
  deadly 400% → impossible 999%`, scaling 510 stat fields and 293 placement `+Level:` values,
  each inside its own field width; deterministic, never a dice roll.
- Ceiling: the *number* of placements cannot be raised without adding bytes to the archive
  (the archive-slack question). "Way more" therefore means re-pointing, not creating.

## Ring Hunt options

| Option | Default | What it does |
|---|---|---|
| **Endgame anchor** | blank (seeded random) | which event opens the Forge. `any-ring` = the seven rings with an anchor · `safe` = end-of-act milestones · blank = seed picks |
| **How many anchors** | 1 | how many events should unlock the ending |
| **Prefer end-of-act anchors** | on | restrict the pool to milestone flags |

The ending is gated by one flag, `ready_for_end`, which is exactly 13 characters — so any
other 13-character `+Event:` flag can be renamed to it in place. Four of them sit beside
ring pickups, covering **7 of 8 rings**:

| Anchor | Rings |
|---|---|
| `act3_finished` | Jade, Four Winds |
| `ikaemostopint` | Fire, Stone |
| `unhide_luvela` | Darkness, Forest |
| `unhide_tathal` | Fire, Water |

**Trade-off:** the chosen anchor stops setting its original flag, so anything checking that
flag no longer fires. End-of-act anchors are the default pool for that reason.

---

## Progression control — XP, level caps, permadeath

Three transforms move the *difficulty curve* rather than the content. Two are dials and one
is a switch.

| Transform | What it does | Size-safe how |
|---|---|---|
| `xp_scale` | scales every `+AddXP:` reward by a percentage | same-width digit scaling — a value only ever moves inside its own digit count |
| `levelcap_set` | scales every `+Levelcap:` by a percentage | same as above |
| `permadeath` | renames the revive ability and Revive Scroll items in place | 1:1 string swaps (`spell_revive`→`spell_none__`, `Revive Scroll`→`Inert Scrap  `) |

**`xp_scale` and `levelcap_set` are deterministic by design.** They are scaling operations,
not shuffles, so they ignore the seed — the same dials always produce the same bytes. That
is deliberate: difficulty pressure should not be a dice roll.

### Options

| Transform | Option | Default | Range | What it does |
|---|---|---|---|---|
| `xp_scale` | % of vanilla XP | 100 | 5–999 | 100 = vanilla, 300 = triple, 33 = a third. Clamped to the field width |
| `levelcap_set` | % of vanilla cap | 100 | 5–999 | how high creatures are allowed to level |
| `permadeath` | disable revive ability | on | yes/no | renames `$Action: "spell_revive"` |
| `permadeath` | neutralise Revive Scrolls | on | yes/no | renames `Revive Scroll` pickups |

Measured on the Summoner 1 corpus: `xp_scale` touches **248** `+AddXP` fields (172 move at
200%+); `levelcap_set` touches **26** `+Levelcap` fields; `permadeath` finds **6** revive
abilities and **11** Revive Scrolls — 17 edits, length unchanged.

### Modes built on them

- **Progression** — selects both dials, preset to 200% each. Dial XP and levelling in the
  Tune panel; the seed does not affect the result. Risk: low, pacing only.
- **Hardcore** — the full Roguelike stack (creature stats, spawns, loot, shops, chests,
  dialogue, audio, level caps, XP, prices, icons) **plus `permadeath`**. Death sticks.

**Permadeath caveat.** The engine looks actions and items up by name, so an unknown name may
be quietly ignored (intended) *or* may error (not intended). Same byte length, fully
reversible, untested in game — treat Hardcore as the boldest mode in the list.

---

## Transforms (41)

Edit counts are for one sample seed on the Summoner 1 corpus; shuffle counts move by a
handful seed to seed. The two dials (`xp_scale`, `levelcap_set`) read 0 at their neutral
100% and scale from there.

| Transform | Targets | Edits |
|---|---|---|
| `spawn_shuffle` | `$Start position` — relocates who stands where | 4,467 |
| `dialogue_blank` | `+NPCText` / `+Stage` — empties text | 5,687 |
| `dialogue_shuffle` | spoken text only, ids untouched | 4,910 |
| `npc_character_shuffle` | `$Character` values | 5,598 |
| `action_shuffle` | `+Action` — NPC behaviour ⚠ | 5,207 |
| `model_ref_shuffle` | `.mvf` refs | 2,381 |
| `animation_shuffle` | `$Animation`, `+Animation class` | 2,134 |
| `sound_shuffle` | every `.wav` ref | 1,706 |
| `creature_stats_shuffle` | speed, weight, HP, damage, protection, aggression, detection, turn rates | 1,284 |
| `enemies_none` | every monster placement unlinked from its navpoint (verified in game) | 4,067 |
| `enemies_amount` | the enemy-count dial — none / few / normal / many / all | 0–4,067 |
| `enemies_random` | which creature stands on each monster placement, `+Level:` | 1,697 |
| `enemies_swarm` | peaceful placements re-pointed at hostile creatures | 1,783 |
| `enemy_difficulty` | hostile stats + placement levels scaled | 803 |
| `music_shuffle` | `$Soundtrack`, `$Sound` | 1,108 |
| `economy_squeeze` | `$Value` prices up, `+AdjustGP` rewards down | 534 |
| `icon_shuffle` | `$Icon`, `.vbm` | 481 |
| `shop_shuffle` | `$Value` prices | 328 |
| `shops_free` | every `$Value` price → `0` | 477 |
| `shops_crazy` | every `$Value` price → all-9s at its own width | 479 |
| `shops_none` | shopkeeper placements re-pointed at non-shopkeepers | 86 |
| `xp_nerf` | `+AddXP` rewards cut to a third | 247 |
| `door_name_shuffle` | `$Door` names | 254 |
| `vfx_shuffle` | `.vfx` | 357 |
| `fade_instant` | `$Fade In/Out` durations | 184 |
| `xp_boost` | `+AddXP` rewards | 172 |
| `xp_scale` | `+AddXP` rewards — the XP dial (0 at 100%, 172 at 200%+) | 0–248 |
| `item_scatter` | `$Item` pickups | 150 |
| `camera_shuffle` | `$Camera`, `.csc` | 146 |
| `slot_shuffle` | `+Slot` / `$Slot` equipment | 105 |
| `door_sound_shuffle` | door `.wav` refs | 91 |
| `cutscene_bypass` | `$Cutscene` token | 84 |
| `cutscene_shuffle` | `$Cutscene` names | 76 |
| `lock_shuffle` | `+Locked` values | 73 |
| `fog_shuffle` | `$Fog` values | 58 |
| `material_shuffle` | `$Default Material` | 72 |
| `levelcap_raise` | `+Levelcap` values | 25 |
| `levelcap_set` | `+Levelcap` values — the level dial (0 at 100%, 26 at 200%) | 0–26 |
| `chest_shuffle` | `+Give` payouts | 22 |
| `permadeath` | `spell_revive` action + `Revive Scroll` items | 17 |
| `ring_hunt` | `+Event` flags | 1–4 |

### Deliberate omissions

**`+Topic:` ids are never shuffled.** They are reference keys — `+Add Topic:` and
`+Remove Topic:` point into the same namespace. Shuffling definitions without references
breaks the links and can strand a quest. Only spoken payloads are shuffled.

**`+Action:` is excluded from Everything.** It drives scripted sequences and can break
them, so it appears only in Behaviour Chaos and Total Chaos.

---

## Blocked, with reasons

| Idea | Blocked by |
|---|---|
| Skip the **startup movie** | not in the data layer — zero `.pss` refs; needs an ELF patch |
| Character models | `.mvf` format |
| Character colours (proper) | `.peg` palettes — though 337 `$Default Material` records do swap |
| Items in random chests, end to end | chest `+Give` doesn't set `got_ring_of_*`; **Ring of Jade has no grant record anywhere** |
| Faction flipping | `+Team:` values are 4/7/8 chars — not equal length, not swappable in place |
| Summoner 2, anything | VPP v2 reader not written |

**Cleared since the last update:** ~~Door destinations / real entrance shuffle — `.p3d` level
geometry~~. Doors are a text-layer `$Trigger:` name rewrite, proven applied and booting
(`DOOR-REMAP.md`). The remaining work is a `DATA_PATCHES` registry plus a reachability guard —
engineering, not a blocker.

---

## The constraint everything obeys

`TABLES.VPP` holds one continuous 6,771,975-byte text stream sliced into 527 chunks at
arbitrary offsets — 424 of 526 boundaries cut mid-line. The boundaries are meaningless to
the loader but must not move.

Every transform is therefore **length-neutral**: values are swapped only between equal-width
fields, and flags renamed only with same-length strings. Nothing is inserted or deleted.

Verified across all 41: **zero size violations.**
