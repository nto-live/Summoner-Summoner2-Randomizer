# The burning-village fire barrier: what removes it, what gates it, and can the randomizer break it

Disassembly/data investigation only. No game or build was modified. All probes are read-only and
live under `docs/lab/`. Retail ISO measured: `C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso`.
ELF `SLUS_200.74` at ISO `0x11DBE000`, PT_LOAD vaddr `0x00100000` → file `0x1000` (via `binary.find_elf`).

Probes written for this analysis:
`probe_invisdoor.py`, `probe_masad_tutorial.py`, `probe_dispatcher.py`, `probe_flagsetters.py`,
`probe_masad_tables.py`, `probe_doorname_risk.py`.

## TL;DR for the end user

- The fire clears when the game removes an object literally named **`invis-door02`**.
- That removal is gated on the **dialogue** flag `masad_dialogue_tutorial_part2b`, which is set by the
  **conversation**, not by the tutorial code. That is why *talking to the guy* matters, and why it can
  take a few tries: you have to reach the conversation branch that sets the flag while the tutorial
  step is the active step.
- The multi-talk behaviour is **retail**. `skip_tutorial` v3 does not cause it and cannot fix it.
- **The randomizer's flag/tutorial handling is safe.** No transform touches the `+Flag` block or the
  tutorial flag names, and `door_destination_remap` cannot reach these records.
- **One real risk exists:** `door_name_shuffle` (in the *Door Shuffle* and *Everything* modes) can
  rename the `invis-door02` record, and the removal call in the executable uses a hardcoded string.
  If it is renamed, the fire may never clear. Details and fix options below.

## Q1 — What calls the removal, and from where

`invis-door02` is removed by a call to the object-removal function at `0x001DBF50`. The scan
(`probe_invisdoor.py`) found 10 call sites to `0x001DBF50` in the image; three of them are inside the
tutorial code (`ngps_tutorial.o`, `do_*` range `0x0023c868..`). The one that removes **invis-door02**
is:

```
0x0023cb6c  0C076FD4  jal 0x001dbf50            ; remove_object(...)   (ISO off 0x11efbb6c)
0x0023cb70  2484DCD0  addiu $a0, $a0, -0x2330   ; DELAY SLOT -> $a0 = 0x0127DCD0 = "invis-door02"
```

In MIPS the delay-slot instruction executes with the `jal`, so `$a0` is `"invis-door02"` for the call.
The `"invis-door02"` string lives at VA `0x0127dcd0` (ISO `0x12f3ccd0`); a second copy is at
`0x012715d0`.

**Containing function:** prologue `0x0023cad8` (`addiu $sp,$sp,-0xa0`), epilogue `jr $ra` at
`0x0023ccb8`. It sits between `do_basic_controls_tutorial` (`0x0023c868`) and
`do_basic_combat_tutorial_part1` (`0x0023ccc0`) in the `ngps_tutorial.o` symbol map — i.e. it is a
**`do_*` tutorial STEP function** (the dialogue-tutorial step handling `masad_dialogue_tutorial_part3`
/ `part2b`). It is **not** `ngps_process_tutorial` and **not** a level-script handler. The same
function also removes `invis-door03` at `0x0023cc04` and stops the fire VFX via
`sub_001b1be0("masad-firedoor1.vfx")` at `0x0023cc8c`. (`invis-door01` is removed by a sibling
combat step at `0x0023ce54`.)

## Q2 — What gates the removal (why talking matters)

Disassembly of the step function (`probe_masad_tutorial.py`), annotated:

