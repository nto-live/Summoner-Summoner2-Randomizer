# How Summoner (SLUS-20074) loads a new level when you walk through a door

Workstream: randomizer — door destinations.
Disc: `F:\rando\S1\iso\Summoner.iso` (read-only). ELF: `SLUS_200.74` @ ISO `0x11DBE000`.
All addresses below are EE virtual addresses (Ghidra base `0x00100000`); ISO byte offsets are absolute.

---

## 0. Headline

**A "door" that changes level is a `#Triggers` block in the level's object table
(`<level>.tbl`, a text file packed inside `TABLES.VPP`).  Its destination is the trigger's
*name*:**

```
#Triggers

$Trigger: "catacombs"          <-- the DESTINATION LEVEL NAME (inline, <=32 bytes)
    +Id: "load level"          <-- trigger type; index 0 of {"load level","boss","sound"}
    +Index: 1                  <-- player start id used in the destination level
    +Type: "spline"            <-- geometry mode: "spline" | "location"
    +Spline name: "$loadarea01"    (mode "spline")  the load-area mesh you must cross
    +Location: "$khosani"          (mode "location") navpoint
    +Radius: 1.2                   (mode "location") radius around that navpoint
```

The engine resolves the trigger name through the **51-entry level table `Level_info`** to get a
level index, and it builds the destination's asset filenames from the **same name string**.
So **rewriting that one quoted string is a complete, consistent, size-preserving redirect of a
door.**  That is the recommended patch (see §5).

**What the previous workstream had was a red herring.**  `level_save_game_data::set_pending_load`
is real, and it really does have exactly one call site (`0x0023919C`, inside
`ngps_loadsave_post_render_checks`, the save/load menu) — but that is the **save-game load**
path, not doors.  Doors never call it.  (Raw `jal` scan, whole segment: exactly 1 call site.)

---

## 1. The chain, door → new level

```
walk into a load area
   │
   ├─ level_script_check_level_load_void()          @ 0x002023C0   (called every frame)
   │     for i in 0 .. Num_level_triggers-1:                      Num_level_triggers @ 0x12844FC
   │        rec = (Level_triggers) + i*100                        Level_triggers     @ 0x1238B78
   │        if rec+0x48 != 0: continue          ; "+Id:" id, 0 = "load level" (active)
   │        if rec+0x58 != -1 and rec+0x58 != player+0x698: continue   ; room filter
   │        if rec+0x4C == 0:   ; "+Type: spline"  -> segment-crossing test
   │              segment = *(rec+0x5C) + 8, len 12   ; door mesh spline
   │              if test_crossing(player path, segment) and inside(mesh):
   │                  if (rec+0x54 & 2) == 0:  goto FOUND       ; flags: parse sets 1
   │                  else: level_script_do_clicked(rec+0x24)  ; run a scripted trigger
   │        else:               ; "+Type: location" -> radius test
   │              nav = *(rec+0x5C) ; radius = *(float*)(rec+0x60)
   │              if dist2(player, nav+0x14) <= radius^2 and inside(mesh):
   │                  if (rec+0x54 & 2) == 0:  goto FOUND
   │                  else: level_script_do_clicked(rec+0x24)
   │
   ├─ FOUND:  (raw disasm 0x00202760-0x002027A4)
   │        uGpffffb228 = 0                       ; "other players nearby" flags
   │        iGpffffb218 = &Level_triggers + i*100 ; -> pending DESTINATION NAME = rec+0x00
   │        iGpffffb21c = *(rec+0x20)             ; -> pending SCRIPT FILENAME
   │        iGpffffb220 = *(rec+0x50)             ; -> pending START ID  ("+Index:")
   │
   └─ level_script_do_frame_void()                  @ 0x00203378   (called every frame)
         if (iGpffffb218 != 0 && iGpffffb224 != 0):
             strcpy(0x1245450, 0x1245410)   ; save previous level name
             strcpy(0x1245410, iGpffffb218) ; Level_data.name   = destination level name
             strcpy(0x1245430, uGpffffb21c) ; Level_data.script = destination script
             DAT_012454b4 = uGpffffb220     ; Level_data.start id
             uGpffffba38 = 6; uGpffffba3c = 1     ; request game-state 6 = load level
                                        │
                                        ▼
             gameplay_init / os_load_busy_ngps  @ 0x0021AA68  (gameload.o)
               builds "<Level_data.name>.s3d" -> s3d_load (0x001DA6D0) -> "<...>.p3d"
               level_script_load()  @ 0x001E9970
                   iGpffffaa28 = level_script_get_level_index(Level_data.name)  ; -> index 0..50
                   -> Level_info[iGpffffaa28] gives per-level init/do_frame/close fn ptrs
                   -> load_level_script_file() @ 0x00203FC8 reads "<Level_data.name>_script.tbl"
```

