# Research — options other randomizers ship, and what we could support

*Written 2026-09-21. Two questions from the owner: "find all the different options we could
support from other popular randomizers", and "can we replace the music with other music?"*

Method: read the public option inventories of the mature randomizers — **Ocarina of Time
Randomizer** (preset/settings list), **ALttPR** (settings and the Archipelago player-option
list), **Enemizer**, and the **Super Metroid / SMZ3 / Zelda 1 combo** randomizers — then map each
idea onto a lever Summoner actually has. Nothing here is copied code or content; it is a list of
*ideas*, and each row says what our equivalent would be and whether it is real.

Status vocabulary matches `FEATURES.md`: **exists** · **build now** · **designed** · **blocked**.

---

## 1. Items and locations

| Idea (where it comes from) | Summoner lever | Status |
|---|---|---|
| Shuffle item locations (everywhere) | `item_scatter` — 177 `$Item` pickups, equal-length swap | **exists** |
| Chest contents shuffle | `chest_shuffle` (payouts) + `chest_items` (the item itself) | **half exists**, `chest_items` **build now** |
| Progressive items (ALttPR `Progressive Items`) | items that upgrade in place; Summoner has no such table in text | **blocked** — item definitions live in the executable |
| Starting inventory (OoTR `Starting Inventory`) | `+Start position` / party setup is script-side, not a flagged table | **designed** |
| Swordless / bombless starts (ALttPR) | no equivalent requirement in Summoner's scripts to remove | **blocked** |
| Triforce-hunt style "collect N of X to win" | the ending is a single flag (`ready_for_end`) — see goals below | **blocked** for a true count |
| Trap items ("ice traps", "beemizer") | `+Gain Item` / `+Lose Item` lines could be re-pointed at a junk item | **designed** |

## 2. Keys, locks and doors

| Idea | Summoner lever | Status |
|---|---|---|
| Door **destination** shuffle (ALttPR entrance shuffle, OoTR interior entrances) | rewrite the `$Trigger:` destination name in the level's own object table | **proven in game**, **not yet in the engine** — `PLANNED.md` §2.1 |
| Door locks / keys | every door carries `+Locked: <float>`; values shuffle | **exists** (`lock_shuffle`) |
| Door sounds | `+Open sound` / `+Close sound` refs | **exists** (`door_sound_shuffle`) |
| Keysanity (keys anywhere) | Summoner has no key *items* — doors are locked by value, not by carried keys | **blocked** by the game's design, and worth saying so |
| Entrance "levels" (Simple → Insanity) | the door remap can be constrained: same-region only, any, or fully crossed | **designed** — a direct fit for the remap's constraint list |
| One-way / trap doors | a remap can point two doors at each other only if the reachability guard passes | **designed** |

## 3. Enemies

| Idea | Summoner lever | Status |
|---|---|---|
| Enemy type shuffle (Enemizer, ALttPR `Enemy Shuffle`) | `enemies_random` — swap creature names per placement | **exists** |
| Enemy count / density (OoTR-ish, "horde" seeds) | `enemies_amount` — none / few / normal / many / all | **exists** (today) |
| Enemy stat shuffle (Enemizer hit counts, ALttPR `Enemy Health`) | `enemy_stats_random` starts with the 51 hostile stat sheets; the *scaling* dial already ships | **build now** / partially exists |
| Enemy damage shuffle (ALttPR `Enemy Damage: Shuffled/Chaos`) | hostile `$Damage` / `$Protection` fields | **build now** (part of the stat shuffle) |
| Boss shuffle (ALttPR `Boss Shuffle: Basic → Singularity`) | bosses are `+Boss` placements; reshuffling which boss stands where, or gathering them in one arena | **designed** — Boss Rush is the same inventory (`PLANNED.md` §2.3) |
| Randomise *where* enemies stand | `spawn_shuffle` + `enemies_amount` combined | **exists** |
| Enemy aggression/vision (stealth seeds) | `$Aggressiveness`, `$Detection range`, `$Field of view range` | **exists** (via the difficulty dial) |

## 4. Shops and economy

