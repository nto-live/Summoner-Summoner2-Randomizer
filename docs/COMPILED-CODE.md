# Compiled Code — Toolchain and Findings

How we get into `SLUS_200.74`, what we've read out of it, and how to reproduce any of it.

*Last updated 2026-09-20.*

---

## 1. Why this matters

The randomizer started as a **text-layer** tool. `TABLES.VPP` holds a plain-text script
language, so 28 transforms were written without touching a single binary.

But a lot of the game is not in that text layer. The executable holds **15.9 MB of `.data`**
— baked numeric tables, creature stats, curves, spawn data — plus all the logic. As long as
we couldn't read the code, that whole layer was out of reach.

We can read it now. That opens a **binary layer**: a second class of transform that edits the
executable instead of the script stream.

---

## 2. Toolchain

| Piece | Version / location |
|---|---|
| Java | OpenJDK **21.0.12.1** (Microsoft build) — Ghidra requires it |
| Ghidra | **12.1.3 PUBLIC** at `F:\rando\S1\tools\ghidra_12.1.3_PUBLIC` |
| EE extension | `ghidra-emotionengine-reloaded` **v2.1.37**, built for `ghidra_12.1.3_PUBLIC` |
| Scripting | `pyghidra` 3.1.0 (Ghidra 12 replaced Jython with this) |
| Target | `SLUS_200.74`, 18,401,616 bytes, EE ELF |
| Symbols | `F:\rando\S1\notes\ghidra-symbols.txt` — 6,530 name→address pairs |
| Projects | `F:\rando\S1\ghidra-proj` (generic MIPS) · `F:\rando\S1\ghidra-ee` (**R5900, use this**) |

### Why an extension is needed at all

Ghidra's stock MIPS processor module cannot model the **R5900** — the PS2's Emotion Engine
adds MMI multiply-accumulate instructions and VU0 macro mode. Import without the extension
produces disassembly with thousands of `Pcode error` lines and a decompiler that emits
nothing but `halt_baddata()`.

With the extension: **`Pcode errors: 0`**.

### The install gotcha

Placing the extension in `Extensions\Ghidra\` does **not** register it — headless fails with:

```
InvalidInputException: Unsupported language: r5900:LE:32:default
```

The reliable fix is to install it as a **processor module** instead:

```
copy extensions\...\ghidra-emotionengine-reloaded\data\languages\*  ->  Ghidra\Processors\MIPS-R5900\data\languages\
copy extensions\...\ghidra-emotionengine-reloaded\lib\*.jar        ->  Ghidra\Processors\MIPS-R5900\lib\
write a non-empty Module.manifest
```

Then the language `r5900:LE:32:default` is always found.

---

## 3. Reproducing the analysis

```bat
set JAVA_HOME=C:\Program Files\Microsoft\jdk-21.0.12.101-hotspot

support\analyzeHeadless.bat F:\rando\S1\ghidra-ee SummonerEE ^
    -import F:\rando\S1\extracted\SLUS_200.74 ^
    -processor r5900:LE:32:default ^
    -loader ElfLoader
