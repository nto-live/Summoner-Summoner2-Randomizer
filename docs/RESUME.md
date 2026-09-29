# RESUME — Summoner Randomizer

## 🔑 CODEWORD: `SUMMON`

Say **`SUMMON`** — on its own, or as "codeword SUMMON", "pick up SUMMON", "resume SUMMON" —
and we resume this project immediately, with no re-explaining.

**What I do when I hear it:**

1. Read this file.
2. Read `PROJECT.md` (§2 status, §6 roadmap, §7 verification) and `MODES.md`.
3. Read `COMPILED-CODE.md` §7–8 (the binary patcher and the headless harness).
4. Read `DOOR-REMAP.md` — the door mechanism, the patch format, the proof, and what is still unproven.
5. Report: where we are, what is next, and any blocker — then get back to work.

**Variants that also work:** `SUMMON status` (report only, no work) · `SUMMON doors` (jump
straight to the doors workstream) · `SUMMON docs` (re-read and update the documents).

**Do not** ask me to re-derive the toolchain, the headless recipe, or the door mechanism —
it is all written down, and re-deriving it has already cost days.

---

## Where we are, in one screen

| | |
|---|---|
| **The product** | a desktop app. ISO in, randomized ISO out, seed shown. No server. |
| **App** | `tools\summoner-rando\` — `desktop\Run.cmd` to launch |
| **Engine** | `cli.py` (JSON in / JSON out). `rando_core.py` (33 transforms, 25 modes). `binary.py` (patches the executable). |
| **Text layer** | done — 33 transforms, 25 modes, size-preserving |
| **Binary layer** | **built and proven** — first patch verified to a single byte, and the emulator agrees (CRC changes) |
| **In-game verification** | **LIVE. It plays.** Headless PCSX2 reaches real gameplay (level `masad`, triggers parsed, player entity walking) - needs `Renderer = 13` (Software); Vulkan silently freezes the game. `COMPILED-CODE.md` §8. |
| **Doors** | **SOLVED** — mechanism found, 218-patch remap built, applied clean, disc **boots** |
| **Door remap in game** | **VERIFIED 2026-09-21** — two discs differing only in one rewritten `$Trigger:` name load two different levels, read straight off the live game. `DOOR-REMAP.md` §4.5 |
| **Door remap in the engine** | **DONE** — `door_destination_remap` is a real seed-driven transform, mode `door_remap`, constraints enforced and refused. No `DATA_PATCHES` class was needed |
| **Active work** | **the reachability guard** — a flag graph + solver, the gate on the highest-risk feature (`door_remap` changes the level graph and nothing yet checks the world stays completable). The two stat items ARE built. Verification tiers every claim must reach: `docs/TEST-PLAN.md`. |
| **Owner's directive** | *"Iterate on this until you get a patched working copy. First feature is the doors."* |

## The next action, specifically

**Two things, in this order.**

**1. `player_stats_random` / `enemy_stats_random`** (`PLANNED.md` §1.4) — shuffle the numeric
fields inside `#Character Info` blocks: hostile blocks for the enemy side, `$Team: "friendly"`
blocks for the party. Equal widths only. `enemy_difficulty` already *scales* hostile numbers;
this *shuffles* them. Recon is done (`work/_probe_stats.py`): 160 blocks carry a `$Team:` —
80 friendly, 80 hostile (78 `hostile` + 1 `Hostile` + 1 `evil`, matching `_hostile_char_blocks`).
All ten numeric fields are present in all 160 blocks, with wide width spreads, so a same-width
shuffle is legal — e.g. hostile `$Max Hit Points` splits w2×11 / w3×58 / w4×11, hostile
`$Attack Radius` is w3 for all 80. Also present and unused by any transform yet: `$Teamwork`,
`$Conservation`, `$Slow/Fast/Moving turn rate`, `$Experience Gained`, `$Skill`, `$Damage`,
`+Resistances`. There is **no** Strength/Dexterity/Intelligence — "player stats" here means
HP / AP / aggressiveness / ranges / turn rates.

**2. `rooms_shuffle`** (`PLANNED.md` §1.5) — permute `$Start position` anchors between
placements of the same kind *within* a level; the level graph, doors and quests never change.

**3. Then** Boss Rush (needs a boss inventory), Collectionthon (blocked on a completion
mechanism), and the open in-game checks — `PLANNED.md` §2.8 (the honest door crossing),
§2.14 (217 of the 218 doors have never been watched), §2.16 (the `chest_items` grant).

Then the test plan in `FEATURES.md` §8 runs down the whole catalogue.

> **Doc note (2026-09-28):** this section was stale for a week — it still said the headline
door feature was unbuilt when `door_destination_remap` had already landed (`DOOR-REMAP.md` §6.1,
`PLANNED.md` §2.1/§2.2). Items 1–3 above are the corrected queue.

Also still open from before:

- **`DATA_PATCHES` sibling in `binary.py`** — an arbitrary byte-range patch class for `TABLES.VPP`,
  carrying the same declare-and-refuse + read-back discipline. Design in `DOOR-REMAP.md` §6.1;
  `F:\rando\S1\notes\apply_door_remap.py` is the reference implementation.
- **Room Shuffle** — the safe default (content, not destinations); see `PROJECT.md` §6.

Doors are cheap now. **The risk did not go away with the cost** — destination rewrites still need
the reachability guard (`RESEARCH-ENTRANCE-LOGIC.md` §2, §4).

## The commands that matter

> **From a PowerShell/exec shell, add `-q` to every `cli.py` call.** The engine writes progress to
> stderr by design (the GUI reads it), and PowerShell 5.1 reports each stderr line as a failed
> command, so a successful build shows up as "Exec failed". `-q` keeps progress in `--log` only.
> The exit code and the artifact are the truth; that banner is not.