Call sites (raw `jal` scan of the whole loadable segment, so these are exhaustive):

| function | address | callers |
|---|---|---|
| `level_script_check_level_load` | `0x002023C0` | `level_script_do_frame` `0x002033F4` |
| `level_script_do_frame` | `0x00203378` | `0x00217AF0`, `0x00217B34`, `0x00217B74` |
| `level_script_load` | `0x001E9970` | `0x0021ABB4` (in `os_load_busy_ngps`) |
| `load_level_script_file` | `0x00203FC8` | `0x00203144` (in `level_script_load_common`) |
| `level_script_get_level_index` | `0x001EAD28` | 16 sites (0x1E2638, 0x1E6CE8, 0x1E99A4, 0x1E9AAC, 0x1EACCC, 0x1ECB48, 0x1ECC18, 0x1EF428, 0x1F4A70, 0x2010AC, 0x20186C, 0x20320C, 0x21DFAC, 0x220AA4, 0x227594, 0x2296AC) |
| `level_save_game_data::set_pending_load` | `0x001F5DD0` | `0x0023919C` **only** (save/load menu) |
| `level_script_ask_level_load(char*,char*,int)` | `0x002029D8` | **none — dead code** |
| `select_new_game(char*,char*)` | `0x0021DF90` | 7 sites (all menu/cutscene: 0x217300, 0x2275D4/0x22764C/0x227694, 0x2281A8, 0x22983C, 0x2391C0) |

### Where the trigger records come from

`FUN_002019F0` (parses `<Level_data.name>.tbl` — it formats the name then `strcat ".tbl"`,
`.tbl` = `0x1284460`) dispatches the sub-blocks.  `#Triggers` = `0x1273668` is dispatched to:

**`FUN_00200FE8` @ `0x00200FE8` (784 bytes) — the `$Trigger:` parser.**  Decompiled:

```c
puVar5 = &Level_triggers;                       // 0x1238B78
do {
  lVar4 = parse_check_for(p, 0x1273468);        // "$Trigger:"
  if (!lVar4) return;
  *(u32*)(puVar5 + 0x54) = 1;                   // flags = 1  (bit1 clear => "level change")
  Num_level_triggers++;                         // counter iGpffffb20c, loop bound in check_level_load
                                                // (max 32 records: 3200 B / 100)
  parse_string(p, puVar5, 0x20, '"','"');       // >>> record+0x00 = DESTINATION LEVEL NAME (<=32 B)
  parse_required(p, 0x1284408);                 // "+Id:"
  *(u32*)(puVar5 + 0x48) = parse_type_from_list(p, list_0x12389a8, 3);  // 0="load level",1="boss",2="sound"
  if (*(u32*)(puVar5+0x48) == 0) {              // "load level"
      script = parse_check_for(p,0x1273478 /*"+Script:"*/) ? read_string() : /*default =*/ trigger_name;
      lvl    = level_script_get_level_index(puVar5);        // name -> 0..50  (ngps_stricmp)
      si     = level_script_get_level_script_index(lvl, script);
      *(u32*)(puVar5 + 0x20) = Level_script_info[si*0x10 + lvl*0x70];  // script filename ptr
      *(u32*)(puVar5 + 0x24) = "+RefName:" ? read_string() : trigger_name;   // inline 32 B
  }
  *(u32*)(puVar5 + 0x50) = 0;                   // default "+Index:" = 0
  if (parse_check_for(p,0x1284410 /*"+Index:"*/)) *(u32*)(puVar5+0x50) = parse_int(p);
  parse_required(p, 0x1284418);                 // "+Type:"
  *(u32*)(puVar5 + 0x4C) = parse_int_list(p, gp+..., 2);   // 0 = spline, 1 = location
  *(u32*)(puVar5 + 0x58) = 0xffffffff;          // "+Plane:" / room, default -1
  if (parse_check_for(p,0x1284420)) *(u32*)(puVar5+0x58) = parse_int(p);
  if (mode == 1) {                              // "+Type: location"
      parse_required(p, 0x12734d0);             // "+Location:"
      *(u32*)(puVar5+0x5C) = find_navpoint(read_string());      // navpoint ptr
      parse_required(p, 0x12734e0);             // "+Radius:"
      *(u32*)(puVar5+0x60) = parse_float(p);
  } else {                                      // "spline"
      parse_check_for(p, 0x1273498);            // "+Spline name:"
      *(u32*)(puVar5+0x5C) = s3d_get_door_from_spline_name(name);
  }
  puVar5 += 100;                                // next record
} while (true);
```

### `Level_trigger` record layout (stride **100** = 0x64, array `0x1238B78`, max **32**)

| off | type | meaning |
|---|---|---|
| `+0x00` | `char[0x20]` | **destination level name (inline)** — the `$Trigger:` string |
| `+0x20` | `char*` | destination script filename pointer (into `Level_script_info`/script pool) |
| `+0x24` | `char[0x20]` | refname (`+RefName:`), used by `level_script_do_clicked` |
| `+0x48` | `int` | `+Id:` id — 0 = "load level" (active), 1 "boss", 2 "sound" |
| `+0x4C` | `int` | `+Type:` — 0 = spline, 1 = location |
| `+0x50` | `int` | `+Index:` player start id |
| `+0x54` | `u32` | flags (parser writes 1; `flags & 0x2` set = run script instead of level change) |
| `+0x58` | `int` | `+Plane:` / room filter, -1 = any |
| `+0x5C` | `void*` | door mesh (spline) or navpoint |
| `+0x60` | `float` | `+Radius:` (location mode) |

Globals: `Level_triggers @ 0x1238B78`, `Num_level_triggers @ 0x12844FC`.
Neighbours: `Level_effects @ 0x12389E8` (stride 0x28, 10), `Level_shopkeepers @ 0x12397F8`,
`Level_clicks @ 0x1239928`.

---

## 2. Level identity: name **and** index, and they are coupled to the *name*

* `Level_info @ 0x1213E68`, **51 records × 0x3C bytes**, field `+0x00` = `char*` level name.
  Fields `+0x04,+0x08,+0x0C,+0x10,+0x14` are per-level function pointers (init / do_frame /
  close / …) and `+0x18` is a size.  (e.g. `Level_info[4]` = "worldmap1" with
  `0x00200760 worldmap_init`, `0x00200990 worldmap_do_frame`, `0x00200B08 worldmap_close`.)
* `level_script_get_level_index(name) @ 0x001EAD28` (108 B) — case-insensitive (`ngps_stricmp`)
  linear search of `Level_info[i].name`, returns `i` or `-1`, bounded `i < 0x33` (51).
  Decompiled body:
  ```c
  ppuVar3 = &Level_info;  iVar2 = 0;
  do { if (!ngps_stricmp(param_1, *ppuVar3)) return iVar2;
       iVar2++; ppuVar3 += 0xf; }        // 0xf dwords = 0x3C bytes
  while (iVar2 < 0x33);
  return -1;
  ```
