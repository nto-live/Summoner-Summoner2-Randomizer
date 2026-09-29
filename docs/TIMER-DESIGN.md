# Timed Runs — Design

Goal: **a timer, displayed on the completion screen.** For a roguelike / speedrun framing, the
end of a run should report how long it took.

*Last updated 2026-09-20.*

---

## 1. The discovery that makes this tractable

Summoner already has a complete timer subsystem, and it is driven by **PS2 hardware**. The
symbol map gave us the API:

```
timer_init_void                     timer_get_int
timer_get_elapsed_time_long_long_int
timer_format_time_int_char          ← formats a time into a string
timer_debug_ticks
timestamp_elapsed / timestamp_realtime_elapsed
timestamp_realtime_reset / timestamp_pause / timestamp_increment / timestamp_invalidate
frametime_calculate / frametime_reset / frametime_set_cap
sceCdReadClock                      ← PS2 real-time clock
```

And the decompiled code tells us exactly how it works:

```c
void timer_init_void(void) {
  if (iGpffff9018 == 0) {
    REG_RCNT0_MODE   = 0;
    AddIntcHandler(9, 0x111170, 0);
    EnableIntc(9);
    REG_RCNT0_COUNT  = 0;
    REG_RCNT0_TARGET = 0x8000;
    REG_RCNT0_MODE   = 0x181;
    iGpffff9018 = 1;
  }
}

undefined4 timer_get_int(int param_1) {
  if (param_1 == 1000)    return lGpffff9038 * 1000    / 0x11E;   // ticks -> ms
  if (param_1 == 1)       return lGpffff9038           / 0x11E;   // ticks -> SECONDS
  if (param_1 == 1000000) return lGpffff9038 * 1000000 / 0x11E;   // ticks -> us
  Debug_error(...);                                               // any other value is a bug
}
```

**What this means, concretely:**

| Fact | Value |
|---|---|
| Clock source | PS2 `RCNT0` hardware timer, interrupt 9 |
| Tick rate | **286 Hz** (`0x11E`) |
| Elapsed time | **one 64-bit global**, `lGpffff9038` |
| Seconds elapsed | `lGpffff9038 / 286` |
| Formatter | `timer_format_time_int_char` — already turns a time into a string |

So there is a **single 64-bit counter** that is the run clock. We do not have to invent a timer
— we have to *read* one that already exists, and then get it onto the screen.

---

## 2. Three tiers

### Tier 1 — External timer (no game modification). **Buildable now.**

Read the counter out of the running emulator and display it outside the game.

- The counter lives at a fixed absolute address: gp-relative offset `0xFFFF9038`
  (i.e. `gp − 0x6FC8`). PS2 `gp` is set once at startup, so once we know it, the address is
  constant for every run.
- PCSX2 exposes a **PINE** server (port 28011) for reading emulator memory, and there is a
  pip-installable Python client plus an MCP bridge. A small script polls the 64-bit value,
  divides by 286, and renders a live timer.
- **Bonus:** the app already knows the seed and the build, so Tier 1 can record a
  **per-seed completion time** into `builds.json` — a run history for comparing seeds and racing.

**Effort:** hours. **Blocked by:** needing a real PCSX2 session to verify (see §4).
**Limitation:** the timer is *outside* the game — not on the completion screen.

### Tier 2 — Timer on the completion screen. **Targeted code patch.**

The ending is a cutscene sequence (`End1-Montage`, `End2-Montage`, and a `credits.tbl` in the
table layer). `timer_format_time_int_char` already produces a formatted string.

The patch shape: wherever the completion/credits screen builds its text, append the result of
formatting the run clock. Because we have **6,530 named symbols** and byte-exact address
translation, this is a targeted hook rather than a hunt — the work is identifying the one call
site that assembles the ending text.

**Effort:** days. Needs the binary layer (§3).
**Open question:** what exactly the completion screen renders from — `credits.tbl` is the prime
suspect, and it is text in the table layer, which is encouraging.

### Tier 3 — Always-on in-game HUD timer. **Bigger patch.**

Superimpose a running clock during play. Requires hooking the render pass and having somewhere
to draw — the real work is finding a text-draw path we can reuse (`timer_format_time` gives us
the string; we need a draw call and a safe screen region).

**Effort:** weeks. Nice-to-have, not on the critical path.

---

## 3. What Tier 2 depends on: the binary layer

Tiers 2 and 3 need the same capability: **editing `SLUS_200.74` rather than the script tables.**
That is the "binary layer" described in `COMPILED-CODE.md`, and the pieces already exist:

- address ↔ file offset translation is solved (`vaddr − 0xFF000`)
- 6,530 symbols are applied, 3,391 functions named
- Ghidra 12.1.3 + the R5900 Emotion Engine extension decompiles to readable C
- the same seed, the same size-preserving rule, and the same UI can carry over

What is missing is a **patcher**: a transform class that writes 4-byte edits into the
executable and re-integrated into the app's mode list.

---

## 4. The blocker, and how to clear it

Nothing in Tiers 1–2 can be **verified** without running the game. PCSX2 2.8.1 and 42 BIOS dumps
are ready on the N100, but OpenClaw's shell runs in **Session 0** — no interactive desktop, so no
GUI application can open a window. Remote Desktop or a logged-in session clears this.

Tier 1 is worth doing *first* precisely because it is the cheapest way to prove the clock is
where we think it is: read the address, confirm it advances at wall-clock rate, and we have
validated the whole premise.

---

## 5. Resolving the counter's absolute address

Two independent routes, either of which settles it:

1. **Statically, from `_start`.** The ELF sets `gp` once in its startup code
   (`_start` at `0x00100008`). Disassemble it, find the `lui`/`addiu` pair that loads `$gp`,
   and add `−0x6FC8`. `_gp` is *not* in MAIN.MAP, so this must come from the code.
2. **At runtime, via PINE.** Read the `gp` register from the emulator (PINE supports register
   reads), or simply scan for a 64-bit value that increments monotonically and whose
   `value / 286` tracks wall-clock seconds. The second method is self-verifying.

Route 2 is more robust because it also proves the tick rate empirically — if `value / 286`
matches a stopwatch, the whole model is confirmed in one step.

---

## 6. Plan

1. **Resolve the counter address** (§5, route 2 preferred) and confirm the 286 Hz rate
   empirically. *Requires a desktop session.*
2. **Build the Tier 1 external timer** — read via PINE, display live, record per-seed times into
   the app's build history. No game modification, works with every existing mode.
3. **Build the binary-layer patcher**, then do the Tier 2 hook so the final time appears on the
   completion screen.
4. Tier 3 only if it still seems worth it afterwards.

## 7. Why this is a good fit

The randomizer already produces a **deterministic seed** and (for Roguelike) a deliberately hard
run. A recorded completion time turns those into something comparable — the missing piece for
races, for leaderboards, and for answering "was that seed actually harder?". The engine tracking
its own clock, at a known rate, in one known global, is about as good a starting position as this
project has had on any feature.