```
0x0023caf0  addiu $s0,$v0,-0x2350   ; $s0 = "masad_dialogue_tutorial_part3"
0x0023cb14  jal   0x001f10a8        ; flag_is_set(part3)   <-- $a1 is the part3 name
0x0023cb1c  bne   $v0,$zero,0x23cc98; if part3 ALREADY set -> return (door already handled)
0x0023cb24  lui   $a2,0x128
0x0023cb2c  addiu $a2,$a2,-0x2370   ; $a2 = "masad_dialogue_tutorial_part2b"
0x0023cb30  jal   0x001f10a8        ; flag_is_set("masad_dialogue_tutorial_part2b")   <<< THE GATE
0x0023cb38  beq   $v0,$zero,0x23cb4c; if part2b NOT set -> 0x23cb4c
0x0023cb40  lw    $v1,0x684c($v0)   ; ($v0=0x1200000) secondary global condition
0x0023cb44  beq   $v1,$zero,0x23cb54; if that global == 0 -> proceed to removal
0x0023cb4c  beq   $zero,$zero,0x23cc98 ; else return
0x0023cb54  ...
0x0023cb5c  jal   0x001f11e8        ; flag_set("masad_dialogue_tutorial_part2b") (idempotent)
0x0023cb6c  jal   0x001dbf50        ; remove_object("invis-door02")   <<< FIRE CLEARS
0x0023cc04  jal   0x001dbf50        ; remove_object("invis-door03")
0x0023cc8c  jal   0x001b1be0        ; stop "masad-firedoor1.vfx"
```

So the fire is removed only when **`flag_is_set("masad_dialogue_tutorial_part2b")` is TRUE** (and a
secondary global at `0x0120684c` is zero, and `part3` is not yet set). `part2b` is a **dialogue
flag**, not a combat or controls flag.

**Who sets `part2b`?** `probe_flagsetters.py` scanned the whole code region for every pointer build
to the three dialogue-flag strings and classified the nearest following `jal`:

```
"masad_dialogue_tutorial_part2b" @ 0x127dc90
   build @ 0x0023ca4c -> next jal = flag_is_set
   build @ 0x0023cb2c -> next jal = flag_is_set     (the gate above)
```

Every code reference to `part2b` is a **check** (`flag_is_set`). The only `flag_set` on `part2b` is
the idempotent one at `0x0023cb5c`, which runs *after* the gate has already passed. So the executable
never originates that flag — it is set by the **dialogue/script layer** when you talk to the NPC.
`probe_masad_tables.py` confirms `part2b` appears in TABLES.VPP only inside the `+Flag:` declaration
block (blob `0x3B56F8`); the conversation data raises it on a dialogue branch.

That is the mechanism behind "talk 2–3 times": you must advance the conversation to the branch that
sets `masad_dialogue_tutorial_part2b`, while the dialogue-tutorial step is the active tutorial step,
before the step's gate fires and pulls `invis-door02`.

## Q3 — Retail vs `skip_tutorial` v3

Dispatcher `ngps_process_tutorial` (`0x0023d618..0x0023d780`, `probe_dispatcher.py`), the relevant tail:

```
0x0023d6c0  slti $v0,$s1,0x11        ; loop over the 17 tutorial steps (s1 = 0..0x10)
0x0023d6ac  jalr $v0                 ; call the active step fn indirectly
0x0023d6b4  bne  $v0,$zero,0x23d65c  ; a step returning nonzero re-runs the activate path
...
0x0023d6dc  beq  $v0,$zero,0x23d74c  ; no active tutorial -> skip advance
0x0023d6e8  jal  0x0011aac0 (btn 0xe); poll dismiss input
0x0023d72c  jal  0x0011aac0 (btn 0xc); poll dismiss input
0x0023d748  addiu $s0,$zero,0x1      ; s0 = 1  => "advance requested"
0x0023d74c  beq  $s0,$zero,0x23d760  ; <<< skip_tutorial v3 NOPs THIS
0x0023d754  jal  0x0023d5f0          ; advance the active tutorial step
0x0023d760  ... return
```

`$s0` is the advance flag; it is set only when the dismiss button is polled. `0x0023d74c beq $s0,zero`
skips the advance (`jal 0x0023d5f0`) when nothing was pressed. **v3 NOPs that branch**, so the
dispatcher advances the active *step* every frame with no input.

What v3 changes: only the **step-advance input-wait**. It does **not** set any flag, and specifically
it does not set the dialogue flag `masad_dialogue_tutorial_part2b` that gates the `invis-door02`
removal. The removal still depends entirely on the conversation setting `part2b`.

Therefore:

- The multi-talk requirement is **inherent to the retail game**. It is driven by conversation state
  (the `part2b` dialogue flag) plus the step being active, not by any patch. Retail does *not*
  guarantee the fire clears on the first "correct" talk — it clears on the frame where the step runs
  with `part2b` already set and the secondary global clear; if you talk before the step is active, or
  the branch that sets `part2b` has not been reached, nothing happens and you talk again.
- v3 does **not** make it require repeats, and it does **not** reliably clear the fire either. Because
  v3 auto-advances steps every frame, it can advance *past* the dialogue-tutorial step before the
  conversation has set `part2b`, so the gated removal is skipped — this matches the project memory's
  record that v3 "raced the scene" and dropped the fire only on a lucky run. `hide_tutorials`
  (which leaves the step logic and its flag-gated removal fully intact and only hides the popup draws)
  is the correct lever, and is play-verified to drop the firewall.

## Q4 — Does the randomizer disturb any of this?

Confirmed against `src/rando_core.py` and measured against the disc (`probe_masad_tables.py`,
`probe_doorname_risk.py`).

**The `+Flag` block and tutorial flag names — SAFE.**
There is no `+Flag` regex anywhere in the transforms. The masad opening declares its flags in one
`+Flag:` block (blob `0x3B567F..`): `masad_talked_to_nath`, `masad_intro`,
`masad_basic_controls_tutorial`, `masad_dialogue_tutorial_part1/2a/2b/3`,
`masad_basic_combat_tutorial_part1/2`, …. No transform reads or writes `+Flag:` values, so these
names never move.

**`door_destination_remap` — SAFE.**
It only rewrites `$Trigger:"…"` names whose block carries `+Id:"load level"`. `invis-door0N` never
appears as a `$Trigger` (0 hits); it is a `$Door:` object record. `rando_core._door_records()` parses
218 doors and finds 0 named `invis*`. The only masad-sourced `$Trigger` is `worldmap1`, and `masad`
/ `worldmap` / `worldmap1` are in `DOOR_SOURCE_EXCLUDE` and held anyway.

**Enemy / stat / xp / drop transforms — SAFE.**
`enemies_random` (`per_level`/`broad`/`global`), `enemies_amount`, `enemies_swarm`,
`enemy_stats_random`, `enemy_difficulty`, `enemy_hp_set`, `enemy_damage_set`, `enemy_xp_*`, drops,
etc. operate on `$Character` placements, `#Character Info` blocks, `+Drop`, `+AddXP`, `$Value`,
`+Level`, `$Start position` (`$npcNNN`→`$zzzNNN`). None of these patterns touch `$Door`, `+Flag`, or
the `invis-door` records.

**`door_name_shuffle` — THE ONE REAL RISK.**
Its regex is `\$Door:\s*"([^"]+)"`, and `invis-door02` exists in TABLES.VPP **only** as `$Door:`
records — twice, in `#Doors` blocks at blob `0x258288` and `0x25FD9E` — with no other definition of
the name. `door_name_shuffle` permutes `$Door` names within an equal-length class. The 12-character
class is:

```
len 12: 15 occurrences, 5 distinct -> {TannerDoor01, invis-door01, invis-door02, invis-door03, secretdoor01}
```

Five distinct names in the class means the shuffle **can rename `invis-door02`** to one of the others.
The executable's removal call passes the **hardcoded** string `"invis-door02"` (baked into the ELF at
`0x0127dcd0`), which the data layer cannot rename. So if the shuffle renames the level's door record,
`remove_object("invis-door02")` no longer matches it and **the barrier can persist**.

`door_name_shuffle` is included in modes **`door_shuffle`** and **`everything`**. It is not in the
enemy/xp/door-destination modes.

## Practical answer: will the fire clear for an end user?

- **Modes that do NOT include `door_name_shuffle`** (vanilla, all the enemy/xp/difficulty/chest/
  dialogue/audio/ring-hunt/door-destination modes): the fire behaves exactly as retail. If the player
  plays normally — talks to the NPC until the conversation sets `masad_dialogue_tutorial_part2b` — it
  clears. No randomizer-introduced risk. (The retail "talk a few times" quirk remains, unchanged.)

