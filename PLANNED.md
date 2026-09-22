# PLANNED.md — the to-be-implemented log

Everything that is *decided and not yet built*, in one place, so nothing lives only in a chat
message. Companion to `FEATURES.md` (what exists, measured) and `MODES.md` (how the modes read to
a player).

**State legend**

| State | Means |
|---|---|
| **NEXT** | at the top of the queue; no unknowns left |
| **QUEUED** | decided, mechanism identified, not started |
| **BLOCKED** | cannot be built yet — the reason and what it waits on are written here |
| **DONE** | built; the entry moves to `FEATURES.md` and the row is struck here |

**Acceptance for every item, without exception:** the transform is size-preserving (checked by
`inventory.py`), it is registered in the engine (visible in `cli.py --list`), its measured edit
count is recorded in `FEATURES.md`, the ops side is written down, and — where it can be — it is
verified in game by the headless rig. Anything that cannot be verified in game says so.

---

## 1. NEXT — in order

### 1.1 `enemies_amount` — one dial for how many enemies — **DONE**
**Requested as:** "How many enemies?", "No enemies?", "Oops all enemies".
**Mechanism:** `none` = navpoint-unlink every monster placement (already proven in game);
`few` = unlink a seeded majority; `normal` = untouched; `many` = convert a seeded share of the
peaceful placements to monsters; `all` = convert every one of them.
**Why one transform:** three requested options are the same lever at different values, and three
transforms would drift apart.
**Acceptance:** five option values produce five distinguishable edit counts; `none` matches the
shipped `enemies_none` behaviour exactly (4,067 edits on the retail disc).
**Built 2026-09-21 — measured on the retail stream, all five size-preserving:** `none` **4,067
edits / 12,201 bytes** (byte-identical output to the verified `enemies_none(how="navpoint")`),
`few` **2,852 / 8,556** (a seeded ~70%, 1,554 of 2,220 placements), `normal` **0 / 0** (vanilla by
design, reported), `many` **872 / 11,314** (1,018 of 2,037 targeted, 134 skipped), `all` **1,783 /
23,280** (every convertible placement; 234 skipped — no hostile name of that length). An unknown
value is refused with nothing changed. Shipped as transform `enemies_amount` (option `amount`) and
mode `oops_all_enemies` (`all` + `enemies_random`). See `FEATURES.md` §2.

### 1.2 `shops_free`, `shops_crazy`, `shops_none` — the shop levers — **DONE**
**Requested as:** "Make it all free", "Make it all crazy numbers", "No Shops".
**Mechanism:** rewrite every `$Value` price to `0`; rewrite it to the largest value its field
holds (`999`, `9999`…); and for "no shops" re-point the placements of shopkeepers — characters
whose definition carries `+Shop` — at equal-length non-shopkeepers, so the shop is simply absent.
**Queued before:** gather the shopkeeper list (which `$Character` definitions carry `+Shop`).
**Acceptance:** prices are all zero / all maximal with the field width preserved; no `+Shop`
character is reachable in the world afterwards.
**Built 2026-09-21 — measured on the retail stream, all three size-preserving:** `shops_free`
**477 edits / 530 bytes** (479 `$Value` prices → `0`, each padded to its own field width; 2 were
already 0), `shops_crazy` **479 / 1,728** (every `$Value` → all-9s at its own width, `999`…
`999999`), `shops_none` **86 / 1,132**.

**The `+Shop` marker lives on the dialogue definition, not `#Character Info` (found while
building):** in the retail stream the bare `+Shop` flag is a *topic* on the character's
dialogue block — keyed by `$Character: "Name"`, e.g. `$Character: "Shopkeeper#general"` →
`+Topic: {"Hail"}` → `+Shop` — and **0** `#Character Info` stat blocks carry it. So the
shopkeeper set is the 46 character names whose dialogue definition carries `+Shop`. A shop is
resolved by name (`level_script_get_shopkeeper_info(char *)`), and a placement reaches it through
its `$Name:` (which equals the definition key), so `shops_none` re-points each of the **86**
placements that name a shopkeeper at an equal-length non-shopkeeper placement name. Every length
class had candidates, so nothing was skipped; the definitions are never touched. Shipped as
transforms `shops_free`, `shops_crazy`, `shops_none` and modes `free_shops`,
`crazy_prices`, `no_shops`. See `FEATURES.md` §1.

### 1.3 `chest_items` — randomise what a chest *yields*
**Requested as:** "Chest Randomization" (the real version).
**Mechanism:** `chest_shuffle` today moves the payout *numbers*; this moves the **item names**
inside `+Give`, between equal-length names, so a cheap chest can hold something precious.
**Caveat carried from research:** chest `+Give` does not set the `got_ring_of_*` flags, and the
Ring of Jade has no grant record anywhere — so ring progression cannot be routed through chests.
**Acceptance:** item names change, counts preserved, no chest left empty.

