# Why skip_tutorial v3 produces the wanted behavior, and hide_tutorials does not

Disassembly-grounded answer (probe: `docs/lab/probe_process_disasm.py`). This is the definitive
explanation — replaces the earlier guesswork.

## The tutorial dispatcher tail (`ngps_process_tutorial`, 0x0023d618)

The step loop (0x0023d678..0x0023d6c8) runs the active step. Then the TAIL polls input and decides
whether to advance:

```
0x0023d6d0  beq v0,zero,0x0023d75c     ; no active tutorial struct -> skip to epilogue
0x0023d6dc  beq v0,zero,0x0023d74c     ; field4==0 -> skip advance
0x0023d6e8  jal 0x0011aac0 ; a1=0xe    ; POLL PAD for button 0xe  -> v0
0x0023d6f0  beq v0,zero,0x0023d728     ; not pressed -> try button 0xc instead
0x0023d700  jal 0x001b36e0 ; a0=0x23   ; (pressed) play UI sound
   ...bumps step counter at -0x335c(gp)... ; 0x0023d70c..0x0023d71c
0x0023d720  beq zero,zero,0x0023d74c   ; -> fall to the gate with s0 still 0 on this path
0x0023d728  jal 0x0011aac0 ; a1=0xc    ; POLL PAD for button 0xc -> v0
0x0023d734  beq v0,zero,0x0023d74c     ; not pressed -> gate with s0==0
0x0023d744  jal 0x001b36e0 ; a0=0x24   ; (pressed) play UI sound
0x0023d748  addiu s0,zero,1            ; s0 = 1  == "a button WAS pressed this frame"
0x0023d74c  beq s0,zero,0x0023d760     ; <-- THE GATE. if s0==0 skip the advance, go to epilogue
0x0023d750  (delay)
0x0023d754  jal 0x0023d5f0             ; ADVANCE the tutorial step  (only when s0!=0)
0x0023d75c..0x0023d77c  epilogue / jr ra
```

`s0` is zeroed at the top (`0x0023d63c`). It is set to 1 ONLY on the paths where a taught button
was actually pressed. So:

- **Retail:** `jal 0x0023d5f0` (advance) runs ONLY when you press the button the step is teaching.
  That is the input-gate — the step holds until you perform the taught action.

## What each patch changes

- **skip_tutorial v3 = NOP `0x0023d74c` (`beq s0,zero,0x0023d760` -> nop).**
  Removes the gate. The fall-through `jal 0x0023d5f0` (advance step) now runs EVERY FRAME regardless
  of `s0` — i.e. regardless of whether the button was pressed. The tutorial auto-advances with no
  input, the popup is dismissed with it, and control is never held. **This is the wanted behavior**
  (no tutorial, player moves, scene progresses). Verified in game.

- **hide_tutorials = NOP the two draw calls in `ngps_render_tutorial`.**
  Touches only the DRAW function. The gate at `0x0023d74c` is untouched, so the step STILL waits for
  the button press before advancing. Result in game: the window is gone but the input-gate and the
  sound cue remain -> player is frozen at the start with no instructions. **Worse UX.** Confirmed.

## The verdict

v3 is the CORRECT mechanism. The wanted behavior comes specifically from making
`jal 0x0023d5f0` (the per-frame step-advance) unconditional. hide_tutorials attacks the wrong thing.

## v3's one weakness and whether it can be removed

v3 advances the DISPATCHER's step every frame. The burning-village fire is removed inside the
dialogue-tutorial step but only after `masad_dialogue_tutorial_part2b` is set by the CONVERSATION
(see ANALYSIS-invis-door02-fire-barrier.md). Because v3 keeps advancing, it can move past the
dialogue-tutorial step before the conversation raises part2b — so the fire-removal step is skipped
until you re-enter it by talking again. That is the "talk 2-3 times" quirk. It is NOT a soft-lock:
re-talking re-satisfies it and the fire drops. Confirmed in game (BISECT1: talked twice, fire
dropped).

Fully removing the 2-3-talk quirk would mean advancing every step EXCEPT letting the dialogue step
persist until part2b is set — i.e. conditional auto-advance, which is more work and not clearly
worth it since the current behavior is playable. Documented as a known, minor, non-blocking quirk.

## Recommendation

Ship **skip_tutorial (v3)** as THE tutorial-off option. Un-demote it from EXPERIMENTAL; relabel it
as the working patch with the honest "talk to the NPC a couple of times for the opening fire" note.
Keep hide_tutorials only as a documented dead-end (wrong lever: hides the box, leaves the gate).
