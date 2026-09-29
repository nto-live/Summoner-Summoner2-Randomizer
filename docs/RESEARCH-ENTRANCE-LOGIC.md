# Research — Entrance / Door Randomization: How Everyone Else Solves It

*Written 2026-09-20. Researched because doors are our blocker and this is a solved problem
genre-wide — just never for Summoner. Everything here is public documentation and public
source; no game data or copyrighted assets are copied.*

## 1. The one-line summary

Nobody shuffles doors by shuffling doors. **They shuffle *exits* onto *entrances*, then verify
the result is completable and retry until it is.** A graph, a shuffle, and a reachability
solver. That is the whole design, and it is what we should build.

## 2. Vocabulary worth stealing

From the DKC2 Entrance Randomizer's own README, which explains it better than anything else:

- **Exit** — a way *out* of the place you are. (`1-1 exit`, `1-1 bonus 1`, `1-1 warp`)
- **Entrance** — a way *into* a place. (`1-1 start`, `1-1 from bonus 1`, `1-1 from warp`)
- **Logic** — "ensures the seed is completable."

The README is emphatic that *this is not an exit randomizer*. Exit randomization and entrance
randomization are **different features** with different failure modes. We have been sloppy
about this distinction; for Summoner we need to decide which one we are doing, because:

- shuffling **destinations** (where a door sends you) can strand the player
- shuffling **arrivals** (which door you appear at) usually cannot, because the level graph
  stays intact

**This is the single most important design fork in the doors work**, and it is cheaper to
choose correctly now than to discover it in playtesting.

## 3. Logic tiers — adopt these three verbatim

DKC2's three modes are the clearest expression of the honesty dial a randomizer needs:

| Tier | Meaning |
|---|---|
| **Easy Logic** | avoids any *required* backtracking; you can still go backwards, it is just never necessary |
| **Hard Logic** | does not consider direction; **backtracking may be necessary** |
| **No Logic** | zero restrictions — **the game may not be possible to finish** |

This maps perfectly onto our existing honesty policy (we already publish a `risk` string and a
blocked-feature list). Doors should expose exactly these three tiers, named the same way, so
players who know the genre already understand them. `No Logic` is not a bug — it is a
*requested* mode by people who enjoy route-breaking.

## 4. The constraints catalogue — this is our reachability guard

Entrance randomizers do not just shuffle and hope. From the OoT and Twilight Princess wikis,
the documented constraint categories are:

