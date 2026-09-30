# Feature register

**Generated** by `tools/gen-feature-register.py` from `src/cli.py --list` — do not hand-edit.
Every count below comes from the engine, so this file cannot silently disagree with the code.
The verification tiers themselves are defined in `TEST-PLAN.md`.

## Summary

| | count |
|---|---|
| Modes | 47 |
| Transforms | 57 |
| Option-bearing transforms | 22 |
| Binary (executable) patches | 4 |
| Blocked / pending, with a recorded reason | 6 |
| Transforms not reachable from any mode | 0 |

**State key.** `play-verified` — a human watched it work · `boot-verified` — reaches gameplay under the harness · `build-verified` — the engine applied it, size preserved, edits confined to declared fields · `blocked` — refuses to run, reason recorded.

> The tier column is the *worst* claim the mode is entitled to make. A mode built out of correct-but-unseen transforms is `build-verified` no matter how confident anyone is.

## 1. Modes

### `vanilla` — Vanilla

- **Tier:** `play-verified`
- **Risk:** none
- No changes. Baseline for comparing against - a reference, not a build target, because there is nothing to change. Use Vanilla · No Tutorials if you want a disc that still differs from retail by one lever.

### `vanilla_no_tutorial` — Vanilla · No Tutorials

- **Tier:** `boot-verified`
- **Risk:** low - no randomisation; the only change is the tutorial patch
- **Binary patches:** `skip_tutorial`
- Nothing randomised at all - the retail game, with only the opening tutorials turned off. The one-lever baseline: a clean comparison disc, and the honest way to play-test the tutorial patch on its own, with no randomisation confounded into the result.

### `doors` — Door Shuffle

- **Tier:** `play-verified`
- **Risk:** low
- **Transforms (3):** `lock_shuffle`, `door_name_shuffle`, `door_sound_shuffle`
- Door locks, names and sounds shuffled. Engine-referenced doors (the burning-village fire barrier) are pinned so the opening cannot soft-lock.

### `door_remap` — Door Remap

- **Tier:** `play-verified`
- **Risk:** high - changes the level graph; reachability is unchecked
- **Transforms (1):** `door_destination_remap`
- Where every door LEADS: all 218 door destinations are rewritten to other real levels, each name staying inside its own field so the archive cannot grow. This changes the level graph itself - doors can send you somewhere the game never intended, and nothing yet checks that the world stays completable.

### `chaos` — Chaos

- **Tier:** `play-verified`
- **Risk:** low
- **Transforms (5):** `npc_character_shuffle`, `model_ref_shuffle`, `cutscene_shuffle`, `material_shuffle`, `door_sound_shuffle`
- Everything cosmetic at once — characters, models, cutscene order, materials.

### `short` — Short Run

- **Tier:** `build-verified`
- **Risk:** medium — untested in game
- **Transforms (2):** `cutscene_bypass`, `xp_boost`
- Cutscenes bypassed and combat scaled so a playthrough is hours not days.

### `one_hour` — One Hour

- **Tier:** `build-verified`
- **Risk:** medium — untested in game
- **Transforms (3):** `cutscene_bypass`, `xp_boost`, `levelcap_raise`
- Aggressive pacing: no cutscenes, no grind, scaled creatures. Door logic still unrandomized pending .p3d.

### `peaceful` — No Enemies

- **Tier:** `play-verified`
- **Risk:** medium - the disarm mechanism is not yet verified in game
- **Transforms (1):** `enemies_none`
- Every monster spawn unlinked from its navpoint and hostile creature definitions re-teamed. Walk the world, fight nobody.

### `invasion` — Enemy Swarm

- **Tier:** `build-verified`
- **Risk:** high - quest NPCs are consumed; quests will not complete
- **Transforms (2):** `enemies_swarm`, `enemies_random`
- Peaceful placements become monsters and the monsters are reshuffled. The harshest thing the text layer can do without adding bytes.

### `impossible` — Impossible Enemies

- **Tier:** `build-verified`
- **Risk:** high - untested in game; may be unwinnable by design
- **Transforms (1):** `enemy_difficulty`
- **Options preset:** `enemy_difficulty.level=impossible`
- Hostile creatures pinned to the top of every stat field they own and to the highest level their +Level: field can hold.

