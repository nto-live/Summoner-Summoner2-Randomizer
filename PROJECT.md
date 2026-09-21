# Summoner Randomizer — Project Document

*Last updated 2026-09-20.*

---

## 1. What we are building

A **randomizer for Summoner** (PS2, Volition/THQ, 2000, SLUS-20074) — and later
**Summoner 2** (PS2, 2002, SLUS20448). A randomizer reshuffles a game's contents so no two
playthroughs match: which items exist where, what doors connect to, which prices apply —
and, in our case, **when the game ends**.

The tool is a self-contained app. You supply your own disc; it writes a new, playable ISO.

**Nobody has done this before.** Summoner has had essentially no modding scene in 25 years.
The only community tool for the PS2 release is a widescreen patch. Everything here was
worked out from the disc.

---

## 2. Status at a glance

| | State |
|---|---|
| Both retail discs | dumped, hash-verified, and rebuilt byte-identical from parts |
| Summoner 1 | **editable** — VPP v1 decoded, full pipeline working |
| Summoner 2 | **detected, not editable** — VPP v2 reader not written |
| App | self-contained, works, ships no game data |
| Text layer | **33 transforms, 24 modes** shipped |
| Binary layer | **built and proven** — `binary.py` patches the executable, verified to the byte on disc |
| `.p3d` | doors located in geometry; portal mechanism understood, format not |
| **Doors** | **SOLVED** — text-layer `$Trigger:` name rewrite; 218-patch remap applied clean and **boots** (`DOOR-REMAP.md`) |
| **Door remap in game** | **VERIFIED (2026-09-21)** — headless run, no pad: two discs differing only in one rewritten destination load two different levels. `DOOR-REMAP.md` §4.5 |
| In-game verification | **LIVE** — headless PCSX2 reaches real gameplay; **requires `Renderer = 13` (Software)**, or Vulkan freezes the game (§7) |
| Desktop app | **built** — WinForms, ISO in / ISO out, seed shown; web server retired |

Four things happened since the last update, and they change the shape of the project:

1. **The binary layer exists and works.** `binary.py` patches `SLUS_200.74` inside the ISO with
   refuse-on-mismatch and read-back verification (§3.5).
2. **In-game verification is unblocked** — the Session 0 problem was solved, and both patched
   test discs boot the real game (§7). This was the gate on everything.
3. **The web UI was replaced by a desktop app**, per the owner's call (§4).
4. **Doors are solved and proven at the patch level** — the mechanism is a text-layer name
   rewrite, 218 door remaps were applied to a copy with zero collateral bytes, and the resulting
   disc boots (§6, and `DOOR-REMAP.md` for the full record).

Two randomizer layers now exist. The **text layer** edits the script stream and is done.
The **binary layer** edits the executable itself — built, and being extended for doors.

---

## 3. What we have reverse-engineered

### The archive format (VPP)
Volition Pack, magic `0x51890ACE`. Version 1 header: entry count at `+0x08`, archive size
at `+0x0C`, a 64-byte-record table of contents at `0x800`, entry data packed from `0x1000`.
**Filenames are stored in plaintext.** Nine archives on Summoner 1, 6,433 files.

Version 2 (Summoner 2) uses the same magic but a different header: count at `+0x3C`, size at
`+0x40`, and a 28-byte TOC record. We can *detect* it and read its filename table, but the
reader is not written.

### The data layer is not binary
`TABLES.VPP` holds a **plain-text script language** — doors, dialogue, spawns, triggers,
items — not compiled tables. Randomizing it is text surgery, not binary patching.

```
#Doors
$Door: "cry_tombcen"
+Open sound: "Doors\Open_Stone_verylarge.wav" 20.0 1.0 1.0
+Locked: 0.50
```

### The one constraint that shapes everything
Those 527 entries are **arbitrary slices of one continuous 6,771,975-byte stream** — 424 of
526 boundaries cut mid-line. We proved it twice: `$F` + `og:` stitches across two "files"
to form `$Fog:`, and one NPC sentence is split mid-word across another boundary.

