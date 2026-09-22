# Door Remapping — the mechanism, the patch, and the proof

*Written 2026-09-21, documenting the work of the evening of 2026-09-20.*

This is the app-side companion to `F:\rando\S1\notes\door-mechanism.md` (the full reverse-engineering
write-up, including the trigger record layout, the `#Triggers` parser, and the 51-level inventory).
Read this file for **what the patch is, what it proved, and what is still unproven**; read that one
for **why it works at the instruction level**.

---

## 1. The answer in one paragraph

**A door is a `#Triggers` block in the level's own object table** (`<level>.tbl`, a plain-text file
packed inside `TABLES.VPP`). The destination is the trigger's **name**, written inline:

```
#Triggers

$Trigger: "catacombs"          <- THE DESTINATION LEVEL NAME (inline, ≤32 bytes)
    +Id: "load level"          <- trigger type: index 0 of {"load level","boss","sound"}
    +Index: 1                  <- player start id used in the destination
    +Type: "spline"            <- geometry mode: "spline" | "location"
    +Spline name: "$loadarea01"     (spline) the load-area mesh you cross
    +Location: "$khosani"           (location) navpoint
    +Radius: 1.2                    (location) radius around that navpoint
    +Script: ""
```

`level_script_check_level_load @ 0x002023C0` — called every frame from
`level_script_do_frame @ 0x00203378` — walks `Level_triggers @ 0x1238B78` (array of 100-byte
records, max 32) and on a hit copies `record+0x00` into `Level_data.name`. That single string then
builds `<name>.s3d`, `<name>.p3d` and `<name>_script.tbl`.

**Level identity is the name.** So rewriting that one quoted string is a complete, consistent,
size-preserving redirect of a door. **No binary patch is needed for the headline feature.**

### The correction this carries

Earlier drafts said doors were *not* in the text layer. That conclusion generalised from a *right*
observation about the wrong file type: `$Trigger:` in a **character** `.tbl` is animation timing
(true, and still true), but `$Trigger:` in a **level** `.tbl` is the door.

`level_save_game_data_set_pending_load` (`0x0023919C`) is the **save-game load** path, not doors —
its single call site is inside `ngps_loadsave_post_render_checks`, the save/load menu. And
`level_script_ask_level_load @ 0x002029D8` has **zero callers** (dead code). Chasing that wrong
funnel is why this took as long as it did.

---

## 2. The patch format

For a name field at `[off, off + L)` with the closing `"` at `off + L`:

```
replacement = new_name.encode() + b'"' + b' ' * (L - len(new_name))
```

Exactly **L + 1 bytes in, L + 1 bytes out.** Nothing moves, no header changes, the VPP size is
untouched, and reversing it is writing the original string back.

- Region: `TABLES.VPP` at ISO `0x49086800`, length `7,395,328`. Extracted copy verified
  byte-identical to the ISO slice.
- A patch carries `iso_offset`, `expect` (the exact bytes we require), `replacement`,
  `orig_dest`, `new_dest`, and a `src_level_comment` naming the source level.

### Constraints that make a remap legal

| Constraint | Why | Failure mode |
|---|---|---|
| Target must be a real `Level_info` name | the name is resolved to an index by `level_script_get_level_index` (case-insensitive `ngps_stricmp` linear search) | index −1 → out-of-bounds read |
| `len(new) <= len(old)` | the field is fixed width | cannot fit without moving the stream |
| `+Index:` must exist as a `$player…` navpoint in the destination | `level_script_set_player_starts` **hard-loops** on failure | looks exactly like a healthy running game from outside — see §5 |
| Blocks with no `+Script:` should target only levels whose base script name equals the level name | no script context to fall back on | undefined selection |

**Head-room is real and uneven.** `"eleh"` (4 chars) has **zero** valid targets and is
unpatchable. `"sewer"` (5) accepts 3. The 9-character names — **125 of the 218 doors** — accept 24.
`"IkaemosBottomInt"` (16) accepts 45.

---

## 3. The proof, end to end

**Patch generation** (`F:\rando\S1\notes\_remapgen2.py` → `door-remap-example.json`):

| Metric | Value |
|---|---|
| Patches generated | **218** |
| Distinct original destinations | **41** |
| Distinct new destinations | **31** |
| Distinct `orig → new` mappings | **142** |
| Field bytes written | **2,167** |
| Bytes that actually differ | **1,679** |