### 1.4 `player_stats_random`, `enemy_stats_random` — the two stat items
**Requested as:** "Randomized enemy hp and stats", "Randomized player stats".
**Mechanism:** shuffle the numeric fields inside `#Character Info` blocks — hostile blocks for the
enemy side, `$Team: "friendly"` blocks for the playable party — between equal widths only.
`enemy_difficulty` already *scales* the hostile numbers; this *shuffles* them.
**Acceptance:** stats move between creatures, widths preserved, and no creature left with values
that cannot be expressed.

### 1.5 `rooms_shuffle` — randomised rooms, safe half
**Requested as:** "Randomized rooms".
**Mechanism:** permute what populates *within* a level: shuffle `$Start position` anchors between
placements of the same kind in the same level. Doors, quests, navpoints and the level graph never
change, so unreachable regions are impossible by construction — this is the safe half of the
design fork in `RESEARCH-ENTRANCE-LOGIC.md` §2.
**Not in scope here:** swapping a level's whole interior with another level's (designed, riskier).
**Acceptance:** anchors permute within a level and never across levels; every destination anchor
still exists.

---

## 2. QUEUED — decided, mechanism known

### 2.1 Door destination remap **inside the engine** *(the headline feature)* — **DONE**
Proven in game on 2026-09-21, but it lives in lab scripts (`make_door_test_iso.py`,
`apply_door_remap.py`); `cli.py` cannot remap a destination. Make it a seed-driven transform with
the constraints *enforced and refused*, never guessed:
target must be a real `Level_info` name; `len(new) <= len(old)`; `+Index:` must exist as a
`$player…` navpoint in the destination; a block with no `+Script:` may only target a level whose
base script name equals its own; `$zzz`-style sentinels are reserved.
Design: `DOOR-REMAP.md` §6.1 (the `DATA_PATCHES` sibling for `binary.py`/`rando_core.py`),
reference implementation `apply_door_remap.py`.
**Blocks:** the "Door Shuffle" mode currently overpromises — it shuffles names, locks and sounds.
**Acceptance:** a seeded remap reproduces the A/B that already passes for the lab script
(`DOOR-REMAP.md` §4.5).

**Built 2026-09-21** as the transform `door_destination_remap` and the mode `door_remap` (label
"Door Remap"). It finds the doors by *parsing* the stream — a `$Trigger: "<name>"` whose block's
`+Id:` is `"load level"` — not from a precomputed table, and **all 218 were found**, with the
discovered offsets agreeing exactly with `door-triggers.json`: all 218 ISO offsets, all 218
destinations and all 218 source-level attributions are identical to the fixture.

**Measured — seed `DOOR1`, retail disc, dry run and a real build:** 218 doors found, **200
destinations rewritten**, 18 landed on the name they already had, **0 skipped**, **1,568 bytes
changed**, image length identical (1,232,699,392 → 1,232,699,392), and a whole-image diff of
**0 bytes outside `TABLES.VPP`** — the first differing byte is `0x49641941`, the first door's own
name field. Every patch declared the bytes it expected, was read back, and the stream diff was
proven to contain nothing outside the declared fields. `how` policy option
(`shuffle` / `swap` / `off`) ships with a label and help text.

**Four of the five designed constraints are enforced and refused** — real `Level_info` name;
`len(new) <= len(old)`; never the door's own source level; never the `$zzz` sentinel — and a door
with no legal target is left alone and counted as a skip. The two softer ones added during
research (`+Index:` navpoint existence in the destination, and the `+Script:` rule) are **not**
enforced; that is the honest gap, and it is exactly what the parent's in-game A/B has to answer.

**`inventory.py` cannot see this.** Its fixture `F:\rando\S1\notes\_end_blob.bin` was built with
the pre-fix offset rule and contains 1 of the 218 doors, so it reports `1 edit / 10 bytes`.
Regenerating that fixture is a lab decision, not taken here; the disc numbers above are the ones
the feature actually produces, and `cli.py --build … --dry-run` reproduces them.

**Not needed after all:** the `DATA_PATCHES` registry of §2.2 — see there.

**Prerequisite bug this uncovered (fixed in the same commit):** the engine read every
`TABLES.VPP` entry from the wrong offset. The data area starts at the next `0x800` boundary after
the table of contents (`0x9000` for 527 records), not at a fixed `0x1000`, and entries are
`0x800`-aligned. The old rule truncated the archive's last ~620 KB — which is where all 52 level
files, and therefore all 218 doors and 59 `#Character Info` blocks, live. Blob length is
unchanged; nine other transforms' *disc* behaviour changes with it (their fixture numbers do not;
the list is in `FEATURES.md` §0).

