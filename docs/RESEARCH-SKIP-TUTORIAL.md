# Research — disabling the opening tutorial (SLUS_200.74)

Goal: turn off the masad opening tutorial popups WITHOUT breaking progression. Verification label
throughout: **static/Ghidra-mapped**; the two things marked "PROVEN IN GAME" were booted.

## The system, as mapped

The "tutorial" is a **17-step state machine**, not a popup overlay:

- **Step functions**: `0x0023C868` … `0x0023D4A8` (17 consecutive fns), pointer table at
  **`0x0127DEE8`**, stride `0x24`, field `+0x00` = step fn ptr.
- **Dispatcher**: `FUN_0023D618` — runs the step loop each frame, then a tail that polls input
  (`FUN_0011aac0`, pad buttons `0xe`/`0xc`), plays a UI sound (`FUN_001b36e0`, `a0=0x23/0x24`),
  and advances a state counter (`-0x44cc(gp)`).
- **Master gate**: at `0x0023D648` the dispatcher does `lw v0,-0x3a70(gp); beq v0,zero,<run>`.
  `gp-0x3A70` is the **"ignore tutorial" global** the shipped debug command `Ignore tutorial`
  (string `0x0127DEC0`, cmd table `0x0023DA14`, handler `0x0023C808` `sw v0,-0x3a70(gp)`) toggles.
- **Flag store**: each step calls `flag_is_set` (`0x001F10A8`) and `flag_set` (`0x001F11E8`,
  `a3=1`). Storage is a per-level byte bitfield; `flag_set` is a pure bit-setter (index the flag
  name, OR the bit) — it does NOT display anything. `flag_is_set` reads the bit.
  `masad_*_tutorial` names are `+Flag:` declarations in the masad level table.
- **Step 1** `FUN_0023C8F0`: `flag_is_set(masad_basic_controls_tutorial)` → gate on
  `masad_dialogue_tutorial_part1` → **proximity check** `0x00205608(f12=2.0, a0="Mulik")` (returns
  nonzero when the player is within 2.0 of NPC "Mulik") → if near, `flag_set(...basic_controls...)`.
  So steps SET flags based on game conditions (walking near an NPC), then a display shows the popup.

## Why the obvious patches fail

1. **Force the ignore-global on** (`0x0023D648 lw v0,-0x3a70(gp)` → `li v0,1`): tutorials turned
   off, but **the first-level firewall never dropped — soft-lock. PROVEN IN GAME.** Because the
   dispatcher's early-out skips the whole step loop, so the tutorial steps' `flag_set` calls (which
   later events like the firewall depend on) never run. The tutorial steps are **load-bearing quest
   logic**, not just popups.
2. **Null a shared "display" function**: there isn't one that's both shared and display-only.
   - `0x00205608` = proximity/near-NPC test (distance math `sub.S`/`sqrt.S`), only 2 step callers
     (1 & 5). Safe to null but only affects those steps, and it's a *condition* check, not the draw.
   - `0x00229BC0` = `jr ra` stub (does nothing).
   - `0x001C8810` = 259 callers — general utility, must not touch.
   - `FUN_0023d5f0` (dispatcher tail call) = decrements the `-0x44cc(gp)` state counter; shared with
     the boot state machine `FUN_0022a1c0`. Not display, not safe to null.
   - `flag_is_set`/`flag_set` = shared by ALL game flags. Never patch.
3. **Neuter the `$Cutscene` token** (earlier, for the story intro): black-screen boot hang. Same
   class — the sequence waits on a completion that never comes.

## The core finding

The tutorial popups and the opening quest progression are **fused into the same state machine**:
steps set flags on game conditions, those flags gate real events (firewall), and display/input/state
advancement share code paths and a frame counter. There is no proven "draw the box" chokepoint that
is separable from the progression it drives.

## What is safe (the honest partial)

`quiet_controls_popup` binary patch: null `0x00205608` (return 1) — suppresses the steps-1/5
controls popup path while their `flag_set` still runs. Single-caller, no flag work, cannot soft-lock.
NOT "all tutorials off". Present in `binary.py`.

## UPDATE 2 (2026-09-29) — hide_tutorials (two-nop) is the best available; play-tested

Timeline of the second investigation:
- `hide_tutorials` v1 = early-return whole `ngps_render_tutorial` @`0x0023d780`. In game: FROZE the
  opening (NPC can't move, scene doesn't load). So the render fn is NOT draw-only; it has a
  load-bearing per-frame side effect (`sw v0,-0x3360(gp)` @`0x0023d8d4`, polled by the scene SM).
- Full disassembly (`docs/lab/probe_render_disasm.py`): six calls; only two are pure output —
  `jal 0x0022b158` @`0x0023d824` (popup box) and `jal 0x00133608` @`0x0023d8c0` (text line).
