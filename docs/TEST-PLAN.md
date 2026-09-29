# TEST-PLAN.md — how a feature earns the right to be called done

The project's evidence vocabulary (`play-verified` / `boot-verified` / `byte-verified` /
`build-verified`) is good, but until now it lived in prose scattered across `TODO.md`,
`FEATURES.md` §8 and `SESSION-PROGRESS.md`. This file is the single place a feature's claim is
**defined, and the place it is proved or withdrawn.**

**The one rule:** *no feature is done until it has a row here and a tier.* A transform that works,
that everyone is confident about, and that no test exercises, is `build-verified` — and saying
otherwise is how this project over-claimed `skip_tutorial` on 2026-09-29 and had to retract it.

**The second rule:** a tier is a *ceiling*, not a badge. Claim the weakest tier you can actually
prove today; upgrade it when the evidence arrives.

---

## 1. The tiers

| tier | what it proves | how it is produced | who can run it |
|---|---|---|---|
| **T0 · schema** | the engine advertises what it claims: the catalogue parses, every transform has a description, every option-bearing transform has a schema, every binary patch declares the bytes it expects | `python tools/gen-feature-register.py`, `cli.py --list` | automated |
| **T1 · build** | the engine *applied* it — exit 0, **output is byte-size-identical to the input**, edits confined to declared fields, every declared byte read back | `cli.py --build … ` then compare sizes + read `reports[]` | automated |
| **T2 · byte** | the specific edit is present **on the output disc**, read back independently of the engine that wrote it | a lab probe against the built ISO (`docs/lab/*.py`) | automated |
| **T3 · boot** | the disc reaches **gameplay** under the headless harness, and is *actually running* (not a frozen PASS) | `pcsx2_headless_boot.ps1` **+** `churn_scan.py` | automated (slow) |
| **T4 · play** | **a human watched it work in game** | Joshua, at the emulator | **Joshua only** |

> **T3 is not T4, and PASS is not running.** `Renderer = 13` (Software) or the game silently freezes
> while the boot test still reports PASS. Always confirm with `churn_scan.py` before calling
> anything boot-verified.
>
> **And one play is not T4 either.** The `skip_tutorial` retraction happened because a single lucky
> play — on a disc where a *control with no patch* also behaved correctly — was written up as
> proof. T4 means *the specific claim was watched, on a build that isolates it.* If the only
> evidence is one session of a stacked disc, the tier is T3.

---

## 2. The suites

### A. Schema / catalogue — automated, seconds

```
python tools/gen-feature-register.py      # must exit 0
```

Acceptance:
- the register regenerates with **no hand edits** (it is generated, so any diff is real drift)
- every transform in `transforms[]` has an entry in `info{}`
- every transform in `option_aware[]` has an entry in `options{}`
- every binary patch declares `expects` and an `va`
- `numberOfItems`-style counts in the docs match the generated ones
- **no transform is a mode-orphan** unless the register lists it under §5 with a reason

### B. Engine property tests — automated, seconds

```
python -m pytest tests -q
```

Acceptance: **green.** Currently `3 failed, 5 passed, 2 skipped` — see §4 defects D1.

To add: one property test per transform currently uncovered, and a fixture test for each binary
patch's declare-and-refuse path.

### C. The end-to-end build matrix — automated, minutes ← **the one that answers "can the GUI make a working disc"**

For **every mode** (and, for option-bearing transforms, **every option value**), build a real disc
and assert on the artefact:

```
python tools/test-build-matrix.py            # (to be written — see §5)
```

Acceptance, per row:
1. exit code **0**
2. output file **exists** and is non-empty
3. **output size == input size, byte for byte** (size-preservation is the project's
   non-negotiable rule — a matrix row that breaks it is a P0)
4. the engine's own `reports[]` account for **≥1 edit** for every mode that claims to change
   something (a "chaos" mode that reports 0 edits is a silent no-op)
5. the output **re-identifies** as a supported Summoner disc (`cli.py --identify <out>`), so the
   build did not corrupt the container
6. **every mode that lists transforms reports an edit for each one** — this is the check that
   catches a mode whose blurb promises ten levers and whose argv delivers three
7. **every binary patch the mode names reports `applied` with all declared words read back
   and matching.** Modes whose only lever is an executable patch (`endgame_gate`,
   `skip_intro`) report `edits: 0` from the text layer — without this they would pass the
   matrix while proving nothing at all about the thing they actually do.
8. **every transform the mode lists appears in the report** by name

This suite is the difference between "the engine works" and **"a user describing what they want in
the UI gets a working disc."**

### D. GUI parity — automated, minutes

The GUI must not be able to ask for something the engine cannot do, and must not hide something it
can do.

```
SummonerRando.Harness.exe --dump-ui ui.json --state populated --mode <every mode>
SummonerRando.Harness.exe --screenshot shot.png
```

Acceptance:
- **every** mode in `mode_order[]` has a selectable control in the dumped UI tree (currently proved
  for the catalogue; the matrix must cover the whole list, not a sample)
- every transform and every option has a control **or** is reachable through the mode that owns it
- **no** control exists for a patch carrying `blocked` (`hide_tutorials`) — the UI must not offer a
  poisoned lever