```

Takes ~116 seconds and reports `Analysis succeeded` / `Save succeeded` / `Import succeeded`.

Then apply symbols and decompile with `F:\rando\S1\tools\ghidra_ee_decomp.py`
(uses `pyghidra`). Three things that file had to get right, each of which cost a failed run:

1. **Sanitise names.** `MAIN.MAP` holds *demangled C++*. Ghidra rejects `()`, `::`, `<`, `>`,
   `,`, `*`, `&`, `=` in symbol names, so `fl::fl(float)` → `fl_fl_float_`. Without this,
   all 6,530 fail.
2. **Mutate inside a transaction.** Otherwise every `setName` throws
   `NoTransactionException`.
3. **`openProgram(..., True)` means read-only.** Pass `False` if you intend to save. Saves
   can also fail with `Unable to lock due to active transaction`, so the pragmatic pattern
   is **apply symbols and decompile in one in-memory pass** — no save needed.

### Address translation

Single `PT_LOAD` segment, so:

```
file_offset = vaddr - 0x00100000 + 0x1000      i.e.  vaddr - 0xFF000
```

That is what makes byte-exact patching possible: `door_is_open` at `0x0017A570` is byte
`0x17B570` in the file.

---

## 4. What we've read

### The symbol map

`MAIN.MAP` shipped unstripped on the retail disc: **6,561 symbol names and 275 original
source filenames**. Applying them gives 3,391 named functions. The interesting families:

```
door        ->  21       level      -> 185      party -> 36
item        ->  89       teleport   ->  10      transition -> 4
```

Highlights:

```
check_portal_crossing_seg_int_pnt_int
check_crossing_closed_door_vector_vector_int_int_float
door_is_open_int_float            get_door_open_char_const
dcf_door_open_void    dcf_door_close_void    dcf_door_toggle_void
get_gamestage_void    dcf_gamestage_void     dcf_full_party_void
gameplay_unload_level_bool        is_valid_level_script_filename_char_const
exec_script_action_level_script_living_entity
party_controller_new_party · party_controller_add_member · party_controller_remove_member
item_new · item_init · item_delete · item_reset_all
level_script_load_effects
```

`dcf_*` looks like an internal debug/console family (`dcf_gamestage`, `dcf_full_party`,
`dcf_door_toggle`) — worth chasing, because if any of it is reachable in a retail build it is
a ready-made test harness.

### The portal mechanism — the door answer

`check_portal_crossing` decompiled at `0x0017EA28`, 308 bytes:

```c
int check_portal_crossing_seg_int_pnt_int
        (undefined8 param_1, int param_2, uint param_3, undefined4 *param_4)
{
  if (puGpffff9930 != NULL) {                 // global: linked list of portals
    puVar6 = puGpffff9930;
    while (true) {
      uStack_ac = puVar6[1];
      lVar4 = check_if_segs_cross_seg_seg_pnt(param_1, &uStack_b0, &fStack_c0);
      if (lVar4 == 1) {                       // player's segment crossed this portal
        lVar4 = is_pnt_right_of_seg_pnt_seg_bool(*(undefined4 *)param_1, &uStack_b0, 0);
        if (lVar4 == 0) { iVar3 = puVar6[2]; uVar5 = puVar6[3]; }
        else            { iVar3 = puVar6[3]; uVar5 = puVar6[2]; }
        if (iVar3 == param_2) {               // one side matches where we currently are
          /* ... distance-squared; keep the nearest crossing ... */
          iVar7 = 1;
          *param_4 = uVar5;                   // OUTPUT: the other side
          puVar6 = (undefined4 *)puVar6[4];   // next portal
        }
      }
    }
  }
}
```

**Portal record layout, read straight off the code:**

| Offset | Field |
|---|---|
| `+0x00` | point A |
| `+0x04` | point B |
| `+0x08` | **side ID 1** |
| `+0x0C` | **side ID 2** |
| `+0x10` | pointer to next portal (singly-linked list) |

Semantics: if the player's movement segment crosses the portal segment, and `side1` equals
the current side, the crossing point is recorded (nearest wins) and **`side2` is returned**.

Those two side IDs are exactly what an entrance randomizer shuffles. We now know their type
and offset rather than guessing strides inside `.p3d`.

Helper functions also named: `check_if_segs_cross_seg_seg_pnt`,
`is_pnt_right_of_seg_pnt_seg_bool`.

### The endgame gate

`get_gamestage` at `0x001F65D8` calls `get_flag` 25 times and returns **21** when
`ready_for_end` is set. `lenele3a_init` tests it with a single instruction:

```
0x00212274   28420015   slti $v0, $v0, 21
```

⚠️ **Correction from an earlier draft:** the `addiu $v0,$zero,21` that returns the endgame
stage is at **`0x001F6614`**, not `0x001F6608` — that address is a `jal` to `get_flag`, and
patching it would corrupt a function call.

Full output: `F:\rando\S1\notes\ghidra-ee-decompiled.txt`.

---

## 5. The `.p3d` position after all this

Four findings, one of them a useful negative:

1. **Doors are named objects inside the level geometry.** `$Door: "FrontDoor"`,
   `$Door: "Portcullis"` — those names appear verbatim inside the matching `.p3d`, matched in
   **34 of 50 levels**.
2. **`.p3d` is per-object blocks — name, then data, repeated.** Not a header and a table:
   object names span the whole file (Jadetemple runs `0x4F83`→`0x12E72B` across 1.26 MB), and
   a stride scan for a parallel integer array found nothing.
3. **`$Trigger:` is a red herring.** All 3,037 uses are animation timing — `"critical end" 29`,
   `"left-foot" 17`, `"no interrupt" -1`.

   ⚠️ **Corrected 2026-09-20.** That is true for `$Trigger:` in a **character** `.tbl` — and only
   there. In a **level** `.tbl`, `$Trigger:` with `+Id: "load level"` is **the door**: 218 of them,
   destination in the quoted name. The mistake was generalising one file type's meaning to the
   other. See `DOOR-REMAP.md` §1 and `F:\rando\S1\notes\door-mechanism.md`.
4. **There is no level-transition verb in the script layer.** Only `+Level:` (313), which is
   an object's own level ID, not a destination.

So the connection data is geometry- or code-side — and `check_portal_crossing` has now told
us its shape.

---

## 6. What this unlocks

### Next: find who builds the portal list

**Superseded for doors (2026-09-20).** Doors turned out to be a text-layer `$Trigger:` name rewrite,
so this is no longer on the critical path — `DOOR-REMAP.md` §1. It stays documented because it
still describes the `.p3d` record layout question for anything geometry-side.

Something populates the global `puGpffff9930` from level data at load time. That function is
the `.p3d` → portal converter, so reading it settles:

- the `.p3d` record layout, definitively
- whether door destinations are a **geometry** edit or something patchable more cheaply

Search targets: cross-references to `puGpffff9930`, and the level-load path through
`gameplay_unload_level_bool` / `level_script_load_effects` / `is_valid_level_script_filename`.

### Now: the binary layer is built

A second patch class that edits `SLUS_200.74` rather than the script stream, reusing the same
seed and the same size-preserving discipline. It enables:

- **`.data` table shuffling** — 15.9 MB of baked numeric data, currently unreachable
- **code constant patching** — damage multipliers, XP curves, range checks, as immediates
- **portal side-ID shuffling**, once the builder is known
- **reachability for `dcf_*`** if any debug hooks survive in the retail build

See §7 for the patcher itself.

---

## 7. The binary patcher

`tools\summoner-rando\binary.py`. Small, and deliberately paranoid.

| Function | What it does |
|---|---|
| `find_elf(iso)` | locates the executable inside the ISO, returns an `ElfLocation` |
| `_valid_elf(b, off)` | validates by magic + machine type before trusting an offset |
| `va_to_iso_offset(va, loc)` | translates a virtual address to a byte offset in the image |
| `apply_patches(iso, patches)` | applies named patches in place, returns a per-patch report |
| `describe()` | the catalogue, for the UI and `cli.py --list` |

`ElfLocation` carries `iso_offset`, `size`, `entry`, `seg_vaddr`, `seg_offset`,
`seg_filesz`, `machine` — so every translation is derived from the disc's own headers rather
than a hard-coded constant.

A patch is declared, not computed:

```python
@dataclass
class Patch:
    name: str          # the registry key
    va: int            # virtual address to patch
    original: int      # the exact value we EXPECT to find there
    encode: object     # params -> the replacement value
    label: str
    help: str
    params: dict = field(default_factory=dict)