* `Level_script_info @ 0x121EB70`, 51 records × 0x70, filled at runtime by
  `level_script_load_script_filename_table @ 0x001EAAF8` from the disc file
  **`script_filenames.tbl`** (`$Level:` / `+Script:` / `+Dialogue:` / `+Levelcap:`).
  Record[j] = up to 7 `char*` script filenames at `+0x00,+0x10,…,+0x60` (stride 0x10).
* `Level_data @ 0x1245410` (a plain struct, not `Level_info`):
  `+0x00 char name[0x20]`, `+0x20 char script[0x20]`, `+0x40 char prev_name[0x20]`
  (i.e. absolute `0x1245410`, `0x1245430`, `0x1245450`), `+0x174` = "is town" flag
  (`#Town` in the level file).
* **The name drives asset filenames.** Verified in `os_load_busy_ngps`:
  `0x0021AA90 lui r16,0x124 / addiu r16,r16,0x5474 ; r17 = r16-100 = 0x1245410 (Level_data)`
  then `0x0021AAC8 jal 0x00123620` with `a1 = Level_data` and `a2 = 0x1284CC8` (`".s3d"`),
  then `0x0021AAE4 jal 0x001DA6D0` (the s3d loader, which itself formats `".p3d"` at
  `0x1DA708`).  And `FUN_002019F0` formats `"<Level_data.name>.tbl"`.
  The *index* (`iGpffffaa28`) selects `Level_info[i]`'s per-level init/close pointers and the
  save-game level slot.

---

## 3. Level inventory (all 51 entries of `Level_info`)

Format: `idx  name  (len)  name-string vaddr`.  Stored `char*` values (4-byte, in `.data`
`0x1213E68 + i*0x3C`); most name strings live in a contiguous block `0x126FA60..0x126FD58`,
five in `.sdata` `0x1283D20..0x1283D58`.

```
 0  Wolong              ( 6) 0x1283D20
 1  Catacombs           ( 9) 0x126FA60
 2  test                ( 4) 0x1283D28
 3  masad               ( 5) 0x1283D30
 4  worldmap1           ( 9) 0x126FA70
 5  lenele1b            ( 8) 0x126FA80
 6  lenele1c            ( 8) 0x126FA90
 7  lenele1d            ( 8) 0x126FAA0
 8  lenele1e            ( 8) 0x126FAB0
 9  sewer               ( 5) 0x1283D38
10  rand-hills01        (12) 0x126FAC0
11  IkaemosBottomInt    (16) 0x126FAD0
12  IkaemosTopInt       (13) 0x126FAE8
13  IkaemosExt          (10) 0x126FAF8
14  KhosaniLab          (10) 0x126FB08
15  IonaExt             ( 7) 0x1283D40
16  WolongCaverns       (13) 0x126FB18
17  TempleInt           ( 9) 0x126FB28
18  rand-forest01       (13) 0x126FB38
19  rand-forestnite1    (16) 0x126FB48
20  Liangshan           ( 9) 0x126FB60
21  Rand-Desert         (11) 0x126FB70
22  IonaExt02           ( 9) 0x126FB80
23  KhosaniStrng        (12) 0x126FB90
24  LPalaceInt          (10) 0x126FBA0
25  tancredhouse        (12) 0x126FBB0
26  LPalaceInt02        (12) 0x126FBC0
27  KhosaniLab2         (11) 0x126FBD0
28  Wolong2             ( 7) 0x1283D48
29  eleh                ( 4) 0x1283D50
30  lenele2aa           ( 9) 0x126FBE0
31  lenele2ab           ( 9) 0x126FBF0
32  lenele3a            ( 8) 0x126FC00
33  lenele3d            ( 8) 0x126FC10
34  jadetemple          (10) 0x126FC20
35  lenele1aa           ( 9) 0x126FC30
36  lenele1ab           ( 9) 0x126FC40
37  TempleInt2          (10) 0x126FC50
38  IkaemosExt2         (11) 0x126FC60
39  IkaemosBottomInt2   (17) 0x126FC70
40  Rand-HillsNite01    (16) 0x126FC88
41  Rand-Iceland01      (15) 0x126FCA0
42  Rand-Grassland01    (16) 0x126FCB0
43  Rand-Orenia01       (13) 0x126FCC8
44  Rand-OreniaNite01   (17) 0x126FCD8
45  Rand-DesertNite01   (17) 0x126FCF0
46  Rand-GrasslandNite01(20) 0x126FD08
47  Rand-IcelandNite01  (17) 0x126FD20
48  endgame             ( 7) 0x1283D58
49  lenele2d            ( 8) 0x126FD38
50  sewerboss           ( 9) 0x126FD48
```