```powershell
# boot a disc headlessly, print PASS/PARTIAL/FAIL
powershell -File F:\rando\S1\notes\pcsx2_headless_boot.ps1 -Iso "<path>.iso" -Seconds 75

# is it actually RUNNING? (PASS does not mean this)
python F:\rando\S1\notes\churn_scan.py 2

# live game state: level name, script, trigger count, churn
python F:\rando\S1\notes\watch_state.py 120 5

# live memory: pointers, positions, the trigger record
python F:\rando\S1\notes\probe_live.py ptr
python F:\rando\S1\notes\pine.py r32 0x1238B78 25
python F:\rando\S1\notes\pine.py str 0x1245410 32

# build a one-door test disc (copy + one in-place field rewrite, read back)
python F:\rando\S1\notes\make_door_test_iso.py catacombs Masad

# fire a live door by hand: clear the record's "run script" flag and watch the load
python F:\rando\S1\notes\force_door.py [newname]

# savestate through PINE (the deterministic baseline)
python F:\rando\S1\notes\pine.py save 9

# the iteration rig: build -> whole-image byte diff -> boot -> one verdict
powershell -File F:\rando\S1\notes\iterate.ps1 -Mode endgame_gate -Seed ITER1

# apply the 218 example door patches + prove size/diff cleanliness (source disc stays read-only)
python F:\rando\S1\notes\apply_door_remap.py

# independent verification of the mechanism claims against the disc (read-only)
python F:\rando\S1\notes\verify_doors.py
```

## The four facts that cost the most to learn

1. **`SettingsVersion` in `PCSX2.ini` must be `1`.** Any other value makes PCSX2 show a modal
   dialog and wait forever for a click. Headlessly that looks exactly like a hang, and **no log
   is written at all**, which sends you hunting in entirely the wrong place. Working
   invocation: `$env:QT_QPA_PLATFORM='windows'; pcsx2-qt.exe -batch -fastboot <iso>`.
1b. **`Renderer` must be `13` (Software)** for anything past boot. With Vulkan (the default) the
   GS device dies in Session 0 every ~30 s (`VK_ERROR_DEVICE_LOST` → recovered); PCSX2 survives
   and the boot test still says PASS, but the *game* freezes - 2 of 31 one-megabyte RAM blocks
   change over two seconds. On Software, ~25 do, and the game actually plays. **PASS is not
   running** - check with `churn_scan.py`.
2. **Every binary patch must declare what it expects and refuse on mismatch.** The
   `0x1F6608` vs `0x1F6614` mix-up is the cautionary tale — a wrong address corrupts a live
   call. `binary.py` enforces this; do not bypass it.
3. **The 527 `TABLES.VPP` entries are arbitrary slices of one stream.** Boundaries must not
   move. Every table-layer edit is length-neutral. Proven twice, by a `$F`+`og:` stitch and by
   a sentence split mid-word.

## Rules that are not negotiable

- **No game data is distributed, hosted, mirrored or linked.** Ever. Seeds and patches only.
- **Never wipe** the verified ISOs or parts folders (`F:\rando\S1\iso\parts`, `F:\rando\S2\...`).
- `F:\rando\S1\iso\` and `F:\rando\S2\iso\` are read-only. Test builds go to `F:\rando\S1\out\`.
- Table-layer edits stay **size-preserving** until the archive-slack question is resolved.
- Unimplemented features are documented as blocked **with a reason**, never half-shipped.
- **Boot-verified is not play-verified.** Say which one a claim is.

## Document map

| File | What is in it |
|---|---|
| `PROJECT.md` | the whole project: status, findings, app, modes, roadmap, verification, rules |
| `DOOR-REMAP.md` | **doors** — mechanism, patch format, the 218-patch proof, what is unproven, `DATA_PATCHES` design |
| `MODES.md` | every mode and option with measured edit counts |
| `COMPILED-CODE.md` | Ghidra/R5900 toolchain · the portal mechanism · **the binary patcher** · **the headless harness** |
| `RESEARCH-SOTN.md` | techniques taken from the SotN randomizer (PPF patch output, seed URLs) |
| `RESEARCH-ENTRANCE-LOGIC.md` | **how doors are solved genre-wide** — logic tiers, constraints, mode taxonomy, PNACH |
| `TIMER-DESIGN.md` | timed runs (deferred by request, design recorded) |
| `PLANNED.md` | **the to-be-implemented log**: state, mechanism and acceptance for every decided-but-unbuilt item |
| `TEST-PLAN.md` | **how a feature earns the right to be called done** — tiers T0–T4, suites A–F, the acceptance bar per class, and the defect list that prompted it |
| `FEATURES-REGISTER.md` | the catalogue **generated** from `cli.py --list`, so it cannot drift from the code (43 modes / 54 transforms / 4 binary patches) |
| `F:\rando\S1\notes\pcsx2-headless-FINDINGS.md` | the full headless write-up, including dead ends |
| `F:\rando\S1\notes\door-mechanism.md` | the doors analysis: trigger records, the `#Triggers` parser, 51-level inventory, patch strategies |
| `F:\rando\S1\notes\door-triggers.json` · `door-remap-example.json` | the 218 doors, and the 218 concrete patches |

## If something is unclear

Read the docs before re-investigating. The dead ends are written down too — `offscreen` Qt
platform, `WinSta0` attachment, `-nogui`, absolute BIOS paths — so that none of them get
retried. If a doc contradicts what you observe, **the observation wins, and fix the doc**.
