# Findings — tutorial-off investigation and the full-disc freeze (2026-09-29)

A consolidated record of everything learned this session, so none of it is re-derived. Pairs with
`docs/RESEARCH-SKIP-TUTORIAL.md` (the deep dive) and `.kiro/steering/project-memory.md` (the state).

## TL;DR

- The old "`skip_tutorial` v3 SOLVED, play-verified" claim was **wrong** — it rested on a single
  lucky play, and later seeds showed the burning-village firewall did NOT drop. v3 is unreliable.
- The tutorial popups and the opening's first-time-action gating are **fused**. There is no clean
  "draw the box" call we can remove without also disturbing movement/targeting timing.
- The best achievable tutorial-off is **`hide_tutorials`** (a two-NOP patch). On a transforms-free
  disc it is play-tested working: no popups, the firewall drops. It has two self-clearing rough
  edges at the very start (brief movement lock; targeting cursor missing on first try).
- **Separate, still-open problem:** the FULL request disc freezes movement at the start, but the
  tutorial-only disc does not. So a **transform** freezes the opening — not the tutorial patch.

## Verification labels used here

- **byte-verified** = the exact original bytes were read off the retail ISO before patching.
- **play-verified** = actually booted and played in PCSX2 by Joshua.
- **static** = read from disassembly/map only, not run.

## The tutorial system (recap of the mapped facts)

Tutorial code = `code/summoner/interface/ngps_interface/ngps_tutorial.o`. The embedded ELF map file
(~`0x0011d4ab40` in the image) names the functions:

| symbol | addr | role |
|---|---|---|
| `do_basic_controls_tutorial` | `0x0023c868` | step logic — SETS quest flags (load-bearing) |
| `do_basic_combat_tutorial_part1` | `0x0023ccc0` | step logic |
| `do_chain_attack_tutorial` | `0x0023d040` | step logic |
| `do_level_up_tutorial_part1` | `0x0023d0f0` | step logic |
| `do_ring_tutorial_part1` | `0x0023d420` | step logic |
| `ngps_init_tutorial` | `0x0023d5a8` | init |
| `ngps_process_tutorial` | `0x0023d618` | dispatcher (old `FUN_0023D618`) |
| `ngps_render_tutorial` | `0x0023d780` | display routine (NOT draw-only — see below) |

The step functions call `flag_is_set` (`0x001F10A8`, ×32) and `flag_set` (`0x001F11E8`, ×18), plus a
proximity/target helper (`0x00205608`). The burning-village fire barrier is removed by
`FUN_001DBF50("invis-door02")`, which the tutorial steps' scripted actions trigger. **Never patch
`flag_is_set` / `flag_set`** — they are shared by every game flag.

## `ngps_render_tutorial` disassembly (the key new fact)

Full disasm in `docs/lab/probe_render_disasm.py`. The function is 0x0023d780..0x0023d8f8, six calls:

| # | jal @ | target | role |
|---|---|---|---|
| 1 | 0x0023d7a0 | 0x001333c0 | context query |
| 2 | 0x0023d800 | 0x00133af0 | text measure / layout |
| 3 | **0x0023d824** | **0x0022b158** | **popup BOX draw** (x/y/size, no text) |
| 4 | 0x0023d838 | 0x0013bf60 | colour set (light grey 0xDC) |
| 5 | 0x0023d888 | 0x00267418 | per-line string build |
| 6 | **0x0023d8c0** | **0x00133608** | **TEXT-LINE draw** (loop body) |

Critically, at `0x0023d8d4` the function does `sw v0,-0x3360(gp)` — a "rendered this frame" flag the
scene state machine polls. **This is why early-returning the whole function froze the opening.**

The two draw targets are shared UI primitives, not tutorial-exclusive: `0x0022b158` (box) has 12
callers, `0x00133608` (text line) has **247** callers across combat/HUD. We NOP the two CALL SITES
inside the tutorial function only, so every other caller is unaffected.

## What was tried, and the in-game result