- **Modes that include `door_name_shuffle` (`door_shuffle`, `everything`)**: there is a genuine,
  seed-dependent risk that `invis-door02` gets renamed and the hardcoded removal call misses it,
  leaving the fire up permanently. This is a soft-lock of the opening on affected seeds. Whether a
  given seed trips it depends on the shuffle landing a different 12-char name on that record.

So: for most modes the fire clears reliably on normal play; for the two modes containing
`door_name_shuffle` there is a real reliability risk that scales with seed luck.

## Where to fix it (options, not applied)

The cause is precise: a hardcoded ELF string vs a data record the shuffle can rename. Fix at either end.

1. **Data-layer exclusion (smallest, safest).** In `t_door_name_shuffle`, exclude the tutorial door
   names from the shuffle pool — drop any `$Door` value matching `invis-door0\d` (and, to be safe,
   the sibling `masad-firedoor*.vfx` is a `.vfx` ref, not a `$Door`, so it is already out of scope).
   This keeps door-name chaos everywhere else while guaranteeing `invis-door01/02/03` keep their
   names, so the executable's removal always matches. One narrow filter; no new bytes; fully within
   the size-preserving rule.

2. **Binary belt-and-braces (covers any future data churn).** Ship a small binary patch that removes
   `invis-door02`/`03` unconditionally at the start of the dialogue-tutorial step, independent of the
   `part2b` gate — e.g. relax the gate so the removal runs once the step is active. This is more
   invasive and needs play-verification (the gate also guards `flag_set` bookkeeping), so option 1 is
   the recommended first move.

3. **Leave tutorials ON + prefer `hide_tutorials`.** Unrelated to the shuffle risk, but worth stating:
   `hide_tutorials` keeps every step's flag-gated removal intact and only suppresses the popup draws,
   so it does not disturb the fire logic at all. Avoid `skip_tutorial` v3 for this scene (it can
   auto-advance past the dialogue-tutorial step before the conversation sets `part2b`).

Recommendation: apply option 1 (exclude `invis-door0\d` from `door_name_shuffle`), and keep steering
users to `hide_tutorials` over `skip_tutorial`. That removes the only randomizer-introduced way the
fire fails to clear, and leaves the retail talk-to-the-NPC flow untouched.

## Evidence index (addresses / offsets)

| Fact | Address / offset | Source |
|---|---|---|
| `remove_object("invis-door02")` call | `jal 0x001dbf50` @ `0x0023cb6c`, ISO `0x11efbb6c`; delay slot `0x0023cb70` sets `$a0="invis-door02"` | probe_masad_tutorial.py |
| `"invis-door02"` string (used by call) | VA `0x0127dcd0`, ISO `0x12f3ccd0` (2nd copy `0x012715d0`) | probe_invisdoor.py |
| Containing step fn | prologue `0x0023cad8`, epilogue `jr $ra` `0x0023ccb8` | probe_masad_tutorial.py |
| Gate on removal | `flag_is_set("masad_dialogue_tutorial_part2b")` @ `0x0023cb30`; `beq` @ `0x0023cb38`; secondary `lw 0x684c($v0)` @ `0x0023cb40` | probe_masad_tutorial.py |
| `part2b` only ever checked in code | builds @ `0x0023ca4c`, `0x0023cb2c` both → `flag_is_set` | probe_flagsetters.py |
| `part2b` set by data | `+Flag:` decl only, blob `0x3B56F8` | probe_masad_tables.py |
| Dispatcher advance gate (v3 target) | `beq $s0,$zero` @ `0x0023d74c`; advance `jal 0x0023d5f0` @ `0x0023d754` | probe_dispatcher.py |
| `invis-door0N` are `$Door:` records | blob `0x258288`, `0x25FD9E` (and 01/03 adjacent) | probe_masad_tables.py |
| Door-remap scope excludes these | 0 `invis` doors of 218; masad `$Trigger` = `worldmap1`, in `DOOR_SOURCE_EXCLUDE` | probe_masad_tables.py |
| `door_name_shuffle` can rename it | 12-char class = {TannerDoor01, invis-door01/02/03, secretdoor01}, 5 distinct | probe_doorname_risk.py |