### `easy_enemies` — Easy Enemies

- **Tier:** `build-verified`
- **Risk:** low
- **Transforms (1):** `enemy_difficulty`
- **Options preset:** `enemy_difficulty.level=easy`
- Hostile creatures cut to three quarters hit points, aggression and reach - plus whatever the difficulty dial is set to.

### `oops_all_enemies` — Oops, All Enemies

- **Tier:** `build-verified`
- **Risk:** high - quest NPCs and shopkeepers are consumed; quests will not complete
- **Transforms (2):** `enemies_amount`, `enemies_random`
- **Options preset:** `enemies_amount.amount=all`
- Every peaceful placement becomes a hostile creature of equal name length, and the existing monsters are reshuffled for good measure. The people who lived in the world are gone.

### `everything` — Everything

- **Tier:** `build-verified`
- **Risk:** medium — excludes +Action on purpose
- **Transforms (24):** `lock_shuffle`, `door_name_shuffle`, `door_sound_shuffle`, `npc_character_shuffle`, `model_ref_shuffle`, `cutscene_shuffle`, `material_shuffle`, `cutscene_bypass`, `xp_boost`, `levelcap_raise`, `item_scatter`, `shop_shuffle`, `chest_shuffle`, `dialogue_shuffle`, `sound_shuffle`, `music_shuffle`, `spawn_shuffle`, `animation_shuffle`, `icon_shuffle`, `vfx_shuffle`, `camera_shuffle`, `fog_shuffle`, `slot_shuffle`, `creature_stats_shuffle`
- All implemented transforms except NPC behaviour, pacing included.

### `ring_hunt` — Ring Hunt

- **Tier:** `build-verified`
- **Risk:** medium — changes progression, needs a boot test
- **Transforms (1):** `ring_hunt`
- The Forge of Urath opens at a chosen event instead of after all eight rings. Changes how the game ENDS, not how it looks.

### `ring_hunt_any` — Ring Hunt · Any Ring

- **Tier:** `build-verified`
- **Risk:** medium — changes progression, needs a boot test
- **Transforms (1):** `ring_hunt`
- **Options preset:** `ring_hunt.anchor=any-ring`
- The ending opens on ANY of the seven rings that have a nearby anchor, instead of all eight. Find one ring, finish the game.

### `ring_hunt_short` — Ring Hunt · Short

- **Tier:** `build-verified`
- **Risk:** medium — two untested levers stacked
- **Transforms (4):** `ring_hunt`, `cutscene_bypass`, `xp_boost`, `levelcap_raise`
- Ring Hunt plus no cutscenes and no grind. The intended one-sitting run.

### `progression` — Progression

- **Tier:** `build-verified`
- **Risk:** low — pacing dials only, nothing structural moved; untested in game
- **Transforms (2):** `xp_scale`, `levelcap_set`
- **Options preset:** `xp_scale.percent=200`, `levelcap_set.percent=200`
- Dial the two progression levers yourself: XP per kill and how high creatures are allowed to level. Deterministic by design, so a seed plays the same every time. Defaults double both.

### `item_scatter` — Item Scatter

- **Tier:** `build-verified`
- **Risk:** low — cosmetic placement, no lock risk
- **Transforms (1):** `item_scatter`
- Which item sits at which pickup point is shuffled, so loot is not where you remember it.

### `shop_shuffle` — Shop Shuffle

- **Tier:** `build-verified`
- **Risk:** low
- **Transforms (1):** `shop_shuffle`
- Every shop price is shuffled among equal widths. A 25-gold item can cost 600 and vice versa.

### `free_shops` — Free Shops

- **Tier:** `build-verified`
- **Risk:** low - prices only, no structure moved
- **Transforms (1):** `shops_free`
- Every shop price becomes 0, each inside its own field width. Take what you like.

### `crazy_prices` — Crazy Prices

- **Tier:** `build-verified`
- **Risk:** low - prices only, no structure moved
- **Transforms (1):** `shops_crazy`
- Every shop price becomes the largest number its own field can hold - 999, 9999, 999999 - so nothing is affordable.

