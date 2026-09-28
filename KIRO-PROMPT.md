# KIRO PROMPT — Summoner Randomizer handoff

Paste-ready brief for Kiro (or any fresh agent) picking this project up. Written 2026-09-28 by Jeni,
the assistant that has been doing this work on the N100 host. **Read it top to bottom before typing
anything.** Everything below is measured, not recalled — the measurements are in the repo.

---

## 1. What you are picking up

A **randomizer for Summoner** (PS2, Volition/THQ, 2000, `SLUS-20074`) and later **Summoner 2**
(`SLUS20448`). Self-contained desktop app: user supplies their own disc, it writes a new playable
ISO, the seed is shown.

**Nobody has done this before.** Summoner has had essentially no modding scene in 25 years; the only
community tool for the PS2 release is a widescreen patch. Every mechanism here was reverse-engineered
from the disc. Do not assume a known answer exists.

The repo you are in is the app. Worked-out facts live in the documents, and those documents are the
deliverable as much as the code is.

---

## 2. Read these first, in this order

| # | File | Why |
|---|---|---|
| 1 | `PROJECT.md` | the whole project: status, findings, app, modes, roadmap, verification, rules |
| 2 | `RESUME.md` | the one-screen state + the next action. **Corrected 2026-09-28** — older copies were a week stale |
| 3 | `FEATURES.md` §0 | where the features actually live, and the archive-layout bug that moved every count |
| 4 | `PLANNED.md` | the to-be-implemented log: state, mechanism, acceptance for every decided-but-unbuilt item |
| 5 | `MODES.md` | every mode and option, with measured edit counts |
| 6 | `DOOR-REMAP.md` | the door mechanism, the patch format, the 218-patch proof, what is still unproven |
| 7 | `COMPILED-CODE.md` | Ghidra/R5900 toolchain, the portal mechanism, the binary patcher, the headless harness |
| 8 | `RESEARCH-ENTRANCE-LOGIC.md` | how doors are solved genre-wide: logic tiers, constraints, mode taxonomy |
| 9 | `TIMER-DESIGN.md` | timed runs (deferred by request; design recorded so it is not re-derived) |

Then, on the data drive: `F:\rando\S1\notes\pcsx2-headless-FINDINGS.md` (the full headless
write-up, dead ends included) and `F:\rando\S1\notes\door-mechanism.md` (the instruction-level door
analysis).

**Do not re-derive the toolchain, the headless recipe, or the door mechanism.** It is all written
down, and re-deriving it has already cost days. If a doc contradicts what you observe, the
observation wins — and then fix the doc in the same commit.

---

## 3. Hard rules

- **No game data is distributed, hosted, mirrored or linked. Ever.** Seeds and patches only. There
  is a guard: `python tools/check-no-game-data.py` must print clean before every push. Run it.