### 2.2 `DATA_PATCHES` — a byte-range patch class in the engine — **DONE (not needed)**
**Resolved 2026-09-21.** No new patch class was required, and none was added. The engine already
returns a modified blob and writes each entry's slice back to its own ISO range
(`randomize_iso`), and once the archive-layout bug above was fixed the door streams are *inside*
that blob — so the doors are ordinary blob transforms like every other one, and the discipline
was carried inside the transform instead (declare-and-refuse on the bytes it expects, read every
patch back, bounds-check against the stream, and prove the whole-stream diff contains nothing
outside the declared fields). A `DATA_PATCHES` registry would have been invented machinery for a
problem that does not exist. `DOOR-REMAP.md` §6.1's `binary.py` sibling is therefore closed
unbuilt, deliberately.

### 2.3 Boss Rush
**Requested as:** "Boss Rush".
Bosses are placements carrying `+Boss`. v1 re-points every boss placement's `$Start position` at
navpoints inside a single arena level, so the bosses stand together and can be fought in one place.
**Needs first:** the boss inventory (blocks carrying `+Boss`) and the arena's navpoint list.
A *sequential* gauntlet — arena → arena chaining — rides on the level graph and is a later item.

### 2.4 Item Hunt — the "out of the shops, into the chests" half
`item_scatter` already moves loose pickups. This item moves goods out of shop stock and quest
rewards and into containers, so they have to be found rather than bought.

### 2.5 NPC Hunt — cross-level relocation
The mode built from `spawn_shuffle` + `npc_character_shuffle` ships first; relocating NPCs to
*other levels* is the stronger version and needs the placement/level cross-reference checked.

### 2.6 In-game level/room readout
Show `LEVEL · PLANE n` on the game's own screen and log it from inside the game's execution.
Known: the text draw is `FUN_00133608(x, y, char *s, ?, font)`; the room is the `+Plane:` id, and
the player's copy is at `entity+0x698`. Needs a code cave that survives startup (the ELF clears
BSS from `0x01285A80` to `0x01B42474`); `find_code_cave.py` locates one.
**Also useful for:** the honest door crossing, so a door can be watched rather than inferred.

### 2.7 Level-raise tool
**Requested as:** "something that raises the characters level" — automatically or inline.
*Inline:* per-session XP/level writing over PINE (`living_entity::adjust_experience` `0x001B9DE8`,
`experience_needed_for_level` `0x001A7BE8`, `Experience_table` `0x00384480`); the struct offset
still has to be read out of the function.
*Automatic:* `xp_scale`/`levelcap_set` already ship; a one-click preset is the small win.

### 2.8 The honest door crossing
The in-game door proof currently *forces* the two geometry gates (`crossing_test`,
`inside_mesh`) and nops the load-arm test. Satisfy the crossing for real: read
`FUN_0017e4d8` / `FUN_0017ee40` / `FUN_0017e548`, drive the player with PINE writes, then drop the
harness patches and re-run the A/B.

### 2.9 In-game checks for Swarm and the Difficulty dial
`enemies_none` is verified against a control; `enemies_swarm` and `enemy_difficulty` change bytes
but nobody has watched a fight.

### 2.10 `--patch-only` output
Emit a small patch file instead of a 1.2 GB ISO: seeds become tiny and shareable *without*
distributing game data, and the ~80 s build drops to seconds. Precedent: SotN's PPF, PNACH
(`RESEARCH-SOTN.md`, `RESEARCH-ENTRANCE-LOGIC.md` §9.1).

### 2.11 Seed sharing
Seed URLs / seed cards, SotN style. Seeds are already reproducible; this is the packaging.

---

### 2.12 `music_replace` — put *other* music in
**Requested as:** "can we replace the music with other music?"
**What the music is (measured 2026-09-21):** `MUSIC.VPP`, 131 tracks named in plaintext
(`catacombs.vmu`, `credits.vmu`, …), 428,976,128 bytes, `.vmu` = a Volition container decoded by
the game's own `vmusic` engine (`vmusic::open` `0x0015ACB0`, `process_block_read` `0x0015B010`).
TOC records are 64 bytes from `0x800` and carry a **size but no offset**; data starts at **0x3000**
(derived: archive − sum of sizes rounded to 2048 = 12,288) and **every entry is 2048-aligned**.
**Why that is good news:** a replacement that is the same length or shorter needs **no offset
fixups** — write it into the slot, zero-pad the alignment, and the archive, the ISO size and every
other entry are untouched. Longer tracks shift everything after them and need a full rebuild,
which is a different (and more carefully tested) path.
**The blocking task:** `.vmu` is a custom codec — no `VAGp`/`RIFF`/`OggS` magic anywhere. Decode
`vmusic` in the Ghidra project to get the block structure and sample format, then write an encoder
or transcoder. Bounded, and the only thing standing in the way.
**Legal line, drawn now:** the randomizer ships no music, ever — only the user's own audio or
generated/CC0 material they supply. `music_shuffle` (which track plays where) already ships and
involves no new media.
Full findings: `RESEARCH-RANDOMIZER-OPTIONS.md` §8.

