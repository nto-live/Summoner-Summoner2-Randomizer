# Research task — resolve the "skip the startup movie" patch

*Written 2026-09-28. This is a host-side Ghidra task: the toolchain, the symbol map and the disc
live on the N100 (`F:\rando\S1\ghidra-ee`, the R5900 project), not in this repo.*

> **Update 2026-09-28 — the address is now resolved, but the patch is deliberately gated.** The
> call site has been found and the exact bytes are already in `src/binary.py`: `va=0x002419C0`
> patched to `jr $ra` (`0x03E00008`) with a delay-slot `li v0,1` (`0x24020001`) at `+0x4`, which
> makes the movie-player routine return immediately and neutralises the THQ logo, the attract demo
> and the Volition logo in one shot. Both originals were verified byte-for-byte against the retail
> ISO. **The patch is NOT live:** it carries a `blocked` reason ("movie-start call site resolved
> but not accepted for release; present but pending sign-off"), so `apply_patches` refuses it —
> it writes zero bytes and reports why. So the search task in §2–§5 below is **done**; the only
> remaining work is **accepting it for release** — deleting the one `blocked=` line and then
> boot-/play-verifying (§6). That acceptance is out of scope for the NTO Live feature (Non-Goal).
> The original discovery notes are kept below for the record and for the delay-slot rationale.*

---

## 1. Why this is a binary patch, not a text edit

Established already, do not re-derive (see `MODES.md` "Fast Start" caveats and `FEATURES.md` §7):

- **There are zero `.pss` references in `TABLES.VPP`.** The intro/boot video is not addressable
  from the script layer that every other feature here edits.
- The movie is played by the **executable**, in `code/vsdk/ps2_movieplayer/mplayer.o`.

So the only honest way to disable it is an ELF patch: no-op the call that starts the boot movie,
or branch over it. That is exactly what `binary.py` is for (`endgame_gate` is the working
precedent — one 4-byte instruction, declared-and-refused, read back).

## 2. What to find

The **one call site** that kicks off the boot/intro movie during startup. Concretely, a `jal`
(or `jalr`) into the movie-player open/play path, reached from the boot sequence — before the
main menu / first playable frame.

Deliverable: a virtual address `va` and the exact 4-byte little-endian word currently there
(`original`), plus a one-line decision on how to neutralise it (see §4).

## 3. How to find it (Ghidra R5900 project)

Toolchain and reproduction are in `COMPILED-CODE.md` §2–3. Working in the existing
`F:\rando\S1\ghidra-ee` project (R5900, symbols already applied):

1. **Start from the source-file name.** `MAIN.MAP` shipped 275 original source filenames; the
   movie player is `mplayer.o` (`code/vsdk/ps2_movieplayer/`). In the Symbol Tree / Namespaces,
   find the functions attributed to that object. Look for names in the
   `mplayer` / `movieplayer` / `pss` / `sceMpeg` family (open, play, start, decode).

2. **Identify the "play/open" entry** — the function that begins playback (as opposed to
   per-frame decode or shutdown). `mplayer::open` / `..._play` / `..._start` is the target.

3. **Find who calls it during boot.** Use Ghidra's *References → Show References To* on that
   function. Walk the call sites and find the one on the **startup path** (reached from `_start`
   / the boot/init sequence, before the title menu). The intro is typically a single unconditional
   call early in init. Cross-check against the boot ELF flow already documented
   (`ELF cdrom0:\SLUS_200.74;1 ... is executing` → init).

4. **Confirm it is the intro, not an in-game cutscene.** In-game cutscenes go through the script
   layer (`$Cutscene`, handled by `cutscene_bypass`). The boot movie call is in engine init and
   has no `$Cutscene` record behind it. If the call is data-driven (a filename argument), confirm
   the filename is the intro video, not a level asset.

5. **Read the exact bytes.** At the chosen instruction, record:
   - `va` (virtual address),
   - the current 4-byte word (Ghidra: the instruction bytes; or compute from the listing),
   - the surrounding instructions (so the no-op choice in §4 is safe re: delay slots).

## 4. How to neutralise it — pick one, safely

MIPS/R5900 has branch **delay slots**, so be deliberate:

- **Option A — nop the `jal`.** Replace the `jal <movie_play>` word with `0x00000000` (`nop`).
  Simplest, but the instruction in the **delay slot** after the `jal` still executes — confirm it
  is harmless (often it sets up an argument that is then unused). This is the `encode` the patch
  currently assumes (`lambda p: 0x00000000`).
- **Option B — return early from the movie-start wrapper.** If there is a small wrapper whose only
  job is to play the intro, patch its first instruction to `jr $ra` (`0x03E00008`) with a `nop`
  delay slot. Cleaner when the wrapper exists.

Whichever you pick, the **`original` you declare must be the real word at that `va`** — the applier
refuses on mismatch, which is the whole safety guarantee.

## 5. It is already in `binary.py` — resolved, but gated by `blocked`

In `src/binary.py`, the `skip_intro` entry is present with the **resolved** address and bytes. The
placeholders described in earlier drafts have been filled in; the chosen fix is Option B (return
early from the movie-player routine), with the delay slot forced to a harmless `li v0,1`:

```python
"skip_intro": Patch(
    name="skip_intro",
    va=0x002419C0,
    original=0x27BDFEF0,           # addiu sp,sp,-0x110  (movie player prologue)
    encode=lambda p: 0x03E00008,   # jr $ra  -> return immediately
    extra=[
        # delay slot: li v0,1 so callers see a non-zero "handled" status and skip playback
        (0x4, 0xFFB400B0, 0x24020001),
    ],
    label="Skip the startup movie",
    help="Stops the boot/intro videos (THQ logo, attract demo, and Volition logo) from playing...",
    blocked="movie-start call site resolved but not accepted for release; "
            "present but pending sign-off (see docs/RESEARCH-SKIP-INTRO.md). "
            "Delete this line to enable.",
),
```

The addresses and words are real and verified against the retail ISO. **The one remaining step to
make the feature live is deleting the `blocked=...` line** — that single change flips it from
"present but pending" to "live", with no other code change (`apply_patches`, `describe()`, the
`--binary skip_intro` flag and the desktop toggle all handle it already). Accepting/verifying it in
game is out of scope for the NTO Live feature.

## 6. Verify (host, headless)

Same discipline as `endgame_gate` (`COMPILED-CODE.md` §7–8, `DOOR-REMAP.md` for the rig):

1. Build a test disc with only `skip_intro`:
   ```powershell
   python src\cli.py --build "F:\rando\S1\iso\Summoner.iso" --mode skip_intro \
          --seed INTRO1 --out "F:\rando\S1\out\Summoner-skipintro-INTRO1.iso" -q --report out.json
   ```
   Expect: `applied: true`, read-back verified, **exactly 4 bytes** changed across the whole image,
   size identical, and the CRC shifts (the executable changed — like `endgame_gate`'s
   `13E2774E → 13E2775E`).
2. Boot headless (`pcsx2_headless_boot.ps1`) and confirm it reaches gameplay **without** the intro
   video. Label the result honestly: boot-verified vs play-verified.
3. Record the measured bytes/CRC in `FEATURES.md` (binary section) and strike the blocked row in
   `PLANNED.md`.

## 7. Honest state right now

- The feature is **present-but-pending**: the call-site addresses are **filled in** in `binary.py`
  (`va=0x002419C0` → `jr $ra` + delay-slot `li v0,1`, covering the THQ logo, attract demo and
  Volition logo), but the patch is deliberately **gated by a `blocked` reason**, so `apply_patches`
  refuses it — it writes nothing and reports why. It appears in `cli.py --list` (mode + binary
  catalogue), is selectable via `--binary skip_intro` and as an independent desktop toggle, and is
  surfaced as pending in the Result panel.
- **Nothing is guessed** — the addresses were resolved and both originals verified byte-for-byte
  against the retail ISO, in keeping with the project's cardinal binary rule (the `0x1F6608` vs
  `0x1F6614` mix-up is the cautionary tale) and the "declare and refuse" guarantee in
  `COMPILED-CODE.md` §9.
- **The only step left is acceptance:** delete the `blocked=` line to enable the write, then
  boot-/play-verify in the emulator (§6) and record the measured bytes/CRC. That acceptance is out
  of scope for the NTO Live feature (Non-Goal) and has not been done — treat the feature as
  present-but-pending, not verified or working.