### `no_shops` — No Shops

- **Tier:** `build-verified`
- **Risk:** medium - shopkeepers stop existing; quests that need one cannot complete
- **Transforms (1):** `shops_none`
- Every shopkeeper's placement is re-pointed at an equal-length non-shopkeeper, so no shop can be reached. The shop definitions themselves are left untouched.

### `chest_shuffle` — Chest Randomisation

- **Tier:** `build-verified`
- **Risk:** low
- **Transforms (2):** `chest_shuffle`, `chest_items`
- Container payouts shuffled AND the yield itself randomised, so a crate can hold something precious. Gold chests stay gold.

### `dialogue_chaos` — Dialogue Chaos

- **Tier:** `build-verified`
- **Risk:** low — text only, no reference keys moved
- **Transforms (1):** `dialogue_shuffle`
- NPCs say each other's lines. Topic ids untouched, so quests still link.

### `sound_chaos` — Sound Chaos

- **Tier:** `build-verified`
- **Risk:** low — audio only
- **Transforms (2):** `sound_shuffle`, `music_shuffle`
- Every sound effect and music cue is shuffled. The loudest, safest, funniest mode in the list.

### `rooms` — Random Rooms

- **Tier:** `build-verified`
- **Risk:** low — anchors permute inside one level only; graph and doors untouched
- **Transforms (1):** `rooms_shuffle`
- **Options preset:** `rooms_shuffle.how=shuffle`
- Randomised rooms, the safe half: within each level the placements swap their $Start position anchors, so a level is furnished differently while every anchor still exists in that level. Doors, quests, the level graph and the navpoint definitions never change, so nothing can become unreachable.

### `npc_hunt` — NPC Hunt

- **Tier:** `build-verified`
- **Risk:** medium — quest NPCs can be re-cast or relocated; quests may not complete
- **Transforms (2):** `spawn_shuffle`, `npc_character_shuffle`
- NPCs are neither where you left them nor who you expect: every placement's $Start position anchor moves within its level, and who stands there ($Character) is shuffled among equal lengths. The people of the world are relocated and re-cast. Cross-level NPC relocation is a designed extension, not shipped here - see PLANNED.md 2.5.

### `boss_rush` — Boss Rush

- **Tier:** `build-verified`
- **Risk:** medium — bosses change position within their level; untested in game
- **Transforms (1):** `boss_rush`
- **Options preset:** `boss_rush.arena=auto`
- The bosses stand together: every level's boss placements are gathered onto a single navpoint of that level, so a boss fights with the others instead of alone. The one-global-arena version is documented as blocked - a navpoint name resolves only inside the level that declares it (names repeat across up to 107 levels), so moving placements BETWEEN levels needs extra bytes.

### `item_hunt` — Item Hunt

- **Tier:** `build-verified`
- **Risk:** low — names trade slots at equal width; no totals moved
- **Transforms (2):** `item_scatter`, `item_hunt`
- **Options preset:** `item_hunt.sources=both`
- Goods have to be found, not bought: shop stock and quest-reward item names are exchanged into containers (equal width only), and the container's old yield takes the shelf/reward slot. Stacked with the loose-pickup scatter. Nothing is lost or invented - only where a thing is found changes.

### `monster_chaos` — Monster Chaos

- **Tier:** `build-verified`
- **Risk:** medium — changes combat balance, untested in game
- **Transforms (2):** `creature_stats_shuffle`, `spawn_shuffle`
- Creature stats and spawn points shuffled. Enemies stop being uniform and show up in unexpected places. The anti-grind mode.

### `enemy_stats` — Random Enemy Stats

- **Tier:** `build-verified`
- **Risk:** medium — combat balance moves; untested in game
- **Transforms (1):** `enemy_stats_random`
- **Options preset:** `enemy_stats_random.style=floor`
- Randomized enemy HP and stats: the hostile creatures' own numbers are shuffled among each other, so the mix changes without the average moving. Bosses stay top-tier (style=floor); enemy_difficulty scales, this shuffles.