**Application** (`F:\rando\S1\notes\apply_door_remap.py`, source disc never opened for write):

```
patches in file: 218
validated: 218   refused: 0
total field bytes: 2167   expected differing bytes: 1679
size: src=1,232,699,392  dst=1,232,699,392  MATCH=True
readback mismatches: 0
differing bytes: 1679
diffs outside a patched field: 0   <- clean
```

Every patch declared what it expected, was validated against the **source** disc before anything
was written, was bounds-checked against the `TABLES.VPP` region, was re-read after writing, and the
whole 1.2 GB image was then diffed to prove **nothing outside a deliberately patched field moved**.

**Boot** (`F:\rando\S1\notes\pcsx2_headless_boot.ps1`, 90 seconds):

```
test-doors.iso   PASS   cpu=28.5s/90s   rss=879MB   thr=17   CRC 13E2774E   err: none new
[    3.3091]   Serial: SLUS-20074
[   17.9135]   ELF cdrom0:\SLUS_200.74;1 with entry point at 0x00100008 is executing.
```

**The CRC tell.** `13E2774E` — identical to vanilla, and identical to the 15,235-edit randomizer
build. Correct: the executable was never touched. The CRC moves **if and only if** a byte of
`SLUS_200.74` changes (the `endgame_gate` disc reads `13E2775E`). So the CRC column is an
independent, emulator-supplied confirmation that our edits land in the data layer exactly where we
believe they do, and nowhere else.

