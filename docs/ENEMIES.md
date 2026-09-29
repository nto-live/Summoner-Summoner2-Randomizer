# Enemies — how the game spawns them, and what the randomizer does about it

*Written 2026-09-21. The feature was requested the same day: "I want to randomize enemies.
Remove them all. Spawn way more. Control the difficulty from easy easy to impossible."*

Everything here is **table-layer** work: no executable patching, no new bytes. Every value is
rewritten inside its own field width, so the 6,771,975-byte TABLES.VPP stream never shifts and
the 527-entry archive stays byte-identical in length. `--build` output is therefore the same
size as the source disc, always.

---

## 1. The two halves of the model

### 1.1 Placements — `#Objects` inside a level

An enemy standing in a level is a record like this:

```
$Name:				"Bone King#$npc038"      <- instance name; the # suffix names the navpoint
$Character:			"Bone King"              <- which creature definition to instantiate
+Monster                                     <- this placement is a hostile
$Start position:	"$npc038"                <- the navpoint it stands on
```

Measured on the retail disc:

| | |
|---|---|
| Monster placements (`+Monster`) | **2,220** |
| Peaceful placements (NPCs, shopkeepers, props) | **2,037** |
| Distinct monster names | **80** |
| Name lengths | 16 classes (4 to 20 characters) |
| Placements that also carry `+Level: N` | **293** |
| `$Position` navpoints in the corpus | 12,822 |

The record is a *placement*, not a definition: `$Name` and `$Start position` both reference the
same `$npcNNN` navpoint, and the navpoint itself is a separate record (`$Name: "$npc038"`,
`$Type: "level"`, `$Position: < x, y, z >`).

### 1.2 Definitions — `#Character Info`

```
#Character Info
$Character:			"Abbot Laurent"
$Size:				"medium"
$Team:				"friendly"        <- 50 friendly, 49 hostile, 1 Hostile, 1 evil
$Max Hit Points:	40
$Hit Points:		40
$Max ability Points:	100
$Ability Points:	100
$Aggressiveness:	50
$Teamwork:			100
$Conservation:		70
$Attack Radius:		1.0
$Field of view range:	4.0
$Detection range:	4.0
$Speedup rate:		3.0
$Slowdown rate:		3.0
$Slow turn rate:	6.5
$Fast turn rate:	11.0
$Moving turn rate:	3.0
```

**101 such blocks exist**, 51 of them hostile. `$Team` is the faction field the door/quest notes
call `+Team`; the values are free text of varying length (`friendly` 8, `hostile` 7, `evil` 4),
which is why re-teaming is done only to equal-length words.

**A third of the monsters have no text definition.** 38 of the 80 placed monster names —
including the most common ones (`Orenian Samurai`, `Orenian Soldier2`, `Onyx Golem`) — have no
`#Character Info` block. Their stat sheets live in the executable's `.data`, which is why the
difficulty dial cannot reach every creature yet. See §5.

---

## 2. What the transforms do

| Transform | Edits (retail disc) | What changes |
|---|---|---|
| `enemies_none` (`how="navpoint"`) | **4,067** | every monster placement is unlinked from its navpoint |
| `enemies_none` (`how="team"`) | **51** | hostile creature definitions re-teamed |
| `enemies_none` (`how="both"`) | **4,118** | both of the above |
| `enemies_random` | **1,688** | 1,451 creature swaps + 237 `+Level:` moves |
| `enemies_swarm` | **1,783** | peaceful placements re-pointed at hostile creatures |
| `enemy_difficulty` (any step) | **803** | 510 stat fields + 293 placement levels |

### `enemies_none` — "remove them all"

Two levers were designed; **one works, one is blocked.**

1. **navpoint** (default, **verified in game**). `$Start position: "$npc038"` → `"$zzz038"`, and
the same suffix in `$Name:`. Same width, and `$zzzNNN` exists nowhere, so the placement can never
bind to a position. 4,067 edits across the 2,220 placements. Catacombs lost 81% of its living
entities on a test disc (§4).
2. **team** (BLOCKED). `$Team: "hostile"` → `"neutral"` looked like the natural same-width swap,
but the resulting disc never loads a level at all - see §4. The transform refuses rather than
shipping it.