- **Never wipe** the verified ISOs or the parts folders (`F:\rando\S1\iso\parts`, `F:\rando\S2\...`).
- `F:\rando\S1\iso\` and `F:\rando\S2\iso\` are **read-only**. Test builds go to `F:\rando\S1\out\`.
- **Every transform is size-preserving.** The 527 `TABLES.VPP` entries are arbitrary slices of one
  6,771,975-byte stream, 424 of 526 boundaries cut mid-line. Values are swapped only between
  equal-width fields; names only with same-length strings. Boundaries must not move.
- **Declare and refuse.** Any binary patch states the exact bytes it expects and aborts the whole
  build on mismatch, then reads back. The `0x1F6608` vs `0x1F6614` mix-up is the cautionary tale:
  a wrong address corrupts a live call. `binary.py` enforces this — do not bypass it.
- **Unimplemented features are documented as blocked, with a reason. Never half-shipped.**
- **Boot-verified is not play-verified.** Always say which one a claim is.
- Never commit an ISO, a blob, a BIOS, or a screenshot of game text. `work/` is gitignored; that is
  where probes belong.

---

## 4. Environment

Engine: `cli.py` (JSON in / JSON out) over `rando_core.py` (33 transforms, 25 modes) and
`binary.py` (patches the executable). Desktop app: `desktop\Run.cmd`. Legacy web UI: `_legacy-web-ui\`.

> **From a PowerShell/exec shell, add `-q` to every `cli.py` call.** The engine writes progress to
> stderr by design (the GUI reads it), and PowerShell 5.1 reports each stderr line as a failed
> command, so a **successful** build shows up as "Exec failed". `-q` keeps progress in `--log` only.
> **The exit code and the artifact are the truth; that banner is not.** The same trap applies to
> `git push`, which prints its progress on stderr and "exits 1" while succeeding.

```powershell
# build a randomised disc
python cli.py --build "F:\rando\S1\iso\Summoner.iso" --transforms <name> --seed <SEED> `
       --out "F:\rando\S1\out\Summoner-<name>-<SEED>.iso" -q --report out.json

# the catalogue, from the terminal
python build.py --list

# boot a disc headlessly: PASS / PARTIAL / FAIL
powershell -File F:\rando\S1\notes\pcsx2_headless_boot.ps1 -Iso "<path>.iso" -Seconds 75

# is it actually RUNNING? (PASS does not mean this)
python F:\rando\S1\notes\churn_scan.py 2

# live game state: level name, script, trigger count, churn
python F:\rando\S1\notes\watch_state.py 120 5

# live memory through PINE:  python pine.py r32 0x1238B78 25 | pine.py str 0x1245410 32 | pine.py save 9
python F:\rando\S1\notes\pine.py status
```

**The four facts that cost the most to learn** (full detail in `RESUME.md` and
`pcsx2-headless-FINDINGS.md`):

1. **`SettingsVersion` in `PCSX2.ini` must be `1`.** Any other value makes PCSX2 pop a modal dialog
   and wait forever for a click. Headlessly that looks exactly like a hang, and **no log is written
   at all**, which sends you hunting in entirely the wrong place.
2. **`Renderer` must be `13` (Software)** for anything past boot. With Vulkan the GS device dies in
   Session 0 every ~30 s and the *game* freezes while the boot test still says PASS. **PASS is not
   running** — check with `churn_scan.py`.
3. The `[Filenames] BIOS` entry must be a **bare filename**, not a path: an absolute path is
   rejected and PCSX2 silently falls back to a random Japan dump.
4. `QT_QPA_PLATFORM=windows` plus `pcsx2-qt.exe -batch -fastboot <iso>` is the working invocation.
   The dead ends are written down — `offscreen`, `WinSta0` attachment, `-nogui`, absolute BIOS
   paths — so that none of them get retried.

Active BIOS on this host: **`ps2-0200a-20040614.bin`** (v2.00 USA, SCPH-70012). PCSX2 2.8.1, PINE
enabled. Client: `F:\rando\S1\notes\pine.py` — one client at a time; kill leftovers before connecting.

---

## 5. Where the project actually stands

Verified facts. Do not take these on faith; they are each reproducible from the repo.

| | State |
|---|---|
| Both retail discs | dumped, hash-verified, and rebuilt byte-identical from parts |
| Summoner 1 | **editable** — VPP v1 decoded, full pipeline working |
| Summoner 2 | **detected, not editable** — VPP v2 header read (`count` at `+0x3C`, `size` at `+0x40`, 28-byte TOC records, filename table readable); the reader is **not written** |
| Text layer | 33 transforms, 25 modes, size-preserving, reversible |
| Binary layer | built and proven — patches `SLUS_200.74` in the ISO, verified to the byte, emulator agrees (CRC changes) |
| Doors | **solved** — a door is the `$Trigger:` name in the level's own table; 218-patch remap applied clean, disc boots |
| Door remap in game | **verified 2026-09-21** — two discs differing only in one rewritten name load two different levels, read off the live game |
| Door remap in the engine | **done** — transform `door_destination_remap`, mode `door_remap`; constraints enforced and refused; no `DATA_PATCHES` class was needed |
| Shipped since: | `enemies_amount`, `shops_free`, `shops_crazy`, `shops_none`, `chest_items` (the last is play-verified at the record level; the grant itself is unwatched) |
| In-game verification | **live** — headless PCSX2 reaches real gameplay, level name and triggers readable through PINE |