### `glass_enemies` — One-HP Enemies

- **Tier:** `build-verified`
- **Risk:** medium — trivialises combat by design; untested in game
- **Transforms (1):** `enemy_stats_random`
- **Options preset:** `enemy_stats_random.hp=one`
- Every enemy is set to 1 hit point — everything hostile dies in a single hit. HP fields vary in width, so the 1 is padded into each field rather than changing its length; nothing else about a creature is touched.

### `player_stats` — Random Player Stats

- **Tier:** `build-verified`
- **Risk:** medium — party balance moves; untested in game
- **Transforms (1):** `player_stats_random`
- **Options preset:** `player_stats_random.style=floor`
- Randomized player stats: the playable party's HP, ability points, aggression, ranges and turn rates are shuffled among the party. Width tiers preserved so nobody is left unplayable (style=floor).

### `stat_chaos` — Stat Chaos

- **Tier:** `build-verified`
- **Risk:** medium — combat and party balance both move; untested in game
- **Transforms (2):** `enemy_stats_random`, `player_stats_random`
- **Options preset:** `enemy_stats_random.style=floor`, `player_stats_random.style=floor`
- Both stat shufflers at once: enemy numbers reshuffled among enemies, party numbers among the party. Each side stays internally coherent; the balance between and within sides is scrambled.

### `behaviour_chaos` — Behaviour Chaos

- **Tier:** `build-verified`
- **Risk:** high — +Action drives scripted sequences and can break them
- **Transforms (2):** `action_shuffle`, `animation_shuffle`
- NPC actions and animations shuffled. Characters do the wrong things, in the wrong way.

### `visual_chaos` — Visual Chaos

- **Tier:** `build-verified`
- **Risk:** low — presentation only
- **Transforms (4):** `icon_shuffle`, `vfx_shuffle`, `fog_shuffle`, `camera_shuffle`
- Item icons, spell effects, fog and cutscene cameras all shuffled. The game looks wrong on purpose.

### `total_chaos` — Total Chaos

- **Tier:** `build-verified`
- **Risk:** very high — includes +Action, which can break scripts
- **Transforms (26):** `lock_shuffle`, `door_name_shuffle`, `door_sound_shuffle`, `npc_character_shuffle`, `model_ref_shuffle`, `cutscene_shuffle`, `material_shuffle`, `cutscene_bypass`, `xp_boost`, `levelcap_raise`, `item_scatter`, `shop_shuffle`, `chest_shuffle`, `dialogue_shuffle`, `sound_shuffle`, `music_shuffle`, `spawn_shuffle`, `animation_shuffle`, `action_shuffle`, `icon_shuffle`, `vfx_shuffle`, `camera_shuffle`, `fog_shuffle`, `slot_shuffle`, `creature_stats_shuffle`, `fade_instant`
- Every single transform, behaviour included. Expect it to be broken; that is the point.

### `fast_start` — Fast Start

- **Tier:** `build-verified`
- **Risk:** medium — untested in game
- **Transforms (4):** `cutscene_bypass`, `dialogue_blank`, `fade_instant`, `xp_boost`
- Cut the opening down: cutscenes skipped, dialogue blanked, fades instant, combat scaled. Gets you into the game.

### `no_dialogue` — No Dialogue

- **Tier:** `build-verified`
- **Risk:** medium — untested in game
- **Transforms (2):** `dialogue_blank`, `cutscene_bypass`
- Every spoken line and quest objective blanked. Play the game, skip the reading.

### `roguelike` — Roguelike

- **Tier:** `build-verified`
- **Risk:** high — stacks eleven changes, untested in game
- **Transforms (12):** `creature_stats_shuffle`, `spawn_shuffle`, `item_scatter`, `shop_shuffle`, `chest_shuffle`, `dialogue_shuffle`, `sound_shuffle`, `music_shuffle`, `levelcap_raise`, `xp_nerf`, `economy_squeeze`, `icon_shuffle`
- High variance plus resource pressure: creatures, spawns, loot, shops and chests all scrambled, XP cut so you cannot out-level the content, and prices driven up. Every seed plays as a run.