### `enemies_random` — "randomize enemies"

Swaps which creature stands on each monster placement, and its `+Level:`, using only
equal-length values (names have 16 length classes; levels group by digit width). The count of
enemies is unchanged; who they are, and how strong, is not.

### `enemies_swarm` — "spawn way more"

`$Character:` selects the definition, and the definition is what carries `$Team: "hostile"`, so
re-pointing a *peaceful* placement at a monster's name makes it a monster on the spot. 1,783 of
the 2,037 peaceful placements can be converted (234 have no hostile name of their length).

The honest cost: **the people go away.** Quest NPCs and shopkeepers converted this way stop
existing as NPCs, so quests that expect them cannot complete. It is an opt-in chaos-tier mode,
not a default.

The ceiling is real and worth stating: the placement *count* cannot be raised, because that
would need new bytes in the archive. "Way more" therefore means "every peaceful placement
becomes hostile", not "the game spawns more objects".

### `enemy_difficulty` — the dial

| Step | Percent | Effect |
|---|---|---|
| `trivial` | 50% | half hit points, half aggression, half sight |
| `easy` | 75% | |
| `normal` | 100% | vanilla (no edits) |
| `hard` | 160% | |
| `brutal` | 250% | |
| `deadly` | 400% | |
| `impossible` | 999% | every value pinned to the largest that fits its field |

Scaled fields: `$Max Hit Points`, `$Hit Points`, `$Max ability Points`, `$Ability Points`,
`$Aggressiveness`, `$Attack Radius`, `$Field of view range`, `$Detection range`,
`$Speedup rate`, `$Slowdown rate` — and every placement's `+Level:`. A `level_shift` option adds
a flat number of creature levels instead of scaling.

The dial is **deterministic**: same step, same output, every seed. Difficulty should not be a
dice roll.

---

## 3. Modes shipped

| Mode | Transforms | Risk |
|---|---|---|
| **No Enemies** | `enemies_none` | medium — the disarm is not yet verified in game |
| **Oops, All Enemies** | `enemies_amount` (all), `enemies_random` | high — quest NPCs are consumed |
| **Enemy Swarm** | `enemies_swarm`, `enemies_random` | high — quest NPCs are consumed |
| **Impossible Enemies** | `enemy_difficulty` (999%) | high — untested, possibly unwinnable by design |
| **Easy Enemies** | `enemy_difficulty` (50%) | low |

Options: `enemy_difficulty.level` (the dial), `enemy_difficulty.level_shift` (flat levels),
`enemies_none.how` (navpoint / team / both), `enemies_amount.amount` (none / few / normal /
many / all — one dial over the enemy count, measured 4,067 / 2,852 / 0 / 872 / 1,783 edits;
`none` reproduces the verified `enemies_none` byte for byte).

---

## 4. Verification status

| Claim | How it was checked |
|---|---|
| every edit is size-preserving | `enemy_smoke.py` on the extracted stream: 9 transform/option combinations, all `len(out) == len(blob)` |
| the engine exposes them | `cli.py --list` shows the 4 transforms, 4 modes and the options; the WinForms app reads that list at startup, so they appear in the UI (rendered and confirmed) |
| a real ISO builds | `cli.py --build … --mode peaceful` → `Summoner-noenemies-ENEMY1.iso`, `size_preserved: true`, 4,067 edits, source sha unchanged |
| **enemies actually disappear** | **verified in game 2026-09-21 - see below** |
| more enemies appear | not verified in game yet |
| the difficulty dial bites | not verified in game yet |

### The in-game test, and its result

Method: two discs built from the same source, differing **only** in the enemy transform. Both are
steered to the same level by the door harness (masad's door rewritten to `catacombs`; the test
pnach opens the crossing gates so the game walks itself through). A live RAM walk of
`Living_entity_list` (`0x003AE0C8`, next pointer at `+0x31C`, sentinel is the head) samples the
entity count while the game plays — `F:\rando\S1\notes\entity_scan.py`.