**Known fixture caveat, stated plainly:** `inventory.py` measures against
`F:\rando\S1\notes\_end_blob.bin`, which was built with the *old* archive-offset rule and holds the
pre-fix stream. It sees 1 of the 218 doors. **Every number in `FEATURES.md` comes from that fixture.**
When you measure something new, measure it against the real disc, and say which source you used.

---

## 6. The job queue

Tracked item-by-item in `PLANNED.md`. Work it in order; the acceptance criterion for each is written
there.

### 6.1 — FIRST: `player_stats_random` and `enemy_stats_random`

The owner's request, verbatim: *"Randomized enemy hp and stats. Randomized player stats."*

**Mechanism (already mapped, do not re-derive):** a creature's numbers live in one of the
`#Character Info` blocks. Hostile blocks are the enemy side; `$Team: "friendly"` blocks are the
playable party. Shuffle the numeric fields **between equal widths only**, within each side
separately. `enemy_difficulty` already *scales* hostile numbers — this **shuffles** them.

**Recon already done** (`work/_probe_stats.py`, read-only against the retail disc):

- **160 `#Character Info` blocks carry a `$Team:` — 80 friendly, 80 hostile** (78 `hostile`,
  1 `Hostile`, 1 `evil`). This agrees exactly with the engine's own `_hostile_char_blocks()`.
- **All ten numeric fields exist in all 160 blocks**, so a same-width shuffle is legal for both
  sides. Widths spread widely, which is what makes it interesting:
  - hostile `$Max Hit Points` — w2×11 / w3×58 / w4×11
  - friendly `$Max Hit Points` — w2×72 / w3×7 / w4×1
  - hostile `$Attack Radius` — w3 for all 80 (a free-for-all pool)
  - hostile `$Aggressiveness` — w2×55 / w3×25; friendly — w2×78 / w3×2
- **There is no Strength, Dexterity, Intelligence, Endurance, Armor or Weight anywhere.** "Player
  stats" here means HP, AP, aggressiveness, attack radius, field-of-view, detection, speedup and
  slowdown rates. The item is smaller than it sounds.
- **Unused headroom worth considering:** `$Teamwork`, `$Conservation`, `$Slow/Fast/Moving turn rate`,
  `$Experience Gained`, `$Skill`, `$Damage`, `+Resistances` all sit in those blocks and **no
  transform touches them yet**. Decide honestly which belong in a "stats" shuffle and which do not,
  and write the decision down.

**The fields the engine already knows about:** `CREATURE_NUM_FIELDS` and `CREATURE_FLOAT_FIELDS` in
`rando_core.py` (~line 1170). Reuse them; do not invent a second list.

**Acceptance:** stats move between creatures, widths preserved, no creature left holding a value its
field cannot express, both sides shuffled separately, edit count measured against the **disc**.

**Open decision, owner's call — ask before you pick.** *Pure shuffle* (a boss can end up with 15 HP)
or *shuffle-with-floor* (values move, but anything in the top width class stays in the top class)?
The assistant defaulted to pure, on the grounds that it is what "randomized" means and it is funnier;
the counter-argument is that a paper boss reads as a bug. Get an answer from the owner.

### 6.2 — `rooms_shuffle`

Permute `$Start position` anchors between placements of the same kind **within** a level. Doors,
quests, navpoints and the level graph never change, so unreachable regions are impossible by
construction. This is the safe half of the design fork in `RESEARCH-ENTRANCE-LOGIC.md` §2; the
deeper version (swapping a level's whole interior with another's) stays designed-not-built.

**Acceptance:** anchors permute within a level and never across levels; every destination anchor
still exists.