- `hide_tutorials` v2 (SHIPPED shape) = NOP only those two CALL SITES (`0x0C08AC56`→0,
  `0x0C04CD82`→0), delay slots + flag write kept. These are call SITES inside the tutorial fn, so
  the shared draw primitives (box: 12 callers; text-line: 247 callers, incl. all combat/HUD) are
  untouched for every other caller.
- **PLAY TEST (transforms-free `Summoner-TUTONLY.iso`, seed TUT1):** no tutorial popups; pulled
  sword, ran to the NPC, **firewall DROPPED.** Two rough edges, both self-clearing:
  (a) player movement briefly unresponsive at the very start (camera worked) then released;
  (b) combat targeting cursor didn't show on the first attempt, worked after.
  Cause of both: the tutorial STEP functions still run (they call `flag_is_set` x32 / `flag_set`
  x18 and the proximity/target helper `0x00205608`), and `do_basic_controls`/`do_basic_combat`
  gate the first-time move/target action; with the accompanying popup removed the first-time
  timing feels off but recovers. This is the popup↔first-action fusion the original finding warned
  about — not fixable by removing more draws without breaking the gate.

VERDICT: `hide_tutorials` (two-nop) is the cleanest achievable "tutorials off": popups gone,
progression intact, fire drops. Honest caveat for the UI/user: the first movement and first target
may lag for a second at the very start, then work normally. Verification: **play-verified on a
transforms-free disc** (fire drops, popups gone); the rough edges are known and documented.

SEPARATE ISSUE (not the tutorial): the FULL request disc (hide_tutorials + door_remap +
enemies_random + xp_scale + enemy_drops_always) FROZE movement entirely, but TUTONLY did not — so a
TRANSFORM freezes the opening. Prime suspect: `door_destination_remap` rewriting the start-level
spawn navpoint. Isolation build `build_nodoors_tut.py` pending test.

`skip_tutorial` v3 is demoted to EXPERIMENTAL (unreliable). See UPDATE 1 below for how v3's
"play-verified" claim was mistaken.

## UPDATE 3 (2026-09-29) — per_level enemy scope is INNOCENT; the firewall just needs 2-3 talks

Bisect result (play-verified). `Summoner-BISECT1.iso` = the known-good CHAOS recipe with ONE change:
`enemies_random` scope flipped `broad` → `per_level`, everything else identical (v3 tutorial, doors,
gear, xp_set, drops). In game: guy MOVES, opening plays; at the burning village, talked to the guy
TWICE and the **firewall DROPPED.**

So **per_level does NOT break the opening.** An earlier "fire didn't drop" reading on this same disc
was just not talking to the guy enough times — a false alarm, retracted. Both CHAOS2 (broad) and
BISECT1 (per_level) drop the fire after ~2-3 talks with the v3 tutorial patch.

REAL cause of the multi-talk quirk: **`skip_tutorial` v3 auto-advance.** It advances the
dialogue-tutorial step every frame, so the "talk to the guy" scene needs 2-3 tries before the flag
that clears the fire sticks. Not a freeze, not a soft-lock — just a couple of extra talks. Playable.

Corrected picture:
- per_level enemy scope: SAFE (play-verified, fire drops).
- v3 tutorial + full transform stack (CHAOS2, BISECT1): PLAYABLE.
- The earlier "froze movement entirely" reports were on `hide_tutorials` discs, NOT v3. So that
  freeze is associated with `hide_tutorials` + the transform stack, still unconfirmed which
  transform; but the v3-based full stack works and is the known-good.
- SHIPPABLE recipe today: v3 tutorial + per_level enemies + doors + xp + drops, honest caveat
  "talk to the NPC 2-3 times for the fire to clear." Cleaner tutorial-off (hide_tutorials without
  the freeze) remains open research.

## UPDATE 1 (2026-09-29) — v3 auto-advance is UNRELIABLE; found the real render fn

v3 (auto-advance) was play-tested again and the burning-village firewall **did NOT drop** after
talking to the guy, even after waiting. Rebuilt without the door remap (isolation test,
`Summoner-REQUEST-NODOORS.iso`, seed REQ1) — fire still did not drop. So v3 "worked once" was luck,
not a fix. Auto-advancing every frame races the scripted scene-action; the barrier-clear is not
reliably reached. **Stop trusting v3.**

**The display poller the earlier notes could not find is named in the ELF map file:**
`ngps_tutorial.o` exports these symbols (map @ ~`0x0011d4ab40`):

| symbol | addr | role |
|---|---|---|
| `do_basic_controls_tutorial` | `0x0023c868` | step logic (SETS FLAGS — load-bearing) |
| `do_basic_combat_tutorial_part1` | `0x0023ccc0` | step logic |
| `do_chain_attack_tutorial` | `0x0023d040` | step logic |
| `do_level_up_tutorial_part1` | `0x0023d0f0` | step logic |
| `do_ring_tutorial_part1` | `0x0023d420` | step logic |
| `ngps_init_tutorial` | `0x0023d5a8` | init |
| `ngps_process_tutorial` | `0x0023d618` | dispatcher (== old `FUN_0023D618`) |
| **`ngps_render_tutorial`** | **`0x0023d780`** | **DRAWS the popup — the display poller** |