| Idea | Summoner lever | Status |
|---|---|---|
| Randomise shop prices (ALttPR `Randomize Shop Prices`) | `shop_shuffle` | **exists** |
| Price modifier (`Shop Price Modifier: 100`) | `shops_crazy` (max) / `shops_free` (zero) / a future percentage dial | **exists** / **build now** (percentage) |
| Randomise shop inventories (ALttPR) | `+Shop` blocks list goods; item names are equal-length swappable | **designed** |
| Remove shops entirely | `shops_none` — shopkeepers re-pointed at non-shopkeepers | **exists** (today) |
| Universal/free healer, cheap potions (QoL) | prices are the lever | **build now** |
| "Scams" (ALttPR: a merchant sells junk) | same inventory lever as above | **designed** |

## 5. Stats, difficulty and pacing

| Idea | Summoner lever | Status |
|---|---|---|
| Difficulty presets (easy → hell) | `enemy_difficulty` dial, seven steps | **exists** |
| Damage multiplier (OoTR `Damage Multiplier`) | hostile `$Damage` per creature | **build now** (in the stat shuffle) |
| Timed runs / countdown (ALttPR `Timer`) | the engine already keeps a 64-bit clock; the plan is written in `TIMER-DESIGN.md` | **designed**, deferred by request |
| XP rate and level caps (pacing) | `xp_scale`, `levelcap_set`, `xp_boost`, `xp_nerf` | **exists** |
| Permadeath / no-revive (Hardcore) | `permadeath` — revive ability and scrolls renamed in place | **exists** |
| Player stat shuffle | `player_stats_random` over the friendly stat sheets | **build now** |
| Item pool size (OoTR `Item Pool`) | not a table we control — items are script grants | **blocked** |

## 6. Hints, information and goals

| Idea | Summoner lever | Status |
|---|---|---|
| Hints / gossip stones (OoTR `Hint Distribution`, ALttPR `Hints`) | `+NPCText` payloads are equal-length swappable — a hint system is a text-layer feature | **designed**, and unusually well suited to this game |
| Goal selection (defeat Ganon / triforce hunt / dungeons) | `ring_hunt` changes the ending gate; a "kill N bosses" goal needs a counter | **half exists** — `ring_hunt` + the boss flag inventory |
| Triforce-piece count | needs a collectible counter | **blocked** (same reason as Collectionthon) |
| Death Link / multiworld (Archipelago) | would need a networked harness; the randomizer is deliberately offline and self-contained | **out of scope** by design |
| Race mode / spoiler log | seeds are already reproducible byte-for-byte; a spoiler log is a small engine feature | **build now** |

## 7. Chaos, cosmetic and audio

| Idea | Summoner lever | Status |
|---|---|---|
| Text/dialogue shuffle (OoTR `Text Shuffle`) | `dialogue_shuffle`, `dialogue_blank` | **exists** |
| Sound effect shuffle (OoTR `Sound Effects`) | `sound_shuffle` | **exists** |
| Music shuffle / wrong track in the wrong place | `music_shuffle` (`$Soundtrack`, `$Sound`) | **exists** |
| **Replace music with other music** | see §8 — the container is friendly, the codec is the work | **designed**, prerequisite known |
| Palette / colour swaps (ALttPR `Palette`, OoTR `Cosmetic Colors`) | character colours are `.peg` palettes | **blocked** — `.peg` undecoded |
| Model swaps (mooks become bosses, funny models) | `.mvf` refs shuffle between equal lengths | **exists** (shuffle) / **blocked** (new models) |
| Interface/cosmetic text (`Item names`) | item names are text; equal-length swaps work | **exists** via shuffles |

---

## 8. Can we replace the music with other music?

**Answer: yes in principle, and the container is friendlier than expected — but the codec has to
be decoded first, and only music the user supplies (or we generate) may ever be used.**

### What the music actually is (measured, not guessed)