```

**Two safety properties, and they are the whole point of this file:**

1. **Refuse on mismatch.** If the bytes at `va` are not exactly `original`, the patch aborts
   instead of writing. A different disc revision can therefore never be silently corrupted.
2. **Read back after writing.** Every patch is re-read and compared to what it claimed to
   write.

### The first patch, and how we know it worked

`endgame_gate` — lower the gamestage threshold that arms the ending:

```
0x00212274   expects  0x28420015   slti $v0, $v0, 21
              writes  0x28420005   slti $v0, $v0, 5
```

Verified three independent ways:

- read-back of the patched instruction from the written ISO
- **exactly one byte differs** across the whole 1.2 GB image, with sizes identical
- the emulator's own emulog reports a **different game CRC** for the patched disc
  (`13E2774E` → `13E2775E`) — external confirmation that the executable really changed

The third one matters most: it is the emulator agreeing with us, not us grading our own work.

### Known limitation

The current model is **one word at one address**. Door remapping needs an **arbitrary
byte-range data patch** (a permuted table or rewritten strings), and that is a **different
patch class**, not another `Patch` entry — a `TABLES.VPP` range rather than an ELF word.

**The door remap proved the class works without this file.** `F:\rando\S1\notes\apply_door_remap.py`
applied 218 byte-range patches to `TABLES.VPP` with the same discipline and got a clean whole-image
diff (1,679 changed bytes, all inside declared fields) and a boot pass. That script is the
**reference implementation**; folding it into the engine as a `DATA_PATCHES` registry is design
item §7.1 below. See `DOOR-REMAP.md` §3 and §6.1.

### 7.1 The data-patch sibling — design (not yet implemented)

Needed in `tools\summoner-rando\rando_core.py` / `binary.py`: a second registry for edits that are
**not** ELF words. Requirements, inherited from `Binary_Patch`'s two non-negotiables plus two of
its own:

1. **Declare and refuse** — each entry states the exact bytes it expects at its offset; one mismatch
   aborts the whole build and writes nothing.
2. **Read back** — every entry re-read and compared after writing.
3. **Bounds-check the region** — `TABLES_OFF <= off and off + len(expect) <= TABLES_OFF + TABLES_LEN`
   (off-Range edits inside the 7,395,328-byte archive are the only legal targets, for now).
4. **Prove a clean whole-image diff** — the set of changed bytes must be a subset of the fields the
   registry declared. This is the check that caught nothing and therefore means everything.

Entry shape mirroring `door-remap-example.json`:

```json
{"iso_offset": 1231296833, "expect": "catacombs\"", "replacement": "lenele1b\" ",
 "orig_dest": "catacombs", "new_dest": "lenele1b", "src_level_comment": "Wolong-Day"}