The chunk names are therefore unreliable labels (`items.tbl` is *not* the item table), and
the boundaries must not move. **Every transform is length-neutral**: values are swapped only
between equal-width fields, and flags renamed only with same-length strings.

### The executable is mapped
`MAIN.MAP` shipped **unstripped** on the retail disc — 6,561 symbols and 275 original source
filenames. With the single `PT_LOAD` segment (`vaddr 0x00100000` → file offset `0x1000`) we
have byte-exact patch targets, and named functions:

```
0x0017A570  door_is_open(int, float)
0x00182D08  party_controller_new_party(living_entity *)
0x00182E40  party_controller_add_member(ai_party *, living_entity *)
0x001B5808  item_new(int)
0x001E98E8  level_script_load_effects(void)
```

### 3.4 The executable, read for real

See **`COMPILED-CODE.md`** for the full toolchain and reproduction steps. Headlines:

Applying the 6,561 MAIN.MAP symbols names 3,391 functions — 21 door-related, 185 level,
36 party, 89 item, 10 teleport. Getting there needed Ghidra 12.1.3 plus the
`ghidra-emotionengine-reloaded` extension, installed as a **processor module** rather than
an extension (the extension route fails with `Unsupported language: r5900:LE:32:default`).
With R5900 support: **0 Pcode errors**, and the decompiler produces readable C.

**The portal mechanism — which is the door answer.** `check_portal_crossing` decompiles at
`0x0017EA28`. Portals are a **singly-linked list** rooted at global `puGpffff9930`. The
record layout, read straight off the code:

| Offset | Field |
|---|---|
| `+0x00` | point A |
| `+0x04` | point B |
| `+0x08` | **side ID 1** |
| `+0x0C` | **side ID 2** |
| `+0x10` | next portal |

If the player's movement segment crosses a portal's segment and `side1` matches the current
side, the other side ID is returned. **Those two IDs are what an entrance randomizer
shuffles** — and we now know their offset and type instead of guessing strides in `.p3d`.

Also named and useful: `door_is_open`, `get_door_open`, `dcf_door_open/close/toggle`,
`gameplay_unload_level`, `is_valid_level_script_filename`, and a `dcf_*` family
(`dcf_gamestage`, `dcf_full_party`) that looks like an internal debug console.

### The endgame — the key discovery
**There is no ring counter.** The ending is gated by one flag, `ready_for_end`, and
gamestage 21 is *defined as* that flag. The eight-ring requirement is enforced
**narratively** — the Guardian of the Stone Portal simply does not hand over the last ring
until the Ulsadana destiny lecture has played.

`ready_for_end` is exactly **13 characters**, which means any other 13-character `+Event:`
flag can be renamed to it in place. No format work, no ELF patch, trivially reversible.

Surveying the corpus found **11 such anchors**, and four of them sit directly beside ring
pickups:

| Anchor | Rings nearby |
|---|---|
| `act3_finished` | Ring of Jade, Ring of the Four Winds |
| `ikaemostopint` | Ring of Fire, Ring of Stone |
| `unhide_luvela` | Ring of Darkness, Ring of Forest |
| `unhide_tathal` | Ring of Fire, Ring of Water |

That is **7 of the 8 rings**. Only the Ring of Light has no adjacent anchor.

---

## 4. What the app does

```
your ISO → identify → read TABLES.VPP → transform the script stream
         → patch the executable → write a new ISO
```

**A desktop app, not a web server.** The first version was a local HTTP server; the owner's
verdict was "why is there a server, this needs to be like a win form that takes an iso and
returns a new iso, also it shows the seed." He was right, and it is now:

**The deliverable is the ISO.** The end-user product is the WinForms app plus the ISO it writes —
not the CLI, not this document. It is packaged so it runs on a computer with none of this
development environment: one folder holding `SummonerRando.exe` (self-contained .NET) and
`summoner-engine.exe` (the engine frozen with PyInstaller, no Python needed). See
`desktop\PACKAGING.md`. `package-portable.ps1` at the repo root builds that folder.