Artifact: `F:\rando\S1\out\test-doors.iso`. Source disc and `parts\` untouched.

---

## 4. What this settles, and what it does not

**Settled:**

- Doors are data, not code. The text layer is the right layer.
- The 218-patch rewrite is structurally sound: size-preserving, refuse-on-mismatch, zero
  collateral, fully reversible.
- A door-remapped disc is a **valid, bootable** image.

**Not settled ("boot-verified is not play-verified"):**

1. **No door has been walked through.** With no pad input in headless emulation, nothing has
   observed a remapped door actually leading somewhere new.
2. **The `+Index:` caveat is untested.** A player-start index that does not exist at the
   destination makes `level_script_set_player_starts` hard-loop. From outside that looks like a
   perfectly healthy running game. It would pass this boot test and still be broken.
3. **Reachability is unchecked.** Nothing here decides whether a remapped destination is a sane
   place to land — or whether the resulting level graph is completable.

---

## 4.5 IN-GAME VERIFICATION — 2026-09-21, the first walked-through door was not walked through by a player

**Boot-verified became play-verified today, without a pad and without a screen.** Three things
made it possible; the first is the one that cost the most.

### The renderer trap (read this before trusting any PASS)

With the default renderer (Automatic → Vulkan) the GS device dies in Session 0 every ~30 s:

```
[118.4] (SubmitCommandBuffer) vkQueueSubmit failed:  (-4: VK_ERROR_DEVICE_LOST)
[119.4] OSD [GSDeviceLost]: Host GPU device encountered an error and was recovered.
```

PCSX2 recovers and the boot test still prints **PASS** - but the **game freezes**. It is invisible
from outside unless you look at memory: a 32 MB churn scan 2 s apart showed **2** blocks changing.
With `Renderer = 13` (Software) the same scan shows **~25**, and the game plays. Everything below
was done on the Software renderer. *PASS is not running.*

### The rig

| Piece | What it does |
|---|---|
| `EmuCore/EnablePINE = true` | PINE opens 127.0.0.1:28011; `F:\rando\S1\notes\pine.py` reads/writes EE RAM, batched, plus savestate save/load |
| `cheats/13E2774E.pnach` | test-only scaffolding - see below |
| `EmuCore/EnableCheats = true` | loads that pnach (an **unlabelled** group is auto-enabled) |
| `watch_state.py` / `churn_scan.py` | level name + trigger count + whole-RAM churn: is the game alive? |

**The pnach does three test-only things** (none of them a gameplay change, all reversible by
deleting the file):

1. **Autoplay** - `ngps_input_button_pressed` (0x11AAC0) and `ngps_input_button_just_pressed`
   (0x11AB30) become `return 1`, so the frontend walks itself into gameplay in ~20 s.
2. **Door gates** - `crossing_test` (0x0017EC18) and `inside_mesh` (0x00202338) bump a counter in
   unused RAM at `0x01A00000`/`+4` and return 1. The counters prove the door check really runs
   (`level_script_check_level_load` reached the spline branch ~2.6 times/s in `masad`).
3. **Load arm** - `level_script_do_frame` (0x00203424) requires a pending destination (`uGpffffb218`)
   *and* an "armed" flag (`uGpffffb224`) before it loads. The nop there drops the arm test.

### The result

With that harness, `Level_data.name` (`0x01245410`) is a live read-out of what the game decided
to load. One named door was rewritten per disc, in `TABLES.VPP`, size-preserving, read-back
verified (`make_door_test_iso.py`):

| Disc | masad's door says | what the game loaded |
|---|---|---|
| `Summoner.iso` (vanilla) | `worldmap1` | did not fire on its own - that door is *scripted* (`flags & 2`) |
| vanilla + the flag bit cleared by hand | `worldmap1` | **`worldmap1`**, script `worldmap1`, start id 2 |
| `test-door1-catacombs.iso` | `catacombs` | **`catacombs`**, script `catacombs` |
| `test-door1-Lenele1aa.iso` | `Lenele1aa` | **`Lenele1aa`**, script `lenele1aa` |

Two discs that differ **only** in the rewritten destination string load two different levels. That
is the randomizer's headline mechanism, observed inside the running game.

**And it holds when stacked with another feature.** On 2026-09-21 a build combining the full
218-door remap with the enemy pass was verified the same way: `masad`'s door — `worldmap1` in
vanilla, rewritten to `lenele1e` — loads **`lenele1e`**, and the chain carries on through `sewer`,
`lenele3d`, `lenele2d`, `Liangshan`. Changed bytes: 13,880 of 1.23 GB, **0 outside** the archive.
See `ENEMIES.md` §4 for the entity-count control that goes with it.

### What this proves, and what it still does not

**Proves:**

- the destination is the trigger's `$Trigger:` **name**, and rewriting it in `TABLES.VPP` redirects
  the door - the game then loads `<name>.s3d` / `<name>.p3d` / `<name>_script.tbl` and the level's
  own script (`Level_data.script` resolves from the new name, not the old one)
- the load chain `record -> pending globals -> level_script_do_frame -> os_load_busy_ngps` works
  exactly as the static analysis said, and `_script.tbl` follows the name
- a level can be changed while the game is running, with the game's own loader - no binary patch

**Does not prove:**

1. **The geometry is still forced.** The crossing/inside gates return 1 unconditionally; a real
   player walking is still unproven. We now have the exact code (`door-check-decomp.c`,
   `door-helpers-decomp.c`) and the live data (`worldmap1`'s door is the segment
   `(-191.857, 104.794, 83.461) -> (-197.781, 104.794, 101.637)` via `*(*(rec+0x5C)+8)`, which is
   *not* in the same coordinate range as the player) - so the next step is to satisfy that test
   honestly rather than force it.
2. **The `+Index:` caveat** (`level_script_set_player_starts` hard-loops if the start id does not
   exist) is still untested.
3. **Reachability** is unchecked - these loads fire because the gates are forced, not because a
   route exists.
4. `masad`'s own door is a **scripted** one (`flags & 2`): it runs `level_script_do_clicked`
   instead of loading directly. Whether an arbitrary remap lands on a scripted or a plain door is
   a per-door property the mapper must respect.

### How to reproduce

```powershell
# 1. build a one-door test disc (source disc is never opened for write)
python F:\rando\S1\notes\make_door_test_iso.py catacombs Masad

# 2. boot it headlessly with the harness pnach in place
$env:QT_QPA_PLATFORM='windows'
Start-Process 'C:\Program Files\PCSX2\pcsx2-qt.exe' -ArgumentList '-batch','-fastboot','F:\rando\S1\out\test-door1-catacombs.iso'