```

Still size-preserving by construction: every field is written in place at its original length.

---

## 8. Headless test harness

The emulator can run **with no display**, which is how anything gets verified on this machine
(it is a headless N100). One config value is the entire difference between working and not:

> **`SettingsVersion` in `PCSX2.ini` must be `1`.** Any other value makes PCSX2 pop a modal
dialog at startup and wait forever for a click that can never happen. The symptom is
misleading: the process is *alive*, `Responding=True`, main thread
`WaitReason=UserRequest`, CPU flat at ~0.06 s, and **no `emulog.txt` is ever written** — which
looks exactly like a hang in Qt initialisation. It is not.

```powershell
$env:QT_QPA_PLATFORM = 'windows'
& 'C:\Program Files\PCSX2\pcsx2-qt.exe' -batch -fastboot 'F:\rando\S1\iso\Summoner.iso'
```

### Three config values that matter (2026-09-21)

Beyond `SettingsVersion = 1`, the ini now carries three settings that turned a boot test into a
real test rig. All three live in `%USERPROFILE%\Documents\PCSX2\inis\PCSX2.ini`:

```ini
[EmuCore]
EnablePINE = true        ; live read/write of the emulated PS2's RAM from a Python script
PINESlot = 28011
EnableCheats = true      ; lets a pnach drive the game with no pad (see below)