**Playing it needs a PS2 emulator (or real hardware).** The app cannot run a disc by itself, so it
finds PCSX2, remembers one the user points it at (`emulator.txt` beside the exe), and offers a
**Play ISO** button; with none installed it says so plainly rather than failing silently. It does
not ship an emulator — PCSX2 is third-party and needs a BIOS the user supplies.

| Piece | What |
|---|---|
| `cli.py` | **the engine, with a JSON interface** — `--list` · `--identify` · `--seeds N` · `--build` · `--dry-run` · `--include/--exclude/--options`. Progress streams to stderr as `#progress …`, the result is one JSON object on stdout. Exit 0 ok / 2 refused / 1 error. |
| `desktop\` | **the WinForms app** — `SummonerRando.Engine` (runs cli.py, parses its JSON), `SummonerRando.Desktop` (the window), `SummonerRando.Harness` (console harness driving the same plumbing with no GUI), `publish\SummonerRando.exe`, `Run.cmd`. Targets .NET 8; builds with 0 warnings. |
| `discover.py` · `rando_core.py` · `binary.py` | identification · transforms + pipeline · executable patching |
| `_legacy-web-ui\` | the retired server + browser UI, kept for the record |

The GUI shows the **seed in the window title** as well as the field, disables Build for an
unsupported disc, renders the option dials only for transforms that are actually active, and
prints the blocked-feature list rather than hiding it. Stdlib plus `pycdlib`; no game data.

- **Disc identification** by volume ID *and* archive fingerprint, so the retail Summoner 1
  disc is recognised despite having a blank volume ID.
- **Honest refusal** — Summoner 2 is rejected with a reason, never a silent no-op.
- **Intake** — drag-and-drop a multi-GB ISO (streamed, never buffered), paste a path, or
  register a folder.
- **Dry run** — reports exactly how many edits and blob bytes a build would change, without
  writing a 1.2 GB file.
- **Seeds are reproducible** — same seed + same mode + same options gives a byte-identical
  ISO. That is what makes seed sharing and racing possible.
- **Every binary patch declares what it expects** and refuses to write if the disc does not
  match, then reads the bytes back to confirm. A wrong disc revision cannot be corrupted.
- **The GUI needs a display; the engine does not.** The verification harness and `cli.py` run
  headless, which is how a build gets tested without a person at the keyboard (§7).

---

## 5. Modes and options shipped

**Twenty-four modes, 33 transforms.** Full detail in **`MODES.md`**.

**Content:** Door Shuffle · Item Scatter · Shop Shuffle · Chest Shuffle · Dialogue Chaos ·
Sound Chaos · Visual Chaos · Chaos
**Pacing:** Short Run · One Hour · **Fast Start** · No Dialogue
**Progression:** Ring Hunt · **Ring Hunt · Any Ring** · Ring Hunt · Short · **Progression**
**Pressure:** Roguelike · Roguelike · Short · **Hardcore**
**Chaos:** Monster Chaos · Behaviour Chaos · Total Chaos
**All:** Everything · Vanilla (baseline)

**Ring Hunt** is the headline — it changes *how the game ends*:

- `any-ring` — the ending opens on **any** of the seven anchored rings. Find one, finish.
- `safe` — end-of-act milestones only (`act3_finished`, `gesualdo_done`, `no_more_korel`,
  `got_map_quest`)
- blank — the seed picks the anchor
- plus *how many* anchors, and whether to prefer end-of-act flags

**One honest trade-off:** the chosen anchor stops setting its original flag, so anything
checking that flag no longer fires. This is why end-of-act anchors are the default pool.

**Two deliberate omissions.** `+Topic:` ids are never shuffled — they are reference keys
that `+Add Topic:` points into, so shuffling definitions without references can strand a
quest. And renaming ids *consistently* is not chaos, just a rename with no visible effect.

**Two new progression modes.** **Progression** exposes the two deterministic dials —
`xp_scale` (every `+AddXP:` reward) and `levelcap_set` (every `+Levelcap:`) — so XP and
levelling can be dialled by hand instead of fixed by a preset. **Hardcore** is the full
Roguelike stack plus **`permadeath`**: it renames the revive ability and Revive Scroll items
in place so death sticks. Permadeath is table-defined and size-preserving, but untested in
game — an unknown action/item name may be ignored (intended) or may error.

---

## 6. What we plan to accomplish

### Now — doors, and the pivot to rooms

The owner's directive: **"Iterate on this until you get a patched working copy. First feature
is the doors."** Then, later the same evening, a better idea:

> *"Instead of changing the doors can we change what rooms are — so the door will lead
> somewhere but that room is different?"*

**That is the safer half of the design fork** documented in `RESEARCH-ENTRANCE-LOGIC.md` §2,
and it is now the recommended approach:

- Shuffling **destinations** (where a door sends you) changes the level graph. It can strand
the player and can dump them into the endgame, and it needs a reachability solver plus — per
OoT's example — a hand-maintained quirks list.
- Shuffling **contents** (what a place is made of) leaves the graph intact. Every door, return
path, quest flag and navpoint keeps working, because the level is still itself. Unreachable
regions become **impossible by construction**.

It does not dodge the investigation — we still need to know how a level's identity and content
are selected at load time — but it changes the target: **keep the name, swap what the level is
made of.**

**Three variants, safest first:**

1. **Interior contents only** — permute what populates a level (spawns, containers, props,
   NPCs, ambient) but leave the geometry alone. Cannot softlock. May need no binary work at
   all: the text layer already shuffles these *within* the blob, so the new part is restricting
   the permutation to be *between* specific rooms.
2. **Content swap including geometry** — level A keeps its identity, script and progression,
   but its interior comes from level B. Walk through a door to A and the room is different.
3. **Full level swap** — A *is* B, geometry and script both. Riskiest: cross-level references
   (`+Level:`, navpoints, quest NPCs, boss arenas) may assume the original layout.

**The deciding question still under investigation:** are quest-critical things keyed to level
*identity* or to level *content*? `+Action: "teleport to" "$navpoint"` being intra-level is a
good sign — it limits the blast radius. Cross-level navpoint or flag references would make
variant 3 dangerous and variant 2 risky.

**Keep the door-destination idea**, but as a later, opt-in, `No Logic`-style mode. People do
want it; it is simply not the safe default.

**SOLVED — and it corrects the record.** Doors are in the **text layer** after all. Our earlier
"text layer ruled out" conclusion was wrong because it generalised from the wrong file type:
`$Trigger:` in a *character* `.tbl` is animation timing, but `$Trigger:` in a **level** `.tbl`
is the door destination.

```
#Triggers
$Trigger: "catacombs"        <- THE DESTINATION LEVEL NAME (inline)
    +Id: "load level"        <- index 0 of {"load level","boss","sound"}
    +Index: 1                <- player start id in the destination
    +Type: "spline"          <- "spline" | "location"
    +Spline name: "$loadarea01"
