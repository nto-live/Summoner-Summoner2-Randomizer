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

### 2.1 Door destination remap **inside the engine** *(the headline feature)*
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

### 2.2 `DATA_PATCHES` — a byte-range patch class in the engine
Required by 2.1: the current `binary.py` registry patches one 4-byte word at one virtual address.
A `TABLES.VPP` range is a different class of edit. Same two non-negotiables (declare-and-refuse,
read-back) plus bounds-checking against the archive region and a clean whole-image diff.

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

### 2.13 Adopted from other randomizers
Mined from OoTR, ALttPR/Archipelago, Enemizer, Super Metroid and Zelda 1 — full table in
`RESEARCH-RANDOMIZER-OPTIONS.md`. Worth building, in rough value order:

* **Hints over `+NPCText`** — a hint system is pure text-layer work, and this game has thousands of
  NPC lines to hide hints in. Nobody expects it from a Summoner randomizer.
* **Entrance "levels"** for the door remap — same-region → crossed → insanity, reusing the remap's
  own constraint list (how ALttPR and Zelda 1 present the same feature).
* **Spoiler log + seed sharing** — seeds are already byte-reproducible; this is packaging.
* **Shop inventory randomisation** — `+Shop` goods swapped between equal-length item names.
* **Enemy damage shuffle** — hostile `$Damage`/`$Protection`, folded into the stat shuffle.
* **Trap items** — re-point a `+Gain Item` at a junk item ("ice trap" in OoTR terms).

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