- the argv the GUI constructs for a mode (`EngineClient.BuildArgs`) is byte-identical to an argv
  the CLI accepts and succeeds on
- the **UI's own labels agree with the catalogue**: today `skip_intro`'s *mode* metadata says
  "BLOCKED" while the *binary patch* is armed and working — see §4 defect D2

### E. Boot smoke — automated but slow

For a representative few discs (vanilla control, one cosmetic-only mode, one structural mode):

```
powershell -File F:\rando\S1\notes\pcsx2_headless_boot.ps1 -Iso "<out>.iso" -Seconds 75
python F:\rando\S1\notes\churn_scan.py 2
```

Acceptance: boot PASS **and** churn in the running range (~25 changed 1 MB blocks on Software).
Never run every mode here — it is minutes each and the matrix in C is the cheap fence.

### F. Human play checks — **Joshua, and kept deliberately short**

The point of A–E is to shrink this list, not to pad it. Every row here must be:
**one specific thing, on one named disc, with a yes/no answer.**

| # | disc | watch for | tier it upgrades |
|---|---|---|---|
| F1 | `Summoner-CHAOS.iso` | the boat transition reaches the **overworld**; an interior door loads a wrong-but-valid level | `door_remap` → T4 |
| F2 | `Summoner-TUTONLY.iso` (seed TUT1) | no popups, player moves, **fire drops** | `skip_tutorial` → T4 (re-earned) |
| F3 | 1-HP + max-gear + fast-XP disc | one-hit kills; drops land; gear reads high | `enemy_hp_set`, `weapon_attack_max`, `armor_protect_max`, `enemy_xp_set` → T4 |
| F4 | any `doors` disc | opening does **not** soft-lock (the `invis-door0N` pin holds) | the door pin → T4 |

---

## 3. Feature acceptance table

The generated `FEATURES-REGISTER.md` supplies the rows; this supplies the *bar*. Every transform
must appear there with a tier, and the tier may only be raised by a suite above.

| class | floor tier | who raises it |
|---|---|---|
| any transform | T1 build | suite C |
| any transform that rewrites a field read back off the disc | T2 byte | suite C + a lab probe |
| any mode that changes how the game *plays* | T3 boot | suite E |
| anything claiming to be shippable to a stranger | **T4 play** | Joshua |

---

## 4. Defects found while writing this plan

Recorded so they are not lost. All five are real today.

- **D1 — the test suite is red.** `3 failed, 5 passed, 2 skipped`. All three failures are staleness,
  not breakage: `skip_intro` was un-blocked on 2026-09-29 and the tests
  (`test_registration_list`, `test_blocked_patch_property`) still assert it is blocked.
- **D2 — `skip_intro` contradicts itself in user-facing metadata.** The *binary patch* entry is
  implemented, armed (`va 0x002419C0`, `expects 0x27BDFEF0`) and play-verified; the *mode* entry
  still says **"BLOCKED until the movie-start call site is located"** with risk `blocked`. One of
  the two is lying to the user. Fix the mode text.
- **D3 — the test suite is not reproducible from a clean checkout.** There is no `requirements.txt`,
  no `pyproject.toml` and no venv. `pytest` and `hypothesis` had to be guessed and installed by
  hand. A second contributor cannot run the suite at all without this.
- **D4 — 9 transforms are reachable from no mode.** All nine are the levers that landed in the
  2026-09-28 chaos build: `armor_protect_max`, `enemy_damage_set`, `enemy_drops_always`,
  `enemy_drops_random`, `enemy_hp_set`, `enemy_xp_random`, `enemy_xp_set`, `music_tracks_shuffle`,
  `weapon_attack_max`. They are reachable through the GUI's independent options, so this is not a
  lost feature — but a user browsing *modes* cannot find them, and `TODO.md` §7 already asked for
  this. Either bundle them into a named mode or say so in the register.
- **D5 — the harness never validates a real artefact.** `EngineClient` plumbing is proved against
  `--dry-run` only, so nothing exercises "write the ISO and check it". That is precisely the
  user's question, and it is suite C.

---

## 5. What has to be built to make this plan real

1. `tools/test-build-matrix.py` — suite C. Walks `mode_order[]` × option values, builds, asserts the
   six conditions, prints a pass/fail matrix.
2. `requirements.txt` — `pytest`, `hypothesis` (D3).
3. Fix D1 (update the three stale tests) and D2 (the `skip_intro` mode text).
4. Extend the harness with a `--build` that writes a real ISO (not just `--dry-run`), so suite C and
   suite D share one code path with the GUI.
5. A `--no-play` tag on the register listing which rows are still waiting on a human, so the
   backlog of T4 claims is visible at a glance.

---

## 6. Honest gaps

- Suite C proves a disc is **structurally** sound, not that it is **fun** or **completable**.
  Reachability is still unchecked — that is the flag-graph solver, and until it exists
  `door_remap` stays `high` risk no matter how green this plan goes.
- T4 cannot be automated here. It is Joshua's, and the plan's job is to keep his queue short.
- Nothing in this plan touches Summoner 2 until the VPP v2 reader exists.