```

`level_script_check_level_load @ 0x002023C0` (called every frame from
`level_script_do_frame`) walks `Level_triggers @ 0x1238B78` — 100-byte records — and on a hit
copies `record+0x00` into `Level_data.name`, which then builds `<name>.s3d`, `<name>.p3d` and
`<name>_script.tbl`. **Level identity is the name.** Verified directly on disc: **218**
`+Id: "load level"` triggers.

**The patch is a pure text edit.** For a name field of length L, write
`new + '"' + spaces(L - len(new))` — exactly L+1 bytes, so nothing moves and it is trivially
reversible. **No binary layer is needed for the headline feature.**

**Constraints that matter:** the target must be a real level name with `len ≤ len(old)`
(otherwise the resolved index is −1); `+Index:` must exist as a `$player…` navpoint in the
destination (`level_script_set_player_starts` hard-loops on failure); and blocks with no
`+Script:` should target only levels whose base script name equals the level name. Head-room
varies: the 125 nine-character destinations have 24 valid targets, and `"eleh"` has none.

**DONE — applied and booted (2026-09-20 22:10).** The 218 concrete patches were applied to a
copy of the disc and the result was put through the emulator. Full record in `DOOR-REMAP.md`;
the numbers:

| | |
|---|---|
| Patches | **218** (41 distinct original destinations → 31 new, 142 distinct mappings) |
| Validation | **218/218 validated, 0 refused** — every patch found exactly the bytes it expected |
| Read-back | **0 mismatches** |
| Size | `1,232,699,392` both sides — **byte-identical** |
| Whole-image diff | **1,679 changed bytes, every one inside a field we deliberately wrote** — zero collateral |
| Boot | **PASS** — cpu=28.5s/90s, rss=879MB, thr=17, **CRC 13E2774E** (unchanged, correct: the executable was never touched) |

**The CRC is the useful tell.** It is identical to vanilla and to the 15,235-edit randomizer
build, and shifts only when `SLUS_200.74` changes (`13E2775E` on the endgame disc). The emulator
is independently confirming that our edits land in the data layer and nowhere else.

**Honest limits:** no door has actually been walked through (no pad input headlessly); the
`+Index:` hard-loop caveat is untested; reachability is unchecked. Boot-verified is not
play-verified.

**Corrected:** `level_save_game_data_set_pending_load` (`0x0023919C`) is the **save-game** load
path, not doors — and a dead function, `level_script_ask_level_load @ 0x002029D8`, has no
callers at all. Chasing that wrong lead is why this took so long.

**A light guard is still needed.** Even a content swap can break a scene staged at a specific
spot, a container the game assumes exists, or Ring Hunt's anchored rings if the changed room is
where an anchor flag lives.

**Iterate in the rig** (`F:\rando\S1\notes\iterate.ps1`): build → whole-image byte diff → boot →
verdict, until a patched disc is a working copy.

### Then

5. **Observation for door tests.** Reaching an actual door needs pad input, which headless
   emulation does not have. The plan, best first: **verbose emulog / CDVD file-read logging**
   (a level transition shows up as disc reads, so loads become visible with no screen); a
   **test-only patch that forces a level load at boot** so a remap is observable
   deterministically; **PCSX2 pnach** memory writes; and input injection via `PostMessage`
   (SDL translates `WM_KEYDOWN`, but `SDL_GetKeyboardState` reads async state and would not
   see it — only event-polling bindings would work).
6. **`--patch-only` output** — emit a small patch file instead of a 1.2 GB ISO copy. SotN's
   PPF mode is the precedent, and it matters twice over: seed files become tiny and
   shareable *without distributing game data*, and the ~80 s build drops to seconds (§10).
7. **Seed sharing** — SotN's seed URLs and Bounty Hunter seed cards are the model (§10).

### Then

4. **Boss rush.** Roughly twelve self-contained boss encounters exist as their own script
   entries, with boss flags (`catacombs_boss_dead`, `ikaemos_boss_killed`, `masad_flag_boss`,
   `sewerboss`). A **boss gauntlet** in a single arena is achievable now by relocating spawns.
   A *sequential* rush needs arena→arena chaining, which is the same missing link as doors.
5. **Chest contents, properly.** `chest_shuffle` moves payouts today. Real chest randomization
   means changing *which item* a chest yields. Two obstacles: chest `+Give` does not set the
   `got_ring_of_*` flags (needs a companion flag patch), and the **Ring of Jade has no grant
   record anywhere** — likely granted in executable code, which the binary layer can now read.
6. **Item hunt, deeper** — tie items to containers and quest rewards so a seed genuinely
   relocates loot.
7. **Creature stats at the binary level** — the table layer exposes 337 `$Speed` / 337
   `$Weight` records, already shuffled by `creature_stats_shuffle`, but the rest of the stat
   model lives in `.data`.
8. **Build matrix and playtest** across all 24 modes; fix what breaks.

### Later — deferred

9. **Timed runs — parked, not shelved.** The engine already tracks elapsed time in one 64-bit
   global, at a known 286 Hz, with a formatter function already written (`timer_format_time`).
   The owner asked for this to be finished *later*, not now, so it is explicitly deferred.
   **`TIMER-DESIGN.md` stays as the design record**: Tier 1 is an external timer reading the
   counter via PCSX2 PINE (no game modification, validates the premise); Tier 2 puts the final
   time on the completion screen via a targeted code hook.
10. **VPP v2 reader** — unlocks Summoner 2 entirely.
11. **Character models** (`.mvf`, 2,556 files) and **colours** (`.peg` palettes).
12. **Faction flipping** — blocked because `+Team:` values are 4/7/8 characters and therefore
    not swappable in place.
13. **Party roster control** — repoint a party slot at a different creature definition to
    field a monster. `party_controller_add_member` is the named hook; we need the
    creature-definition table.
14. **Archive slack** — roughly **619 KB** of unused space sits between the sum of entry
    sizes and the archive's data region. If the game reads entries by offset rather than
    fixed position, we could **grow the blob** and lift the size-preserving constraint
    entirely. That would unlock proper XP multiplication, appended data, genuinely new
    characters, and authored endgame chains. Unresolved, and it needs a boot test.

---

## 7. Verification — was the blocker, now SOLVED

**No mode could be verified in game** because PCSX2 would not start: OpenClaw's shell runs as
SYSTEM in **Session 0** (the services session, no interactive desktop).

**The cause was not Qt and not the missing desktop.** It was one config value:

> **`SettingsVersion` in `PCSX2.ini` must be `1`.** Any other value makes PCSX2 pop a **modal
> dialog at startup and wait forever** for a click that can never happen. That is the entire
> symptom: process alive, ~0.06 s CPU, `Responding=True`, main thread `WaitReason=UserRequest`,
> and no `emulog.txt`. Confirmed by brute-forcing versions 1–10 — only `1` avoids the dialog.

The native Qt `windows` plugin works fine in Session 0; invisible windows are still real
windows. The working invocation:

```powershell
$env:QT_QPA_PLATFORM = 'windows'
& 'C:\Program Files\PCSX2\pcsx2-qt.exe' -batch -fastboot 'F:\rando\S1\iso\Summoner.iso'
```

Live emulog from a real headless run:

```
[ 0.3264] BIOS Found: USA v01.20(02/09/2000)  Console 20000902-234318
[ 0.3867] Disc changed to Summoner.iso.  Serial: SLUS-20074  CRC: 13E2774E
[ 2.8948] VM subsystems initialized in 2568.77 ms
[11.1634] ELF cdrom0:\SLUS_200.74;1 ... is executing.
```

**Both patched test discs boot the real game.** `test-roguelike.iso` (15,235 edits) and
`test-endgame.iso` (1 byte of executable patched) each load the BIOS, read the disc, and
execute the boot ELF. The endgame disc's CRC shifts to `13E2775E` — correct and expected,
since we changed a byte of the binary.

**A door-remapped disc boots too.** `test-doors.iso` — 218 door destinations rewritten in
`TABLES.VPP`, 1,679 changed bytes, every one inside a declared field — passes the same harness
at 90 seconds, with the CRC still `13E2774E` (the executable is untouched). What that does and
does not prove is spelled out in §6 and `DOOR-REMAP.md` §3–4.

Harnesses live in `F:\rando\S1\notes\`: `pcsx2_headless_boot.ps1` (runs with timeout, samples
CPU, saves emulog, prints **PASS/PARTIAL/FAIL**), `iterate.ps1` (build → byte diff → boot →
verdict), and `pcsx2-headless-FINDINGS.md` (the full write-up, including the dead ends).

**A door remapped on disc loads the remapped level — observed, 2026-09-21.** Headless, no pad, no
screen: `Renderer = 13` (Software) keeps the game alive where Vulkan froze it, PINE reads/writes
live EE RAM, and a test-only pnach opens the door gates so the game fires the door by itself.
`Level_data.name` then reports what the game chose to load:

| Disc (one field rewritten) | loaded |
|---|---|
| vanilla, `worldmap1` (scripted door - needs the flag cleared) | `worldmap1` |
| `test-door1-catacombs.iso` | `catacombs` |
| `test-door1-Lenele1aa.iso` | `Lenele1aa` |

Full record, harness, and honest limits: `DOOR-REMAP.md` §4.5. **Boot-verified and now
play-verified as far as the door *destination* goes; the crossing geometry is still forced, and
reachability is still unchecked.**

**Dead ends — do not retry.** `QT_QPA_PLATFORM=offscreen` cannot work on this build: PCSX2
2.8.1 creates a real GS device and swapchain for *every* renderer including Null, and
offscreen supplies no HWND. Attaching to `WinSta0\Default` is unnecessary. `-nogui` is not
needed. An **absolute** path in `[Filenames] BIOS` is silently rejected with a fallback to a
Japan dump — a bare filename works.

**What is still unproven:** the crossing geometry (forced in the harness), the `+Index:` start-id
check, a whole playthrough, and anything about Summoner 2. See §6 step 5 and `DOOR-REMAP.md` §4.5.

---

## 8. Rules this project holds to

- **No game data is distributed, hosted, mirrored or linked** — on the website, in the app,
  or anywhere else. No ISO downloads, no download endpoints. The site says "bring your own
  legally dumped disc" and nothing more.
- The verified ISOs and part files on this machine are **never wiped**.
- Table-layer edits stay **size-preserving** until the archive-slack question is resolved.
- Unimplemented features are listed as blocked with a reason, never half-shipped.

---

## 9. Where things live

| Path | What |
|---|---|
| `tools\summoner-rando\` | **the app** (this folder) |
| `tools\summoner-rando\COMPILED-CODE.md` | Ghidra toolchain, portal mechanism, binary patcher, headless harness |
| `tools\summoner-rando\DOOR-REMAP.md` | **doors** — mechanism, patch format, the 218-patch proof, what is unproven, `DATA_PATCHES` design |
| `tools\summoner-rando\TIMER-DESIGN.md` | timed runs: the engine's RCNT0 clock, three implementation tiers |
| `tools\summoner-rando\RESEARCH-SOTN.md` | **NEW** — techniques consumed from the SotN randomizer, and what we are adopting |
| `tools\summoner-rando\cli.py` | the JSON engine the desktop app drives |
| `tools\summoner-rando\desktop\` | the WinForms app (`Run.cmd`, `publish\SummonerRando.exe`) |
| `F:\rando\S1\notes\pcsx2_headless_boot.ps1` | **the headless boot harness** |
| `F:\rando\S1\notes\iterate.ps1` | **the iteration rig** |
| `F:\rando\S1\notes\door-mechanism.md` | **the door mechanism write-up** — trigger records, `#Triggers` parser, 51-level inventory |
| `F:\rando\S1\notes\door-triggers.json` | all **218** `+Id: "load level"` doors with ISO offsets and fields |
| `F:\rando\S1\notes\door-remap-example.json` | the **218 concrete patches** used for the door proof |
| `F:\rando\S1\notes\apply_door_remap.py` | the door applier: refuse-on-mismatch, read-back, size check, whole-image diff |
| `F:\rando\S1\notes\verify_doors.py` | independent, read-only verification of the door claims against the disc |
| `F:\rando\S1\out\test-doors.iso` | the boot-verified door-remapped artifact |
| `F:\rando\` | the lab — RE tooling, extracted data, findings, docs |
| `F:\rando\S1\docs\` | `summoner-findings.md`, `randomizer-design.md`, `FEATURES.md`, `PLANNED-FEATURES.md`, `ITEMS-AND-CHESTS.md`, `ENDGAME-AND-RINGHUNT.md` |
| `F:\rando\S1\ghidra-ee\` | **Ghidra project, R5900 — the one to use** |
| `F:\rando\S1\notes\ghidra-symbols.txt` | 6,530 name→address pairs from MAIN.MAP |
| `F:\rando\S1\notes\ghidra-ee-decompiled.txt` | decompiled door / portal / gamestage functions |
| `F:\rando\S1\tools\ghidra_ee_decomp.py` | apply symbols + decompile, headless |
| `F:\rando\S1\iso\` · `F:\rando\S2\iso\` | verified source discs |
| `F:\rando\S1\tools\symbols.py` | ELF symbol table + address translation |
| `summoner-randomizer.pages.dev` | public project page |
| `github.com/nto-live/Summoner-Summoner2-Randomizer` | repository |