### `roguelike_short` — Roguelike · Short

- **Tier:** `build-verified`
- **Risk:** high
- **Transforms (12):** `creature_stats_shuffle`, `spawn_shuffle`, `item_scatter`, `shop_shuffle`, `chest_shuffle`, `sound_shuffle`, `levelcap_raise`, `xp_nerf`, `economy_squeeze`, `cutscene_bypass`, `dialogue_blank`, `fade_instant`
- Roguelike pressure with the length taken out: no cutscenes, instant fades, blanked dialogue. A single-sitting run.

### `hardcore` — Hardcore

- **Tier:** `build-verified`
- **Risk:** very high — permadeath is untested; a bad action/item name may error
- **Transforms (13):** `creature_stats_shuffle`, `spawn_shuffle`, `item_scatter`, `shop_shuffle`, `chest_shuffle`, `dialogue_shuffle`, `sound_shuffle`, `music_shuffle`, `levelcap_raise`, `xp_nerf`, `economy_squeeze`, `icon_shuffle`, `permadeath`
- The Roguelike stack plus permadeath: creatures, spawns, loot, shops and chests scrambled, XP cut, prices driven up — and the revive ability and Revive Scrolls removed so death sticks.

### `endgame_gate` — Endgame Gate (binary)

- **Tier:** `boot-verified`
- **Risk:** medium — changes progression, needs a boot test
- **Binary patches:** `endgame_gate`
- Patches the executable itself: lowers the gamestage threshold that arms the ending, so the Forge becomes available much earlier. One instruction, verified by re-reading it after writing.

### `skip_intro` — Skip Intro Movie (binary)

- **Tier:** `play-verified`
- **Risk:** low - presentation only; play-verified (boot logos gone)
- **Binary patches:** `skip_intro`
- Stops the boot/intro video from playing: it makes the movie-player routine return immediately, which neutralises every boot-movie call at once. The intro is not in the script layer (zero .pss refs), so this is an executable patch. Play-verified - the THQ logo is gone. NOTE: this removes the .pss FMV logos; the in-engine story cinematic is a separate $Cutscene and is NOT removed by this patch (neutering it hangs the boot).

### `power_trip` — Power Trip

- **Tier:** `build-verified`
- **Risk:** high - trivialises combat by design; untested in game
- **Transforms (6):** `enemy_hp_set`, `enemy_damage_set`, `weapon_attack_max`, `armor_protect_max`, `enemy_xp_set`, `enemy_drops_always`
- **Options preset:** `enemy_hp_set.value=1`, `enemy_damage_set.value=0`, `enemy_xp_set.value=9999`
- You are the boss fight. Every enemy dies in one hit and barely scratches you, your weapons and armour are pinned to the top of their fields, every kill pays maximum XP, and anything that can drop an item does. Nothing is randomised - this is a straight power fantasy, for blasting through the story or checking a later area early.

### `random_rewards` — Random Rewards

- **Tier:** `build-verified`
- **Risk:** low - rewards move between enemies; no totals changed
- **Transforms (2):** `enemy_xp_random`, `enemy_drops_random`
- Kills stop being predictable: how much XP a creature is worth and which item it drops are both shuffled between creatures. A trash mob can pay a boss's XP. Shuffling, not inflating - the average is unmoved, only who pays what changes.

### `music_only` — Music Only

- **Tier:** `build-verified`
- **Risk:** low - music only, no sound effects, no progression risk
- **Transforms (1):** `music_tracks_shuffle`
- The background music is shuffled and nothing else is touched - the wrong track plays in the wrong place, but every sound effect stays correct. The gentlest mode in the list; useful on its own or stacked onto another.

## 2. Transforms