[EmuCore/GS]
Renderer = 13            ; Software - see the warning below
```

**`Renderer = 13` (Software) is not optional for anything past the boot.** With the default
(Automatic → Vulkan) on this machine the GS device dies in Session 0 every ~30 seconds:

```
[118.4] (SubmitCommandBuffer) vkQueueSubmit failed:  (-4: VK_ERROR_DEVICE_LOST)
[119.4] OSD [GSDeviceLost]: Host GPU device encountered an error and was recovered.
```

PCSX2 recovers by itself, so the boot test still said PASS - but **the game froze**, and that is
invisible from outside unless you look at memory. Whole-EE-RAM churn scan (32 MB, 2 s apart):

| renderer | blocks changed / 31 | game state |
|---|---|---|
| Vulkan (default) | **2** | frozen - level loaded, nothing advances |
| Software | **~25** | live gameplay, player entity walking |

Lesson: *PASS is not running.* The RAM churn scan is how you tell them apart (`churn_scan.py`).

### PINE - the observation channel

`PINEServer` (PCSX2 2.8.1, `pcsx2/PINE.cpp`) speaks a tiny TCP protocol on 28011:

```
request : [u32 total_len][u8 opcode][u32 addr][args...]      total_len = 4 + len(cmd)
reply   : [u32 total_len][u8 result][payload...]             result 00 = OK, FF = FAIL
opcodes : 0..3 read8/16/32/64, 4..7 write8/16/32/64, 8 version, 9 savestate(slot),
          0xA loadstate(slot), 0xB title, 0xC id, 0xE gamever, 0xF status