(Note: matching is `ngps_stricmp`, i.e. **case-insensitive** — `$Trigger: "catacombs"`
matches `Level_info[1].name == "Catacombs"`.  Case is therefore free to change.)

### Door inventory (measured, not guessed)

Scanning `TABLES.VPP` (ISO `0x49086800`, size 7,395,328; extracted copy is byte-identical to
the ISO slice — verified): **218** `$Trigger:` blocks with `+Id: "load level"`, **41** distinct
destinations.  `+Type:` = 196 spline / 22 location.  `+Index:` distribution = {1:64, 2:35,
3:73, 4:10, 5:11, 6:10, 7:6, 8:5, 9:4}.  118 of 218 blocks carry an explicit `+Script:`.
Full machine-readable list (ISO offset, source level, original destination, index, type,
spline/navpoint, radius, script) is in **`door-triggers.json`** next to this file.

Distinct destinations with length and substitution head-room (legal targets = `Level_info`
names with `len <= len(orig)`, excluding self):

```
"eleh"              4   x1    -> 0 legal   (only itself; effectively unpatchable)
"sewer"             5   x9    -> 3   (eleh, masad, test)
"masad"             5   x1    -> 3
"wolong"            6   x2    -> 4
"ionaext"           7   x2    -> 7
"wolong2"           7   x3    -> 7
"lenele1d/1b/1c/1e/2d/3d/3a" 8  x44 -> 14
"catacombs/worldmap1/lenele1ab/lenele1aa/templeint/lenele2ab/lenele2aa/sewerboss/ionaext02/liangshan" 9 x125 -> 24
"IkaemosExt/KhosaniLab/lpalaceint/templeint2/LPalaceInt/ikaemosext/jadetemple" 10 -> 29
"IkaemosExt2/KhosaniLab2/ikaemosext2" 11 -> 32
"KhosaniStrng/tancredhouse/lpalaceint02/khosanistrng" 12 -> 36
"IkaemosTopInt/wolongcaverns" 13 -> 40
"IkaemosBottomInt" 16 -> 45
"IkaemosBottomInt2" 17 -> 48
```

---

## 4. Where the data physically lives

`TABLES.VPP` is a plain (uncompressed) packfile; its members contain the `<level>.tbl` text
files.  Destination strings are ordinary ASCII inside those members.

| example | TABLES.VPP off | ISO off | bytes present |
|---|---|---|---|
| Wolong-Day → catacombs | `0x005BB141` | `0x049641941` | `catacombs` |
| Catacombs → ionaext | `0x006CCB09` | `0x049753309` | `ionaext` |
| Eleh → worldmap1 | `0x006CD2DF` | `0x049753ADF` | `worldmap1` |
| worldmap → wolong | `0x00757C19` | `0x049793619` | `wolong` |

`iso_offset = 0x49086800 + vpp_offset`.  All 218 offsets are in `door-triggers.json`
and `door-remap-example.json`.

---

## 5. Patch strategies evaluated

### (a) Pointer/array permutation — **RULED OUT (it does not do what it looks like)**

`Level_info[i].name` is a 51-entry `char*` array of 4-byte pointers at
`0x1213E68 + i*0x3C`, so permuting it *is* size-preserving and byte-cheap.  **But it does not
redirect doors.**  The destination level is *not* chosen by the resolved index — it is chosen by
the *name string*:

* `Level_data.name` (`0x1245410`) is `strcpy`'d from the trigger's name inside
  `level_script_do_frame` (`strcpy(0x1245410, iGpffffb218)` — the block just after the
  `level_script_check_level_load` call at `0x002033F4`), and that string is what
  `os_load_busy_ngps` turns into `<name>.s3d` / `<name>.p3d` (`0x0021AAC8`, `0x001DA708`)
  and what `FUN_002019F0` turns into `<name>.tbl`, and `load_level_script_file` into
  `<name>_script.tbl`.
* The index only selects `Level_info[i]`'s per-level init/do_frame/close pointers and the
  save slot.

So permuting `Level_info[i].name` merely re-points names at other entries' function
sets while the level actually loaded stays the one named by the requested string.
⇒ It is a **no-op for destination randomisation** and a desynchroniser for everything else.
Do not use it.

### (b) In-place destination-name rewrite — **AVAILABLE, RECOMMENDED**

Rewrite the quoted destination inside the `$Trigger:` line, in place, in `TABLES.VPP` on the
disc (or in an extracted-and-repacked copy).  Size-preserving by construction; no VPP header
change; no ELF change.

**Exact byte recipe.**  For a block whose name field currently occupies
`[off, off+len(orig))` with the closing `"` at `off+len(orig)`:

* write `new_name` at `off`
* write `"` (0x22) at `off+len(new_name)`
* fill `off+len(new_name)+1 .. off+len(orig)+1` with `0x20` (spaces)

Total bytes written = `len(orig)+1` — **identical length**.  The parser
(`parse_parse_string`, `0x00126D38`, quote char `0x22`) reads up to the first `"`, and the
parser is whitespace-tolerant, so the trailing spaces are inert.  (`+Index:` also becomes a
valid rewrite target if needed — it is a plain decimal read by `parse_parse_int`, and can be
padded with a space to the left/right if a narrower value is wanted.)

Worked examples (expected byte string → replacement byte string, `"` included):

```
0x049641941  'catacombs"'  ->  'lenele1b"'        (same length)
0x049753309  'ionaext"'    ->  'Wolong2"'         (same length)
0x049753ADF  'worldmap1"'  ->  'masad"    '       (5 chars + quote + 4 spaces)
0x049754E8E  'IkaemosTopInt"' -> 'rand-forest01"' (same length)
0x049754EFA  'IkaemosTopInt"' -> 'lenele1e"     ' (9 + quote + 5 spaces)
```

**Constraint:** a target name must be **≤ the original length** *and* a real `Level_info`
name (otherwise `level_script_get_level_index` returns -1 and `Level_script_info[-1*0x70 + …]`
reads garbage — crash).  The length head-room table is in §3.

**Two caveats to honour in the randomizer, both mechanical:**