| transform | what it does | options | used by |
|---|---|---|---|
| `action_shuffle` | Shuffles +Action verbs — the AI and script instructions. Characters do the wrong things. Actions drive scripted sequences, so this CAN break them. | — | 2 (behaviour_chaos, total_chaos) |
| `animation_shuffle` | Shuffles $Animation and +Animation class, so characters perform the wrong movements. | — | 3 (everything...) |
| `armor_protect_max` | Sets every armour item's $Protection to one high value (default 999, clamped into each field's own width). Scoped to $Armor: record spans, so creature protection is never touched. Size-preserving. ... | `value` | 1 (power_trip) |
| `boss_rush` | Gathers a level's `+Boss` placements onto a single navpoint of that same level (same width only), so the bosses stand together and are fought in one place. Not a single global arena: a navpoint nam... | `arena` | 1 (boss_rush) |
| `camera_shuffle` | Shuffles $Camera and .csc, so cutscenes are shot from the wrong angles. | — | 3 (everything...) |
| `chest_items` | Shuffles WHAT a container yields — the +Messagebox: name in a block that also carries +Give: — between equal-length names, so a cheap crate can hold something precious. The amount is not touched. | `how` | 1 (chest_shuffle) |
| `chest_shuffle` | Shuffles +Give payouts among equal widths. Most single digits are item counts, so only the multi-digit gold payouts really move. | — | 6 (everything...) |
| `creature_stats_shuffle` | Shuffles the creature stat block — speed, weight, hit points, damage, protection, aggression, detection range, turn rates. This is the anti-grind lever: enemies stop being uniform. | — | 6 (everything...) |
| `cutscene_bypass` | Breaks the $Cutscene token in place ($Cutscene -> $Xutscene). Single-byte revert, the biggest wall-clock saving available. | — | 8 (short...) |
| `cutscene_shuffle` | Shuffles $Cutscene names among equal lengths. | — | 3 (chaos...) |
| `dialogue_blank` | Empties every spoken line and quest objective, keeping the exact byte length and line structure. Removes 2.6 million characters of reading. The boxes still need advancing — this removes the reading... | — | 3 (fast_start...) |
| `dialogue_shuffle` | Shuffles spoken text so NPCs say each other's lines. Topic ids are left alone on purpose — they are reference keys and shuffling them breaks quests. | — | 5 (everything...) |
| `door_destination_remap` | Rewrites the destination name inside every door's `$Trigger:` record, so doors lead somewhere else. Finds the doors by parsing the level tables, rewrites only names that fit the field, refuses anyt... | `how`, `require_script` | 1 (door_remap) |
| `door_name_shuffle` | Shuffles $Door names among equal widths. | — | 3 (doors...) |
| `door_sound_shuffle` | Shuffles open/close .wav references across doors — you hear the wrong door. | — | 4 (doors...) |
| `economy_squeeze` | Drives shop prices up and gold rewards down within their own field widths. Shops stop being a safety net; you live off what you find. | — | 3 (roguelike...) |
| `enemies_amount` | One dial over the enemy count: none (unlink every monster placement from its navpoint), few (a seeded ~70%), normal (vanilla, no edits), many (a seeded ~50% of the peaceful placements become monste... | `amount` | 1 (oops_all_enemies) |
| `enemies_none` | Unlinks every monster placement (2,220 of them) from the navpoint it spawns on, and optionally re-teams the hostile creature definitions. Nothing added, nothing moved. | `how` | 1 (peaceful) |
| `enemies_random` | Swaps which creature stands on each monster placement, and its +Level:, between equal-length values only. | `scope` | 2 (invasion, oops_all_enemies) |
| `enemies_swarm` | Re-points peaceful placements (NPCs, props, shopkeepers) at hostile creatures. Far more enemies to fight, at the cost of the people who lived there. | — | 1 (invasion) |
| `enemy_damage_set` | Sets every hostile creature's $Damage to one value you choose (default 0 = they barely hurt you). Summoner enemies have no defence stat, so lowering their damage is the way to make them softer. Wea... | `value` | 1 (power_trip) |
| `enemy_difficulty` | The dial: scales hostile creature stats and placement levels from trivial through easy / normal / hard / brutal / deadly to impossible, inside each field's own width. | `level`, `level_shift` | 2 (impossible, easy_enemies) |
| `enemy_drops_always` | Maxes every enemy +Drop chance (to 100 where the field allows), so any enemy that can drop an item almost always does. Cannot add a drop to an enemy that has none (that needs extra bytes). Size-pre... | — | 1 (power_trip) |
| `enemy_drops_random` | Shuffles which item each enemy `+Drop:` yields, among equal-length item names. The drop-chance weight is left alone, so rates are unchanged - only WHAT drops moves. Nothing is invented or lost. Siz... | — | 1 (random_rewards) |
| `enemy_hp_set` | Sets every hostile creature's $Max Hit Points and $Hit Points to one value you choose, padded into each field's own width (all-9s clamp if it will not fit). HP only - attack, damage and level are l... | `value` | 1 (power_trip) |
| `enemy_stats_random` | Shuffles the hostile creatures' own numbers — hit points, ability points, aggression, attack radius, view/detection range, movement rates — among each other. enemy_difficulty scales these; this mov... | `style`, `hp` | 3 (enemy_stats...) |
| `enemy_xp_random` | Shuffles $Experience Gained among hostile creatures, so how much XP a mob is worth on death is scrambled - a trash mob may pay a boss's XP and vice-versa. Separate from the global XP multipliers an... | `style` | 1 (random_rewards) |
| `enemy_xp_set` | Sets every hostile creature's $Experience Gained to one value you choose, clamped per field to the largest number that fits its width. Set it high to level up fast. Separate from the global XP mult... | `value` | 1 (power_trip) |
| `fade_instant` | Zeroes every scene fade duration, so the pauses between scenes, cutscenes and level loads disappear. Presentation only. | — | 3 (total_chaos...) |
| `fog_shuffle` | Shuffles $Fog values so each level's atmosphere and draw distance changes. | — | 3 (everything...) |
| `icon_shuffle` | Shuffles $Icon and .vbm refs, so items and gear display the wrong art. | — | 5 (everything...) |
| `item_hunt` | Moves goods out of the shop stock (+Buy List: / +Sell List:) and the quest rewards (+Gain Item:) and into the containers: each good is exchanged, equal width only, with a container yield, and that ... | `sources` | 1 (item_hunt) |
| `item_scatter` | Shuffles which item sits at which loose pickup point. | — | 7 (everything...) |
| `levelcap_raise` | Pushes +Levelcap: values up, same field width, so creatures scale with you. In-game effect unverified. | — | 7 (one_hour...) |
| `levelcap_set` | Scales every +Levelcap: by a percentage you choose — how high creatures are allowed to grow. 100 = vanilla, 200 = twice as high. | `percent` | 1 (progression) |
| `lock_shuffle` | Shuffles the +Locked: values across every door, so a door's lock no longer matches what is behind it. | — | 3 (doors...) |
| `material_shuffle` | Shuffles $Material / $Mat names — colour swaps wherever those records exist. | — | 3 (chaos...) |
| `model_ref_shuffle` | .mvf model references reshuffled among equal lengths. | — | 3 (chaos...) |
| `music_shuffle` | Shuffles $Soundtrack / $Sound — the wrong track plays in the wrong place. | — | 5 (everything...) |
| `music_tracks_shuffle` | Shuffles the background music tracks ($Soundtrack) among equal-length names, so the wrong track plays in the wrong place - but sound effects are left alone. Use music_shuffle instead if you want SF... | — | 1 (music_only) |
| `npc_character_shuffle` | Shuffles $Character values — who stands where changes. | — | 4 (chaos...) |
| `permadeath` | Disables the revive ability and neutralises Revive Scroll pickups so death sticks. Both are table-defined. Risky: an unknown name may error. | `block_ability`, `block_items` | 1 (hardcore) |
| `player_stats_random` | Shuffles the playable party's numbers among themselves — HP, ability points, aggression, ranges and turn rates (this game has no Str/Dex/Int). style=floor keeps each value in its own width tier; st... | `style` | 2 (player_stats, stat_chaos) |
| `ring_hunt` | Opens the Forge of Urath at a chosen event instead of after all eight rings. The game has no ring counter — the ending is gated by the single flag ready_for_end, which is 13 characters, so any 13-c... | `anchor`, `count`, `safe_only` | 3 (ring_hunt...) |
| `rooms_shuffle` | Randomised rooms, the safe half: permutes $Start position anchors between placements INSIDE one level (same kind, same width), so a level is furnished differently while every anchor still exists in... | `how` | 1 (rooms) |
| `shop_shuffle` | Shuffles $Value prices among equal widths. | — | 6 (everything...) |
| `shops_crazy` | Every $Value price becomes the largest value its own field can hold (all 9s). | — | 1 (crazy_prices) |
| `shops_free` | Every $Value price becomes 0, padded to its own field width. Everything is free. | — | 1 (free_shops) |
| `shops_none` | Re-points the placements that name a +Shop character at equal-length non-shopkeeper names, so the shopkeeper is never reached and the shop is absent from the world. The definitions themselves are n... | — | 1 (no_shops) |
| `slot_shuffle` | Shuffles +Slot / $Slot, so gear lands in the wrong equipment slot. | — | 2 (everything, total_chaos) |
| `sound_shuffle` | Shuffles every .wav reference, so the wrong noise plays everywhere. Very audible, no progression risk. | — | 6 (everything...) |
| `spawn_shuffle` | Shuffles $Start position anchors, so NPCs and creatures appear at other points in the level. Relocates who stands where. | — | 7 (everything...) |
| `vfx_shuffle` | Shuffles .vfx references — the wrong visual effect fires for a spell. | — | 3 (everything...) |
| `weapon_attack_max` | Sets every weapon's $Damage to one high value (default 999, clamped into each field's own width). Scoped to weapon records by the adjacent $Damage Type marker, so creature damage is never touched. ... | `value` | 1 (power_trip) |
| `xp_boost` | Scales every +AddXP: reward up inside its own digit width. Kills the grind. In-game effect unverified. | — | 6 (short...) |
| `xp_nerf` | Scales every +AddXP: reward DOWN, so you cannot out-level the content. Roguelike pressure — encounters stay dangerous the whole run. | — | 3 (roguelike...) |
| `xp_scale` | Scales every +AddXP: reward by a percentage you choose. 100 = vanilla, 300 = triple, 33 = a third. Deterministic, so difficulty is not a dice roll. | `percent` | 1 (progression) |