```

`ParseCommand` loops over the request buffer, so **hundreds of reads can be batched into one
round trip** - that is what makes a 32 MB scan take ~45 s instead of forever. Client:
`F:\rando\S1\notes\pine.py` (also `probe_live.py`, `door_brute.py`, `door_push.py`,
`watch_state.py`, `churn_scan.py`).

### The test-only autoplay pnach

Headless has no pad. To get **into gameplay with no input at all**, patch the game's own input
queries in RAM (`cheats/<CRC>.pnach`, CRC 13E2774E for retail Summoner):

```
ngps_input_button_pressed      @ 0x0011AAC0 -> addiu v0,zero,1 ; jr ra ; nop
ngps_input_button_just_pressed @ 0x0011AB30 -> addiu v0,zero,1 ; jr ra ; nop
```

**An unlabelled pnach group is auto-enabled** (`Patch::EnablePatches`:"For compatibility, we
auto enable anything that's not labelled") - a `[name]` header needs an entry in
`[Cheats] Enable = [...]`, an unlabelled block does not. Verified by reading the patched words
back out of EE RAM through PINE. With it the game walks the frontend by itself and loads level
`masad` in ~20 s. Remove the file (or set `EnableCheats = false`) for vanilla behaviour.

The native Qt `windows` plugin works fine in Session 0 — invisible windows are still real
windows. A passing run looks like this:

```
[ 0.3264] BIOS Found: USA v01.20(02/09/2000)  Console 20000902-234318
[ 0.3867] Disc changed to Summoner.iso.  Serial: SLUS-20074  CRC: 13E2774E
[ 2.8948] VM subsystems initialized in 2568.77 ms
[11.1634] ELF cdrom0:\SLUS_200.74;1 ... is executing.
```

### Harnesses (`F:\rando\S1\notes\`)

| File | Purpose |
|---|---|
| `pcsx2_headless_boot.ps1` | sets the env var, preflight-fixes `SettingsVersion`, runs with a timeout, samples CPU, keeps a copy of emulog, prints **PASS/PARTIAL/FAIL** |
| `pine.py` | **PINE client** - read/write EE RAM, batching, savestate save/load, `lvlwatch` |
| `watch_state.py` | poll `Level_data.name` + trigger count + RAM churn (is the game actually running?) |
| `churn_scan.py` | whole-32 MB churn scan - the difference between "booted" and "running" |
| `probe_live.py` | dump `Main_entity`/`Main_player` pointers, floats, watch a position |
| `door_push.py` / `door_brute.py` | drive the player's position and hunt for a door crossing |
| `pcsx2_ctl.ps1` / `post_keys.ps1` | window enumeration, PrintWindow capture, SendInput/posted-key injection (see below) |
| `iterate.ps1` | the iteration rig: **build → whole-image byte diff → boot → one verdict** |
| `pcsx2-headless-FINDINGS.md` | full write-up, probe scripts, and the dead ends |
| `gui_on_winsta.ps1`, `win_sta.ps1`, `capture_window.ps1` | window-station and window-capture experiments (kept for the record) |

The rig uses a compiled C# helper for the byte diff — a PowerShell elementwise loop over
1.2 GB is unusably slow. It also flags any transform whose report shows `changed=0`
("CHANGED NOTHING"), which is how a silently-dead transform gets caught.

### Dead ends — do not retry

- **`QT_QPA_PLATFORM=offscreen` cannot work on this build.** PCSX2 2.8.1 creates a real GS
  device and swapchain for *every* renderer including Null, and an offscreen platform supplies
  no native HWND: `MonitorFromWindow() failed: 1400` → `vkCreateSwapchainKHR failed`.
- **Attaching to `WinSta0\Default` is unnecessary.** We start in `Service-0x0-3e7$` and can
  open `WinSta0`, but `SetThreadDesktop` fails `err=170 ERROR_BUSY`, and forcing the child onto
  the desktop via `lpDesktop` still stalls at `Missing top level window`.
- **`-nogui` is not needed**, and it makes `-testconfig` write nothing at all.
- **An absolute path in `[Filenames] BIOS` is silently rejected** — PCSX2 falls back to a
  *Japan* dump. Use a **bare filename**.
- A fresh `-datapath` writes to `<datapath>\PCSX2\...`, i.e. a **subdirectory**, not the root.
  Looking in the wrong place reads as "it created nothing".

### Window/input work that does NOT work here

- **PrintWindow on the GS window returns pure black.** Both the Qt top-level and the display
  widget capture as a uniform black bitmap - there is no DWM composition in Session 0, so the
  Vulkan/GS surface is not capturable. No screenshots of the game this way.
- **`SendInput` is useless without a foreground window.** `GetForegroundWindow()` is `0` in
  Session 0, so focus can never be established (`SetForegroundWindow` → False).
- **Posted `WM_KEYDOWN` does nothing observable** - even with a faked
  `WM_ACTIVATE`+`WM_SETFOCUS`, and even targeted at both the top-level and the display widget:
  no PCSX2 hotkey fired (F8 screenshot wrote no file), no emulog line, no game reaction.
- Therefore: **do not spend time on host input.** Drive the *game* with a pnach + PINE writes
  instead (above).

### What PASS does and does not mean

PASS means **the BIOS loaded, the disc was read, and the boot ELF is executing** — with steady
CPU, not a spinning stub. It does **not** mean the game is playable, and it does **not** even
mean the game is *running*: a Vulkan device-lost every 30 s passes the boot test and freezes the
game (see the renderer table above). Run `churn_scan.py` before believing any PASS.

---

## 9. Rules for this layer

- **Size-preserving, same as the text layer** — 4-byte instruction and field swaps only,
  unless and until the archive-slack question is resolved.
- **Byte-exact targets only.** `vaddr - 0xFF000`. A wrong address corrupts a live call —
  the `0x1F6608` vs `0x1F6614` mix-up is the cautionary tale.
- **Types are inference, control flow is fact.** Ghidra emits `undefined4` / `uStack_c0`
  everywhere because the binary has no type info. Trust the structure and the branching;
  double-check the widths before patching.
- **Refuse-on-mismatch is mandatory** for every patch. Declare the expected original; never
  write blind.
- **Data-layer edits are a separate class from ELF edits** — same discipline, different offsets
  (§7.1). Never route a `TABLES.VPP` byte range through the ELF registry.
- **Boot-verified is not play-verified.** The binary layer's patches boot; none have been
  played. Say so rather than implying more.