# 3. watch what the game loads (Level_data.name, trigger count, is RAM alive)
python F:\rando\S1\notes\watch_state.py 120 5
```

## 5. The next thing: observation, then a guard

### Observation — CDVD file-read logging

The cheapest way to *see* a level transition with no screen: a load of a new level shows up as
disc reads. Log CDVD activity through the emulator and a door crossing becomes observable.
Runners-up, in order, are in `PROJECT.md` §6 step 5: a **test-only patch that forces a level load
at boot** (deterministic, no input needed), **PCSX2 pnach** memory writes, then input injection via
`PostMessage` (weaker than it looks — SDL reads async keyboard state, so only event-polling
bindings would see it).

### Guard — a flood-fill plus an honest constraint list

The genre-wide design, catalogued in `RESEARCH-ENTRANCE-LOGIC.md`: exits onto entrances, a graph, a
reachability flood-fill, retry until completable. Our starting constraints are recorded there
(never into the endgame; no one-way traps; a hub always reachable; account for the seven anchored
rings; expect a hand-kept quirks list, because OoT needed one per dungeon).

---

## 6. Implementation plan

### 6.1 `binary.py` needs a sibling patch type

`binary.py`'s registry is **ELF, one 4-byte word at one virtual address** (`Patch`: `va`,
`original`, `encode`). The door patch is an **arbitrary byte range inside `TABLES.VPP`**, which is a
different class of edit. It does not drop in verbatim. The sibling must carry the same two
non-negotiables:

1. **Declare and refuse.** Each entry states the exact bytes it expects to find; a mismatch aborts
   the whole build rather than writing anything.
2. **Read back.** Every entry is re-read and compared after writing.

Plus two of its own: **bounds-check every range against the archive region** (the door applier
already does this: `TABLES_OFF <= off and off + len <= TABLES_OFF + TABLES_LEN`), and **prove a
clean whole-image diff** — changed bytes must be a subset of the fields we declared.

`apply_door_remap.py` is the reference implementation of that discipline, written as a standalone
script. Folding it into `rando_core.py` as a real transform — with the seed driving the mapping —
is the work item.

> **CLOSED 2026-09-21 — and the sibling turned out not to be needed.** The transform exists:
> `door_destination_remap` in `rando_core.py`, mode `door_remap`, all 218 doors found by parsing
> the stream, constraints enforced and refused, the discipline carried inside the transform
> (declare-and-refuse, read back, bounds check, and a whole-stream diff that must contain nothing
> outside the declared fields). No `DATA_PATCHES` class was added: the engine already writes each
> entry's slice back to its own ISO range, so a door is an ordinary transform on the reassembled
> blob. Folding it in also uncovered the reason the lab had to work outside the engine — the
> archive's data area starts at the next `0x800` boundary after the TOC (`0x9000` for 527
> entries), not at a fixed `0x1000`, and entries are `0x800`-aligned. See `FEATURES.md` §0.

### 6.2 Then `--patch-only` output

Emit a small patch file instead of a 1.2 GB ISO copy. Two wins: seeds become tiny and shareable
**without distributing game data**, and the ~80 s build drops to seconds. `RESEARCH-SOTN.md` (PPF)
and `RESEARCH-ENTRANCE-LOGIC.md` §9.1 (PNACH) both have precedents.

### 6.3 And the design fork, which is still open

**Shuffle destinations** (what we just proved possible) changes the level graph: it can strand the
player and needs the reachability guard. **Shuffle contents / rooms** — Joshua's idea — leaves the
graph intact, so unreachable regions become *impossible by construction*, and it may need no binary
work at all. The full three-variant ranking is in `PROJECT.md` §6 and
`RESEARCH-ENTRANCE-LOGIC.md` §2.

The cost of doors went away; the risk did not. **Room Shuffle stays the safe default; Door Shuffle
becomes a real, opt-in mode with the guard** — not a `No Logic` stunt.

---

## 7. Files

| File | What |
|---|---|
| `F:\rando\S1\notes\door-mechanism.md` | the full mechanism write-up (records, parser, inventory, patch strategies evaluated) |
| `F:\rando\S1\notes\door-triggers.json` | all 218 `+Id: "load level"` triggers with ISO offsets, source level, index, type, spline/navpoint, radius, script |
| `F:\rando\S1\notes\door-remap-example.json` | the 218 concrete patches used for this proof |
| `F:\rando\S1\notes\apply_door_remap.py` | the applier: refuse-on-mismatch, read-back, size check, whole-image diff |
| `F:\rando\S1\notes\verify_doors.py` | independent verification of the mechanism claims against the disc (read-only) |
| `F:\rando\S1\notes\_remapgen*.py` | remap generation scratch scripts |
| `F:\rando\S1\out\test-doors.iso` | the boot-verified, door-remapped artifact |

No game data is distributed, hosted, mirrored or linked by any of this. Patches and seeds only.