| Fact | Value |
|---|---|
| Archive | `MUSIC.VPP`, ISO offset `0x2DA6F800`, 428,976,128 bytes |
| Tracks | **131**, named in plaintext: `catacombs.vmu`, `forestday.vmu`, `01-boss-luminar.vmu`, `ending01.vmu`, `credits.vmu`, `Ghost_Rider_Escape.vmu`, … |
| Format | `.vmu` — a Volition music container, decoded by the game's own `vmusic` engine (`vmusic::open` `0x0015ACB0`, `vmusic::process_block_read` `0x0015B010`, `vmusic_block::process` `0x0015AA78`) |
| Track sizes | 336 KB to 10.6 MB (median ≈ 3 MB) |
| Table of contents | 64-byte records from `0x800`: name[48] + 3 reserved u32 + **size** u32 — note: **no offset field** |
| Data start | **`0x3000`** — derived, not assumed: archive size − sum(sizes rounded up to 2048) = 12,288 = 0x3000 |
| Entry alignment | **every entry starts on a 2048-byte boundary** |
| Header | each track begins with a small header (entry 0 reads `0xBA, 0xB9C, 0x759`, …) followed by low-entropy data consistent with a compressed/ADPCM stream |

### Why that is good news for replacement

Because offsets are **implicit and 2048-aligned**, a replacement track that is the **same length
or shorter** needs *no* offset fixups anywhere: write it into the entry's slot and zero-pad the
remainder of the alignment. Nothing else in the archive moves, the archive size is unchanged, and
the ISO stays byte-for-byte the same length. That is the same discipline as every other edit in
this project, and it means music replacement is **not** blocked on the archive-slack question.

A *longer* track would shift every following entry, so it needs either the remainder of the
alignment as headroom (up to 2,047 bytes, useless for music) or a full archive/ISO rebuild. Full
rebuilds are technically feasible — the project already rebuilds the disc byte-identically — but a
rebuilt disc is no longer "same size, only the data region touched", so it becomes a separate,
more carefully tested path.

### The actual prerequisite

`.vmu` is a **custom codec**, not a standard container: no `VAGp`, `RIFF`, `OggS` or `FMT` magic
anywhere in the tracks. So replacing music needs, in order:

1. **Decode `.vmu`** — read `vmusic::open` / `vmusic_block::process` in the Ghidra project to find
   the block structure and the sample format (likely 4-bit ADPCM with a small header).
2. **Write an encoder** for it, or at minimum a *same-format transcoder* that can take a decoded
   PCM stream and re-emit valid `.vmu`.
3. **Only then** the transform: `music_replace` — swap track A's payload for track B's, or inject a
   user-supplied file, pad to the alignment, done.

### The legal line, drawn now

Music is the most copyrightable thing in the project. Whatever gets built, **the randomizer ships
no music**, exactly as it ships no game data. Two acceptable sources only:

* **the user's own audio** — they point the tool at a folder, it converts and patches their disc;
* **generated audio** — our own synthesis (the project already generates music for other tasks),
  or CC0/public-domain material the user supplies.

Swapping *which game track plays where* (`music_shuffle`) is already shipped and involves no new
media at all.

### What to do next, concretely

1. Add `music_replace` to `PLANNED.md` with the constraint set above (same-or-shorter, 2048-pad,
   user-supplied audio only).
2. Decode the `.vmu` block format (Ghidra pass on the `vmusic` family) — that is the single
   blocking task, and it is bounded.
3. Prototype with one track: decode a small one, re-encode it, and check the disc still boots and
   the track still plays.

---

## 9. Recommended adoptions

Ranked by value for effort, given what this game actually exposes:

1. **Door destination remap in the engine** — the headline feature, proven, still a lab script.
2. **Enemy damage/stat shuffle + player stat shuffle** — cheap, visible, and directly requested.
3. **Hints over `+NPCText`** — a hint system is pure text-layer work, and this game has a *lot* of
   NPC dialogue to hide hints in. Nobody expects a hint system from a Summoner randomizer.
4. **Spoiler log + seed sharing** — seeds are already reproducible; this makes runs shareable.
5. **Entrance "levels"** for the door remap (same-region → crossed → insanity) — reuses the remap's
   own constraint list, and mirrors how ALttPR/Zelda 1 present the same feature.
6. **Music replacement** — big payoff, gated behind one bounded reverse-engineering task.