### 2.13 Adopted from other randomizers — the full list
Mined from OoTR, ALttPR/Archipelago, Enemizer, Super Metroid and Zelda 1; the complete table with
sources is `RESEARCH-RANDOMIZER-OPTIONS.md`. Everything below is *not yet built*; the ones this
project already ships are listed as **exists** in that document and are not repeated here.

**Items and locations**
* `chest_items` — which item a container yields, equal-length names (§1.3, NEXT). **build now**
* Trap items — re-point a `+Gain Item` at a junk item (OoTR's "ice trap"). **designed**
* Starting inventory — party/start setup is script-side, not a flagged table. **designed**
* Progressive items, item pool size, swordless/bombless starts — the item tables live in the
executable, not the text layer. **blocked**, and honestly so

**Keys, locks and doors**
* Door destination remap (§2.1, the headline). **QUEUED, first**
* Entrance "levels" — same-region → crossed → insanity, reusing the remap's own constraint list.
**designed**, and a natural fit
* One-way and trap doors — allowed only where the reachability guard passes. **designed**
* Keysanity — Summoner has no key items; doors are locked by a value, not by a carried key.
**blocked by the game's design**, worth saying out loud

**Enemies**
* `enemy_stats_random` (§1.4) — hostile stat numbers shuffled. **build now**
* Enemy damage/health shuffle — `$Damage`/`$Protection` inside the same shuffle. **build now**
* Boss shuffle (ALttPR `Basic → Singularity`) — same inventory as Boss Rush (§2.3), different use:
reshuffle which boss stands where instead of gathering them. **designed**
* Aggression/vision dials (stealth seeds) — already exposed via the difficulty dial. **exists**

**Shops and economy**
* Percentage price dial (`Shop Price Modifier`) — `shops_crazy`/`shops_free` exist; a percentage
sits between them. **build now**
* Shop inventory randomisation — `+Shop` goods swapped between equal-length item names. **designed**
* "Scams" — a merchant selling junk; same lever as above. **designed**
* Cheap-healer quality of life — prices again. **build now**

**Stats, difficulty and pacing**
* Player stat shuffle (§1.4). **build now**
* Damage multiplier as its own dial. **build now**
* Timed runs / countdown — engine already keeps the clock; plan in `TIMER-DESIGN.md`.
**designed**, deferred by the owner's request

**Hints, information and goals**
* **Hint system over `+NPCText`** — thousands of NPC lines to hide hints in; pure text-layer work.
**designed, and the most distinctive idea on this list**
* Goal selection — `ring_hunt` already changes the ending gate; a "kill N bosses" goal needs a
counter (same blocker as Collectionthon). **half exists**
* Spoiler log + seed sharing — seeds are already byte-reproducible; this is packaging. **build now**
* Death Link / multiworld — would need a networked harness. **out of scope by design** (this tool is
self-contained and offline)

**Chaos, cosmetic and audio**
* `music_replace` (§2.12) — **designed**, blocked on decoding `.vmu`
* Palette/colour swaps — `.peg` palettes, undecoded. **blocked**
* Model swaps — shuffling `.mvf` refs ships; *new* models are blocked on the format. **half exists**

---

## 3. BLOCKED — reason and what would unblock it

| Item | Blocked by |
|---|---|
| **Collectionthon** | the game has no collection counter. Two candidates: rename an unused `+Event:` flag to `ready_for_end` (cheap, checks one thing) or patch the executable to gate the ending on a counter (the binary layer exists; the counter does not) |
| Encounter-rate scaling | the `#Resistances` block layout is unmapped |
| Character colours | `.peg` texture format undecoded |
| Item relocation across the board | the blob's segmentation map (chunk names are unreliable) |
| Level order | the runtime level-id → name table |
| One Hour (true version) | a flag graph plus a reachability solver |
| Character models | `.mvf` format |
| Creatures the game spawns from code (~38 of 80 names) | their stat sheets are in the executable's `.data`, not the text layer |
| Any edit that grows the archive | the archive-slack question (≈619 KB unused; needs a boot test) |
| Summoner 2 (any of it) | the VPP v2 reader does not exist |

---

## 4. Closing an item

1. Implement as a size-preserving transform; refuse rather than guess.
2. `python inventory.py` — confirm the edit count and that the output length is identical.
3. Register it so `cli.py --list` shows it; wire options and any mode that uses it.
4. Move the row from this file into `FEATURES.md` with its measured numbers.
5. Verify in game if it can be; otherwise say plainly that it cannot.
6. Commit with the measurement in the message.