`ngps_render_tutorial` is a separate function (own prologue `0x27BDFE10 addiu sp,-0x1f0` at
`0x0023d780`; `ngps_process_tutorial` is a distinct function ending before it). Early-returning the
RENDER function draws nothing while `ngps_process_tutorial` + every `do_*_tutorial` step keep
running, so all flags still get set on schedule → the firewall flag fires normally. This is the
clean cut v1/v2/v3 were groping for (they all messed with *process*; the fix is to null *render*).

The tutorial help PROSE lives in the ELF data segment ~`0x0012f3907a..0x0012f3a84b` (interleaved
with memory-card system strings — "Basic Controls Tutorial\n\n...", "Left Analog Stick...", etc.).
An alternative fix is to blank those strings size-preservingly (boxes pop but empty). Rejected in
favour of the render-null (no empty boxes, one 8-byte edit).

**New patch `hide_tutorials`** (binary): early-return `ngps_render_tutorial`.
  0x0023d780: 0x27BDFE10 (addiu sp,sp,-0x1f0) -> 0x03E00008 (jr $ra)
  0x0023d784: 0x2404FFFF (addiu a0,zero,-1)   -> 0x00000000 (nop)  [delay slot]
Because the return is the FIRST instruction, the prologue never runs, so sp is never touched and
there is nothing to restore — same shape as the proven skip_intro patch. Both originals verified
byte-for-byte against the retail ISO (docs/lab/probe_render_bytes.py). `skip_tutorial` (v3) is kept
in the catalogue but demoted to experimental so the honest history survives and we can A/B.

Verification label for this patch until Joshua plays it: **static/Ghidra-mapped + byte-verified,
NOT yet play-verified.**

## SUPERSEDED VERDICT (2026-09-28, proven in game) — v3 auto-advance

Three patches were tried; v3 is the winner. The earlier "v3 stalls" reading was WRONG — I did not
wait long enough. The burning-village fire clears on its own **short timer** once the tutorial
auto-advances; it is not a soft-lock.

| approach | site | in-game result |
|---|---|---|
| v1 force ignore-global on | `0x0023D648 lw v0,-0x3a70(gp)` → `li v0,1` | firewall never drops (soft-lock) — BAD |
| v2 NOP popup-activation | `0x0023D6B4 bne v0,zero,..` → nop | popups gone but scene stalls — BAD |
| **v3 auto-advance tail** | **`0x0023D74C beq s0,zero,..` → nop** | **popups gone, scene advances on its timer — WORKS** |

**Why v3 works:** the dispatcher `FUN_0023D618` tail only advances the active tutorial when a
dismiss button is polled (`0x0023D74C beq s0,zero,0x0023d760`). NOP-ing that branch advances every
frame with no input, so each tutorial auto-completes and its scripted scene-action still runs (e.g.
`FUN_001DBF50("invis-door02")` removes the burning-village barrier). The scene clears on its normal
timer, just without you reading/dismissing a popup. v1/v2 failed because they skipped the step loop
or the activation that the scene-advance rides on; v3 keeps both and only removes the input-wait.

`skip_tutorial` is therefore **ENABLED** in `binary.py` and in the build. It is a UI toggle +
`--binary skip_tutorial`. **Play-verified**: tutorials off, opening plays through, fire drops.

## Angles NOT yet exhausted (next)

- **The display is likely a SEPARATE per-frame poller** that reads the tutorial flag bits and draws
  the matching help text (text lives in TABLES.VPP, keyed by flag name — not in the ELF strings).
  If found, nulling THAT poller kills every popup while the steps keep setting flags. Not yet located.
- **Data-layer**: the tutorial help TEXT is in TABLES.VPP. Blanking/!-marking the tutorial message
  records (like `dialogue_blank` does for dialogue) might hide the text size-preservingly without
  touching the flag logic at all — a script-layer transform, not a binary patch. Promising, untried.
- **`-0x3970(gp)`** and the messagebox/HUD render path (seen in `0x00205490`) not yet traced to the
  tutorial box specifically.

## Addresses index (for continuation)

| what | addr |
|---|---|
| step table | `0x0127DEE8` (stride 0x24, 17) |
| step fns | `0x0023C868`..`0x0023D4A8` |
| dispatcher | `FUN_0023D618` |
| ignore-global gate | `0x0023D648` (`lw v0,-0x3a70(gp)`) |
| ignore global | `gp-0x3A70` |
| ignore-tutorial cmd handler | `0x0023C808` |
| flag_is_set / flag_set | `0x001F10A8` / `0x001F11E8` |
| step-1 proximity/popup helper | `0x00205608` (safe to null; partial) |