### 6.3 — `npc_hunt`, as a mode over two shipped transforms

`spawn_shuffle` + `npc_character_shuffle` stacked. Cross-level NPC relocation stays **designed**.

### 6.4 — Boss Rush

Needs a **boss inventory** first: the placements carrying `+Boss`, and the arena level's navpoint
list. The first version re-points every boss placement's `$Start position` at navpoints inside one
arena so they stand together. A true gauntlet rides on the level graph.

### 6.5 — Collectionthon — **blocked, with a reason**

The game has no collection counter. Two candidates: (a) rename an unused `+Event:` flag to
`ready_for_end` and set it at the last collection point — cheap, but it only checks one thing;
(b) patch the executable to gate the ending on a counter — the binary layer exists, the counter
does not. Do not guess at a third.

### 6.6 — The open in-game checks (owner is doing the testing — see §8)

- `PLANNED.md` §2.8 — **the honest door crossing**: the harness forces the geometry gates; the real
  crossing test has not been done.
- `PLANNED.md` §2.14 — **217 of the 218 doors have never been watched.**
- `PLANNED.md` §2.16 — `chest_items`, half done: the record is play-verified, the **grant** is not.
- `PLANNED.md` §2.9 — in-game checks for Swarm and the Difficulty dial.

### 6.7 — Second game

The **VPP v2 reader** for Summoner 2. Detection and the filename table are done; the reader is the
gap between "Summoner 2 too" on the box and reality. Nothing else about S2 is blocked on this.

---

## 7. Definition of done — the pattern every item follows

Every shipped item in this repo did all six. Match it.

1. **The transform** in `rando_core.py` — registered in the transform registry (~line 1980), the
   option spec written with a real `help` string, added to the dispatch table (~line 2240).
2. **A `Report`** — edits counted per field, notes for anything refused. Refusals are reported,
   never guessed at.
3. **The mode**, if the owner asked for one, in `MODES.md` — and its own option values merged
   through `rando_core.mode_options`, because a mode that uses a dial **must** set a value
   (three modes silently did nothing until this rule was written down, `FEATURES.md` §0).
4. **The measurement**, against the disc, added to `MODES.md` and `FEATURES.md`. Numbers, not "works".
5. **`PLANNED.md` updated** — the row struck if done, or re-stated with the new blocker.
6. **The commit.** Style is `lowercase: what changed, and why it is honest` — e.g.
   `chest_items: real chest randomisation, and the plan had the field wrong`. The docs go in the
   **same** commit as the code. Run `python tools/check-no-game-data.py` and `build.py --list`
   before committing.

---

## 8. Testing — who does what, for now

**The owner (Joshua) is doing the in-game testing himself for now.** Your job is to hand him
something testable and unambiguous. For every build that needs eyes on it, produce:

- the built ISO path (under `F:\rando\S1\out\`), the exact seed, and the exact `cli.py` invocation,
- **what to look at and what "correct" looks like** — one sentence per check, not a wall,
- **what a failure would look like**, so he is not guessing whether he is seeing a bug,
- the honest label: *boot-verified* or *play-verified*, and which checks are neither.

Do not claim a feature works because the build succeeded. That distinction is the whole reason this
project's documents are trustworthy.

---

## 9. What is deliberately not here

- No game data, no ISO, no blob, no BIOS in the repo. The 527-entry archive is one stream; the piece
  you need is extracted at runtime from the user's own disc.
- `--patch-only` output (emit a small patch instead of a 1.2 GB ISO copy) — designed in
  `DOOR-REMAP.md` §6.2, not built. It would make seeds tiny and shareable without distributing game
  data, and would drop the ~80 s build to seconds.
- The reachability guard for door destinations — `DOOR-REMAP.md` §5, `RESEARCH-ENTRANCE-LOGIC.md`.
  **Doors are cheap now; the risk did not go away with the cost.**

If something here contradicts what you observe, **the observation wins — and fix this file too.**