## 3. Binary patches (they edit the executable, not the data layer)

| patch | address | expects | state |
|---|---|---|---|
| `endgame_gate` | `0x00212274` | `0x28420015` | verified byte-for-byte, not watched in game |
| `skip_intro` | `0x002419C0` | `0x27BDFEF0` | play-verified |
| `skip_tutorial` | `0x0023D74C` | `0x12000004` | verified byte-for-byte, not watched in game |
| `hide_tutorials` | `0x0023D824` | `0x0C08AC56` | **BLOCKED** — wrong lever: hides the popup but leaves the input-gate, freezing the opening. Use skip_tutorial (NOPs the gate instead). See docs/lab/ANALYSIS-why-v3-works.md. |

Every patch declares the bytes it expects and refuses on mismatch — that rule is not optional.

## 4. Blocked and pending — with the reason and what would unblock it

These are the honest gaps. Each carries a `blocked_by`, so no one has to re-derive why.

| item | blocked by | reason |
|---|---|---|
| `anti_grind_encounters` | #Resistances block layout | Encounter rate and creature stats live in the Rand-* overworld scripts and the 59 #Resistances stat blocks. These are addressable but the record layout inside those blocks is not yet mapped, so scaling them is unsafe. |
| `character_colours` | .peg texture format | Only 17 $Material/$Mat records exist in the table layer, which is far too few for every character. The real colour data is palettes inside the .peg texture packs, which are not decoded. |
| `item_shuffle` | blob segmentation map | Item records exist but their location is unconfirmed: .tbl chunk names are arbitrary slices, so 'items.tbl' is not the item table. |
| `level_order` | ELF analysis / MAIN.MAP symbols | Needs the runtime numeric level-ID -> name table, which appears to live in SLUS_200.74. |
| `one_hour_mode` | flag graph solver | Needs the full flag graph plus a reachability solver so seeds can never be unbeatable. |
| `character_models` | .mvf format | CHARS.VPP holds 2,556 .mvf files; the format is undecoded. |