- **Cannot spawn in a boss room.**
- **Cannot spawn in the endgame area** (OoT: "cannot spawn in the area Outside Ganon's Castle").
- **A refill area must always be reachable with no items** (OoT: "either Kokiri Forest or
  Kakariko Village must be reachable from the start of the seed with no items. This is to
  ensure ammo can always be refilled").
- **Item-gated areas need guarantees** (OoT: the Big Poe Shop stays reachable without bottles;
  a Hylian shield is required as adult for specific scrubs).
- **Per-dungeon "ER Logic Quirks"** — OoT documents an explicit quirks list for Desert
  Colossus, Deku Tree, Jabu-Jabu, Forest/Fire/Water Temple, Ice Cavern. **Every one of these
  is a hand-written exception someone had to find by playing.**
- One entrances type is simply excluded: "overworld spawns can currently never be inside a
  grotto due to issues with how they are coded." **A documented, accepted limitation.**

Translated to Summoner, our starting constraint set:

1. **Never remap into the endgame.** The Forge / gamestage-21 path stays gated behind
   `ready_for_end`. This is the one that actually loses a run.
2. **Never remap into a level with no exit** — no one-way traps.
3. **Keep a hub reachable from the start**, mirroring the ammo-refill rule (Summoner has shops
   and rest points; something equivalent must remain reachable).
4. **Account for the seven anchored rings.** Ring Hunt changes which flags open the ending; a
   door remap that hides a ring behind an unreachable door breaks the mode combination.
5. **Expect a quirks list.** OoT needed one per dungeon. We should budget for the same rather
   than assuming the general rule is sufficient.

## 5. Mode taxonomy — adopt as our door modes

From the Twilight Princess Entrance Randomizer wiki, the four settings are a ready-made
feature list:

- **Randomize Starting Location** — with explicit spawn restrictions (not a boss room, not the
  endgame area) and a note that it auto-skips the prologue.
- **Shuffle Dungeon Entrances** — and entry portals return you *in front of the entrance you
  came from*.
- **Unpair Entrances** — where a single place has **two** doors, each door becomes its own
  independent entrance (TP: left door → Temple of Time, right door → Palace of Twilight).
- **Decouple Entrances** — entrances stop being assumed two-way: "Link could enter Forest
  Temple to find Temple of Time, but then turn around and leave and be placed in Lake Hylia."

**Unpair is a gift for us.** Our portal records already carry **two** side IDs per portal
(`+0x08` and `+0x0C`, established from `check_portal_crossing`). That is precisely a paired
entrance, so "paired / unpaired / decoupled" is a natural and *implementable* set of door
modes given the data we already understand.

Also from ALttP's entrance randomizer, the **coupling rule**: "keeps all 4-entrance dungeons
confined to one location such that dungeons will one to one swap with each other." Coupling
preserves a structure's internal topology while shuffling the structure itself. Worth having as
an option rather than shuffling every door flat.

## 6. The algorithm

```
build a graph:  nodes = levels, edges = doors/exits
shuffle edges under the constraint set (tier + coupling rules)
verify: from the start, with no items, which nodes are reachable?
        is the required endgame path reachable?
if not -> re-shuffle and retry (bounded attempts, then relax or fail loudly)
emit: the chosen mapping + a spoiler log
```

The reachability check is a plain graph flood-fill. The *hard* part is not the algorithm — it
is enumerating the constraints, which is exactly why OoT has a hand-written quirks list.
**Do not let the search for a perfect general rule block step one.** A flood-fill plus a small,
honest constraint list beats an elegant model we cannot specify.

## 7. Spoiler logs — a standard feature we are missing

The KH2 randomizer's changelog is full of spoiler-log work: a search bar for boss/enemy
replacement, and specifically *"Keyblade slots should no longer show as unreachable in the
spoiler log (unless they are actually unreachable)"*, plus a "report depth" setting.

Two lessons:

1. A **spoiler log is standard**, and it is where unreachable things get surfaced.
2. The phrasing "**unless they are actually unreachable**" is the mature attitude: the log
   *reports* unreachable entries rather than hiding them. Our randomizer should emit a log
   listing the door map, the seed, the mode, and anything the verifier flagged.

## 8. Testing discipline worth copying

`tommadness/KH2Randomizer` (Python, ~2,083 commits) carries `seedtests/`, `tests/`, and a
dedicated `item_distribution_checker.py`. The equivalent for us is a **seed test harness**:
generate N seeds across every mode, assert each passes the reachability verifier *and* boots
in the emulator. We have the boot harness already (§8 of `COMPILED-CODE.md`); marrying it to a
seed loop is the missing half.

## 9. PS2-specific tooling worth knowing

| Tool | What it does | Relevance |
|---|---|---|
| **PS2 Patch Engine** (pelvicthrustman) | embeds **static ELF *and* runtime memory patches** into PS2 disc images; accepts RAW or **PNACH** cheat format; .iso/.img/.bin; converts .bin→.iso | the closest existing thing to what we do. Note its own claim: *"How can you embed code into an executable without breaking it? — By knowing that PS2 games are written in C; in this case by exploiting `string.h`."* |
| **Snaggly/PS2_Pnacher** | applies PNACH files directly to an ISO via libcdio; **locates the ELF inside the ISO itself** | same job as our `find_elf` — independent confirmation the approach is standard |
| **Finzenku/Ps2IsoTools** | reads/builds/edits **UDF** PS2 ISOs (C#, from DiscUtils) | if we ever need to rebuild rather than patch in place |
| **anasrar/ps2iso** | unpack/pack a PS2 ISO to JSON + files | quick inspection tool |
| **PS2Recomp**, **ps2mkisofs** | recompile PS2 binaries; build PS2 ISOs | longer-term, not needed |
| **OpenKH** (Kingdom Hearts, 430★) | libraries + tools + **a game engine** + full docs site | the model for documenting a whole game's internals properly |
| **gaithern/KH1FM-RANDOMIZER**, **tommadness/KH2Randomizer** | PS2-era randomizers in the open | PS2 randomizers *do* exist in public — ours is the first for Summoner |

### 9.1 PNACH is worth taking seriously

`PS2 Patch Engine` and `PS2_Pnacher` both speak **PNACH** — the documented PCSX2 cheat format.
That gives us two things:

1. **A second path to the fast-iteration win.** A patch expressed as PNACH can be applied
   *live in the emulator* with no ISO copy at all — no 1.2 GB write, no 80-second cycle. For
   door experiments this is the fastest possible loop.
2. **A tiny, standard, shareable seed format.** A seed becomes a small text file of code
   types, which the community's own tooling can already apply. Same "no game data" benefit as
   the PPF idea in `RESEARCH-SOTN.md`, with better tooling support.

Caveat to check: PS2 Patch Engine notes *"not all cheat code types are supported"*, and
runtime memory patches only exist while the emulator session does — so PNACH is a
**development and sharing** channel, not a replacement for a patched disc.

### 9.2 A fallback if static data patching fails

PS2 Patch Engine's core trick is embedding a **bootstrap that applies patches at runtime**. If
door destinations turn out to be runtime-computed (which would defeat a static data patch), the
fallback is: leave the game's data alone and intercept the value at runtime instead. That is a
genuinely different implementation route and it is proven to work on retail PS2 hardware.

## 10. Net effect on the doors plan

*Status column added 2026-09-21 — see §11 for what actually happened.*

1. **Decide the fork first:** are we shuffling *destinations* (risky, needs the guard) or
   *arrivals* (safer)? Everything else depends on this answer. — **DECIDED.** Room Shuffle
   (content, not graph) is the safe default; Door Shuffle (destinations) becomes a real opt-in
   mode **with** the guard.
2. **Adopt the three logic tiers** by name: Easy / Hard / No Logic. — **OPEN.** Not implemented;
   nothing in the app exposes named logic tiers yet.
3. **Adopt the mode taxonomy**: Shuffle Doors · Unpair Doors · Decouple Doors · Start Location.
   — **OPEN.** Note the naming collision: the shipped **Door Shuffle** mode shuffles door
   *locks, names and sounds*, **not destinations**. Real destination shuffling needs a new name.
4. **Build the guard as a flood-fill plus an explicit constraint list**, and expect a hand-kept
   quirks list. Do not wait for a perfect rule. — **OPEN.** The constraint list is drafted in §4.
5. **Emit a spoiler log** from the first working version. — **OPEN.**
6. **Wire a seed test loop** (N seeds → verify → boot) rather than testing single builds. —
   **PARTIAL.** `F:\rando\S1\notes\compare_runs.ps1` boots a list of discs through one harness and
   compares verdicts; it is not yet a seed loop.
7. **Try PNACH as a development channel** to make the door iteration loop fast instead of
   80 seconds long. — **OPEN.** Still the best candidate for fast door iteration.

---

## 11. Status update — 2026-09-21 (what changed, and what did not)

The mechanism question is **settled**, and the design fork is now more nuanced than §2 assumed.

**Doors are text, and the destination is the `$Trigger:` name.** A door is a `#Triggers` block in
that level's `.tbl`; the quoted name is the destination level. The 218 in-place name rewrites were
applied to a copy and the result **boots**, with a clean whole-image diff. Full record:
`tools\summoner-rando\DOOR-REMAP.md`. So the genre comparison above is still the right checklist,
but the *implementation* turned out to be cheaper than any of the precedents: no code injection, no
bootstrap, no runtime interception — one string rewritten in place.

**The fork sharpened rather than resolved.** §2 framed it as *destinations vs arrivals*. The owner's
pivot reframed it as *destinations vs contents* (Room Shuffle): a content permutation leaves the
level graph intact, so unreachable regions become impossible by construction and no solver is
needed. That is now the recommended default, with destination shuffling kept as an opt-in mode.

**Cost ≠ risk.** Doors got *cheap*; they did not get *safe*. Destination rewrites still change the
level graph, still can strand a player, and still need the §4 constraint set plus a flood-fill.
Nothing in this section removes work from items 1–7 above.

**One correction to §9.2.** The "fallback if static data patching fails" worry is moot for doors:
destinations are read from the text layer at load time, and a static in-place rewrite of that
string is sufficient. §9.2 remains relevant only if a future feature turns out to be runtime-computed.