| approach | site(s) | result |
|---|---|---|
| v1 force ignore-global on | `0x0023d648` lw→`li v0,1` | firewall soft-lock (skips step loop) — BAD |
| v2 NOP activation branch | `0x0023d6b4` | popups gone, scene stalls — BAD |
| v3 auto-advance (`skip_tutorial`) | `0x0023d74c` beq→nop | fire dropped ONCE, failed on later seeds — UNRELIABLE |
| early-return render | `0x0023d780` → jr $ra + nop | froze opening (NPC can't move, nothing loads) — BAD |
| **two-NOP draws (`hide_tutorials`)** | `0x0023d824` + `0x0023d8c0` → nop | **popups gone, fire drops; minor start lag** — BEST |

### Why the v3 "play-verified" claim was mistaken
The only play where the fire dropped with v3 was one CHAOS session. A separate **control disc with
NO tutorial patch** ALSO dropped the fire — so the fire clearing did not prove v3 worked. Later
seeds (REQ1, REQ1-no-doors) with v3 did NOT drop the fire. Conclusion: v3 was never reliable; the
earlier "SOLVED" was over-claimed from insufficient evidence. `skip_tutorial` is now labelled
EXPERIMENTAL in `binary.py`.

## `hide_tutorials` — the shipped tutorial-off patch

Two 4-byte NOPs, byte-verified against the retail ISO (`docs/lab/probe_two_draws.py`):

```
0x0023d824: 0x0C08AC56 (jal 0x0022b158)  -> 0x00000000 (nop)   # popup box
0x0023d8c0: 0x0C04CD82 (jal 0x00133608)  -> 0x00000000 (nop)   # text line
```

Delay slots (`0x0023d828 addiu a3,a3,0xa`; `0x0023d8c4 addu s3,s3,s5`) are left intact — they
execute harmlessly. The `sw v0,-0x3360(gp)` flag write and calls #1/#2/#4/#5 all still run, so the
scene keeps advancing.

**Play test — `Summoner-TUTONLY.iso`, seed TUT1 (skip_intro + hide_tutorials, NO transforms):**
- No tutorial popup boxes. ✔
- Pulled the sword, ran to the NPC, **firewall dropped.** ✔ (play-verified)
- Rough edge A: player movement briefly unresponsive at the very start; camera worked; released on
  its own.
- Rough edge B: combat targeting cursor did not appear on the first attempt; worked on retry.

Both rough edges trace to the tutorial STEP functions still running their first-time gates
(`do_basic_controls`, `do_basic_combat`) without the accompanying popup. This is the popup↔action
fusion; removing more draws would break the gate that clears the fire. They self-clear, so the disc
is playable.

## OPEN PROBLEM — a transform freezes the opening (not the tutorial)

Established by isolation:

| disc | tutorial | doors | enemies | other | start movement |
|---|---|---|---|---|---|
| CHAOS2 (last night) | skip_tutorial v3 | remap | broad | hp1, wpn/arm max, xp_set, dmg0 | playable |
| TUTONLY (today) | hide_tutorials | — | — | — | playable (minor lag) |
| HIDETUT / REQUEST | hide_tutorials | remap | per_level | xp_scale, drops_always | **FROZE** |

- The tutorial patch alone (TUTONLY) does NOT freeze → tutorial patch is not the cause.
- CHAOS2 had the door remap on and was playable → the door remap alone may NOT be the cause.
- The freeze appears only in the combined HIDETUT/REQUEST stack. Next step is to bisect the
  transforms on a `hide_tutorials` base, one at a time, starting with doors removed
  (`build_nodoors_tut.py`, staged but not yet tested).

Note: last night's playable disc used **v3 + broad + xp_set**; the frozen discs use
**hide_tutorials + per_level + xp_scale + drops_always**. The differing variables to bisect are the
tutorial patch, the enemy scope, the xp transform, and drops_always — as well as doors.

## Build recipes (all in `tools/builds/`, ISOs go to the external out dir)

| script | ISO | contents |
|---|---|---|
| `build_chaos.py` | Summoner-CHAOS.iso | last night's full stack (v3 tutorial, broad enemies) |
| `build_request.py` | Summoner-REQUEST.iso | the user request (v3? no — skip_intro+skip_tutorial) |
| `build_request_nodoors.py` | Summoner-REQUEST-NODOORS.iso | REQUEST minus door remap (v3) |
| `build_hidetut.py` | Summoner-HIDETUT.iso | REQUEST feature set but hide_tutorials instead of v3 |
| `build_tutonly.py` | Summoner-TUTONLY.iso | ONLY skip_intro + hide_tutorials, no transforms |
| `build_nodoors_tut.py` | Summoner-NODOORS-TUT.iso | hide_tutorials + enemies/xp/drops, NO doors (untested) |

## Lab probes added this session (all read-only, in `docs/lab/`)

- `probe_tutorial_text.py` — found masad_*_tutorial are +Flag decls, not text
- `probe_messagebox.py` — +Messagebox is examine-text, NOT tutorials
- `probe_tut_prose.py` — tutorial prose is in the ELF data segment ~`0x0012f3907a`, not a VPP
- `probe_tut_strings.py` — mapped the tutorial string block + the ngps_* symbols
- `probe_render_bytes.py` — read the render/process/init function prologues
- `probe_render_disasm.py` — full disasm of ngps_render_tutorial + callee roles
- `probe_two_draws.py` — byte-verified the two draw call words
- `probe_draw_callers.py` — counted callers of each draw routine (proved they're shared primitives)

## Recommendation

1. Rebuild last night's known-good CHAOS recipe to have a playable disc in hand.
2. Decide the tutorial patch: `hide_tutorials` is the honest best (play-verified, minor start lag)
   but only tested transforms-free. Confirm it survives the transform stack once the freeze is fixed.
3. Bisect the transform freeze on a hide_tutorials base (doors → enemies scope → xp → drops).
4. Do NOT re-attempt v1/v2/v3 or the render early-return — all documented BAD above.