1. **`+Index:` must be valid in the destination.**  `level_script_set_player_starts`
   (`0x00202A80`) looks up navpoints `"$player%d-%02d"` (or `"$player%02d"`) using the
   `+Index:` value and the destination's own navpoint list; on failure it enters
   `do { Debug_error(...) } while(true);`.  Either restrict targets per index (each
   destination's valid indices are visible in the `<level>_script.tbl` `#Navpoints`), or
   rewrite `+Index:` alongside the name (see recipe above).
2. **`+Script:` default.**  If a block has no `+Script:`, the script is the trigger name;
   `level_script_get_level_script_index(level, name)` (`0x001EAD98`) then searches
   `Level_script_info[level][0..6]` (`ngps_stricmp`) and returns `-1` if absent, after which
   `*(Level_script_info + -0x10 + level*0x70)` is dereferenced.  So when rewriting a block
   that has **no** `+Script:`, restrict the target to levels whose base script filename equals
   the level name (true for the shipped data — all 100 such blocks rely on it), or rewrite the
   `+Script:` string too.

**Harness form.**  `binary.py`'s `PATCHES` registry is 4-byte-word/ELF only, so this does not
drop in verbatim.  The natural extension is a sibling registry with the same discipline —
explicit expected bytes, refuse on mismatch, verify by read-back:

```python
# proposed binary.py addition (do NOT edit binary.py; reported for the owner)
DATA_PATCHES = {
    # one entry per door trigger, generated from door-triggers.json
    # "door_<i>": DataPatch(
    #     iso_offset=0x049641941,
    #     expect=b'catacombs"',          # name + closing quote
    #     replacement=b'lenele1b"'),     # same length; pad with b' ' after the quote
}
def apply_data_patches(iso, patches):
    with iso.open("r+b") as fh:
        for off, expect, repl in patches:
            assert len(expect) == len(repl)
            fh.seek(off); before = fh.read(len(expect))
            if before != expect: refuse(...)
            fh.seek(off); fh.write(repl); fh.flush()
            fh.seek(off); assert fh.read(len(repl)) == repl
```
A ready-to-feed example set of all 218 patches (seed 1) is in
`door-remap-example.json` (`iso_offset` / `expect` / `replacement`).

### (c) Code patch / hook — **AVAILABLE, not needed, and riskier than it looks**

The natural hook is the `$Trigger:` parser `FUN_00200FE8 @ 0x00200FE8`.  Byte-exact sites:

| vaddr | word | instruction | note |
|---|---|---|---|
| `0x00201038` | `0x0C049B4E` | `jal 0x00126D38` | parse the destination name into `record+0x00`; delay slot `0x0020103C` = `addiu r8,r0,0x22` |
| `0x00201068` | `0xAE420048` | `sw r2,0x48(r18)` | stores `+Id:` id into `record+0x48` |
| `0x002010AC` | `0x0C07AB4A` | `jal 0x001EAD28` | `level_script_get_level_index(record)`, `a0 = r18 = record` |

A `j`-trampoline over `0x00201038` (`→` cave: `jal 0x00126D38`, `nop`, overwrite
`record+0x00` with a permuted 32-byte name chosen off `Num_level_triggers`
`0x12844FC`, `j 0x00201040`) is mechanically sound — **but hooking `0x002010AC` to permute the
returned index is wrong** for the same reason as (a): the name (and hence the asset filenames)
would not change.  The hook must rewrite the *name*.

Slack: the loadable segment is riddled with zero runs.  Largest: **14,384,448 bytes at vaddr
`0x0044B190`**, then 339,768 B @ `0x003AF030`, 320,397 B @ `0x002C2B54`, 315,432 B @
`0x00275A30`.  Caveat: these live inside the loaded image, above the ~2.9 MB of real code
(`.text` ends `0x0026F783`), so they are almost certainly zero-initialised data/heap at
runtime; parking code there is not guaranteed safe.  The tail of `.text` between the last
function and `0x0026F783` is a safer (smaller) option.

Because (b) achieves an arbitrary per-door remap with zero code injection, **do not use (c)**.

---

## 6. Recommendation (one paragraph)

Rewrite the `$Trigger:` destination strings in `TABLES.VPP` in place (option **b**).  Build a
per-door permutation over the 218 blocks listed in `door-triggers.json`, restricted so that
`len(new) <= len(old)` and `new ∈ Level_info`, enforce a valid `+Index:` (or rewrite it), and
for the 100 blocks without `+Script:` restrict targets to levels whose base script equals the
level name.  Each edit is `name + '"' + spaces` padded to `len(old)+1` bytes, so the VPP and
ISO sizes never change and the patch is trivially reversible (record the original bytes; the
harness's expected-bytes check already guards against the wrong disc revision).
Option (a) is a no-op; option (c) is possible but unnecessary and touches runtime-heap space.

---

## 7. Corrections to the brief (verified negatives)

* `level_save_game_data::set_pending_load` is the **save-game** load funnel (1 call site at
  `0x0023919C` in the save/load UI, copying `Savegames[slot]`), **not** the door path.
* `level_script_ask_level_load(char*,char*,int)` @ `0x002029D8` exists, has the right shape,
  and **is never called** — dead code.
* `+Action:` / `$Trigger:` in *character* `.tbl` files (`Joseph.tbl`, `eleh.tbl`, …) are
  **animation triggers** (`$Trigger: "left-foot" 17`), exactly as the brief said — those are
  a different, unrelated `$Trigger:` (parsed by `script_internal.cpp`, `0x1EC918`).
  The level-change `$Trigger:` is the one inside a `#Triggers` block of a `<level>.tbl`.
* `+Trigger:` (object attribute, `parse_object` @ `0x001EC918`, string at `0x1270370`) is
  **conditional NPC spawn** (`+Trigger: "ionaext02" "luminar_intro"` = spawn this NPC only if
  flag `luminar_intro` is set for level `ionaext02`).  Not a door.
* Portal records / `check_portal_crossing` / `door_is_open` / `s3d_*_door_*` are
  visibility, pathing, and the physical door open/close animation — confirmed unrelated.

## 8. Scratch scripts (all in `F:\rando\S1\notes\`)

`_door_decomp.py` `_door2.._door10.py` (Ghidra decompiles / listings, forced disassembly of
regions Ghidra left unanalysed), `_jalscan.py` `_jaltargets.py` (raw `jal` caller scans),
`_addrscan.py` `_addrscan2.py` `_addrfind.py` (LUI/ADDIU data-ref scans), `_elfdump.py`
`_dumplevels.py` `_trig_dump.py` `_doors_dump.py` `_vpptrig.py` `_trigblock.py` `_sf.py`
`_sf2.py` (disc parsing), `_iso_dir2.py` (ISO9660), `_doors_all.py` `_doors_src.py`
`_doorexport.py` `_remapgen2.py` `_final.py` `_p3d.py` `_p3d_dis.py` `_mkfn.py` `_lvlidx.py`.

Machine-readable outputs: `door-triggers.json` (218 doors), `door-remap-example.json`
(218 concrete byte patches, seed 1).

---

## 9. RESULT (2026-09-20 22:10) - the patch is applied and the disc boots

The recommended patch (b) was applied for real, to a copy, and then booted. This section is the
outcome; sections 1-8 above are unchanged and still describe the mechanism.

**Tooling:** `apply_door_remap.py` (applier), `_remapgen2.py` (mapping generator),
`door-remap-example.json` (the 218 concrete patches), `verify_doors.py` (independent read-only
verification of this file's claims).

**Applied:** 218 patches / 41 distinct original destinations -> 31 new, 142 distinct mappings /
2,167 field bytes / 1,679 bytes actually different.

```
patches in file: 218
validated: 218   refused: 0
size: src=1,232,699,392  dst=1,232,699,392  MATCH=True
readback mismatches: 0
differing bytes: 1679
diffs outside a patched field: 0   <- clean
```

Every patch was validated against the SOURCE disc (refuse-on-mismatch, bounds-checked against the
TABLES.VPP region at ISO 0x49086800 +7,395,328), written, re-read, and then the whole 1.2 GB image
was diffed to prove nothing else moved. The source disc was never opened for write.

**Booted:** `F:\rando\S1\out\test-doors.iso`

```
test-doors.iso   PASS   cpu=28.5s/90s   rss=879MB   thr=17   CRC 13E2774E   err: none new
[    3.3091]   Serial: SLUS-20074
[   17.9135]   ELF cdrom0:\SLUS_200.74;1 with entry point at 0x00100008 is executing.
```

The CRC stays 13E2774E - identical to vanilla, because only TABLES.VPP changed. It shifts to
13E2775E only when SLUS_200.74 changes (the endgame_gate disc). That is the emulator independently
confirming the edits landed in the data layer and nowhere else.

**Still unproven (do not overclaim):**

1. No door has been walked through - headless emulation has no pad input.
2. The `+Index:` hard-loop caveat is untested. It would pass this boot test and still be broken.
3. Reachability is unchecked: nothing here says a remapped destination is a sane place to land.

Next: get into gameplay so a crossing is observable - CDVD file-read logging is the cheapest route,
since a level load shows up as disc reads. Then the reachability guard. Full app-side record:
`tools\summoner-rando\DOOR-REMAP.md`.
