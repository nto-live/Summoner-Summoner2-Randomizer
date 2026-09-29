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

## FINAL VERDICT (2026-09-28, proven in game) — BLOCKED

Three resolved patches were each built and booted; all three break the game, and a **control disc
identical except without the patch plays the opening fine** (so the patch is the cause, not the
mode stack):

| approach | site | in-game result |
|---|---|---|
| v1 force ignore-global on | `0x0023D648 lw v0,-0x3a70(gp)` → `li v0,1` | firewall never drops (soft-lock) |
| v2 NOP popup-activation | `0x0023D6B4 bne v0,zero,..` → nop | popups gone, burning-village intro stalls |
| v3 auto-advance tail | `0x0023D74C beq s0,zero,..` → nop | popups gone, burning-village intro stalls |

**Root cause, confirmed:** the dispatcher `FUN_0023D618` drives BOTH the tutorial popups AND the
advance of the opening scripted scene (burning village) through the *same* path. Removing the popup
display (any lever) also removes the scene-advance. There is no separable "draw the box only"
chokepoint. The burning-village opening is `masad_flag_*` quest/`Game-Pre-Intro` `$Cutscene` driven
and is entangled with the tutorial step machine.

`skip_tutorial` is therefore **BLOCKED** in `binary.py` (applier refuses, writes nothing) and pulled
from the build. Do not re-attempt without a genuinely new mechanism (e.g. a per-frame popup RENDER
call distinct from the scene-advance, not yet found; or a data-layer approach to the tutorial text
that was also not locatable — the text is not keyed by the flag names in TABLES.VPP).

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