| Level | vanilla | `enemies_none` (navpoint) | change |
|---|---|---|---|
| catacombs | **96** entities | **18** | **-81%** |
| masad | 58 | 38 | -34% |
| ionaext | 67 | 66 | unchanged |
| worldmap1 | 1 | 66 | (see the caveat) |

**What that settles:** the navpoint lever works. Unlinking `$npcNNN` really does stop
navpoint-placed monsters from spawning - catacombs lost four fifths of its living entities.

**What it does not settle:**

1. **A level is not emptied.** 18 entities remain in catacombs, and `ionaext` lost nothing at
   all. Those are creatures the game creates from code or from script rather than from a
   `#Objects` record - the same subset whose stat sheets are not in the text layer (§1.2).
2. **`worldmap1` went the other way** (1 → 66). The world map is not a normal level; the sample
   was taken at a different point of the run and the comparison there is not meaningful.
3. Entity counts include non-combat entities. This measures *spawns*, not *hostility* - a
   finer test needs the creature definition each entity points at.

### The team lever is BLOCKED

`how="team"` rewrote `$Team: "hostile"` → `"neutral"` and `"evil"` → `"good"` (51 definitions,
same widths). The built disc **never loaded a level at all**: `Level_data.name` stayed empty for a
whole 110-second run, three boots in a row. Those strings are evidently not valid team
identifiers, and an invalid one takes the level load down with it. The transform now **refuses**
with that reason instead of shipping it, and `how="both"` does the navpoint lever only.

### Combined with the door remap, against a control — 2026-09-21

The piece that matters for a real build: **no enemies *and* 218 remapped door destinations in one
disc**, checked against a control that differs only in the enemy pass.

| Check | Result |
|---|---|
| boots, boot ELF executes | PASS (`EntryPoint = 0x00100008 is executing`) |
| reaches gameplay unattended | PASS — first level ~55 s after launch |
| the remapped door fires | PASS — `masad`'s door loads **`lenele1e`** (vanilla: `worldmap1`), then the chain continues: `sewer` → `lenele3d` → `lenele2d` → `Liangshan` → … |
| nothing altered outside the archive | PASS — 13,880 bytes differ in 1.23 GB, **0 outside** the 7,395,328-byte `TABLES.VPP` region |

Living-entity maxima, same route, two discs (`test-doors.iso` = doors remapped, enemies present):

| level | no enemies | control | delta |
|---|---|---|---|
| masad | 38 | 58 | −20 |
| lenele1e | 38 | 58 | −20 |
| sewer | 12 | 65 | −53 |
| lenele3d | 5 | 15 | −10 |
| lenele2d | 11 | 12 | −1 |
| Liangshan | 17 | 100 | −83 |

Every level is lower with the monsters disarmed, and the control reproduces the vanilla `masad`
reference (58) exactly. Towns only drop a third — those 38 are townsfolk and party, not monsters,
which is also why the towns are where the metric is weakest.

**Still not proven:** the route only reached six levels, so ~212 of the 218 remapped doors remain
unexercised in game; entity counts are a *proxy* for "enemies gone" (the harness does not read
creature type); and the run needs the test pnach to force door crossings, so it is a harness route
rather than normal play.

## 5. Open items

1. **In-game verification of all three** — boot a built ISO headlessly (PINE rig: `watch_state.py`,
   `probe_live.py`, entity-list counts) and count what actually spawns.
2. **The 38 code-defined monsters** — their stat sheets are in the executable's `.data`. The
   difficulty dial is blind to them until that table is mapped (PROJECT.md §6 item 7).
3. **Adding placements** — genuinely more spawn points, rather than re-pointed ones, needs the
   archive-slack question answered (PROJECT.md §6 item 14).
4. **`+Level:` coverage** — only 293 of 2,220 placements carry a level; the rest take the level
   from somewhere not yet identified.
