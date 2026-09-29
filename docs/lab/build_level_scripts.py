r"""Parse the AUTHORITATIVE script_filenames.tbl inside TABLES.VPP and emit docs/lab/level_scripts.json.

WHY: A door with NO explicit `+Script:` uses its destination NAME as the script name
(door-mechanism.md 5b caveat 2). The engine then calls level_script_get_level_script_index(level, name)
@ 0x001EAD98, which searches that level's script list (Level_script_info) with ngps_stricmp and
returns -1 if absent -> "Exit to Unknown" bounce. So a no-script door can only SAFELY target a
level whose BASE (first-listed) `+Script:` equals the level name (case-insensitive).

script_filenames.tbl format (verified, door-mechanism.md 2):
    $Level:   "name"
    +Script:  "scriptbase"      <- the FIRST +Script: is the base/default (index 0)
        +Dialogue: N N          (optional, per script)
        +Levelcap: N            (optional, per level/script)
    // comment                  (optional)
    +Script:  "scriptbase_v2"   <- additional scripts (indices 1..6)
    ...
    #End

The table lives in a member of TABLES.VPP. We do NOT copy any game bytes into the repo; we emit
only NAMES (level names + script filenames), which is metadata, matching the door-triggers.json /
transitions.json precedent.

Read-only against the retail ISO. Cross-checks:
  1. the 51-level inventory in door-mechanism.md section 3 (must match exactly);
  2. the 128 no-script doors in transitions.json (safe vs unsafe target counts).
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import discover  # noqa: E402

ISO = Path(r"C:\temp\NTO_Live_Code\Summoner (USA)\Summoner (USA).iso")
LAB = Path(os.path.dirname(os.path.abspath(__file__)))
OUT = LAB / "level_scripts.json"
TRANSITIONS = LAB / "transitions.json"

# The table body starts at the first $Level: after the "CHANGING THE ORDER" warning banner and
# ends at the "#End" marker. We locate both by content, then parse ONLY that slice - never the
# 191 other $Level: lines scattered in per-level .tbl / dialogue members.
BANNER = b"CHANGING THE ORDER IN WHICH THE SCRIPTS APPEAR"
END_MARK = b"#End"

# The 51-level inventory from door-mechanism.md section 3 (Level_info order), for cross-check.
LEVEL_INFO_51 = [
    "Wolong", "Catacombs", "test", "masad", "worldmap1", "lenele1b", "lenele1c", "lenele1d",
    "lenele1e", "sewer", "rand-hills01", "IkaemosBottomInt", "IkaemosTopInt", "IkaemosExt",
    "KhosaniLab", "IonaExt", "WolongCaverns", "TempleInt", "rand-forest01", "rand-forestnite1",
    "Liangshan", "Rand-Desert", "IonaExt02", "KhosaniStrng", "LPalaceInt", "tancredhouse",
    "LPalaceInt02", "KhosaniLab2", "Wolong2", "eleh", "lenele2aa", "lenele2ab", "lenele3a",
    "lenele3d", "jadetemple", "lenele1aa", "lenele1ab", "TempleInt2", "IkaemosExt2",
    "IkaemosBottomInt2", "Rand-HillsNite01", "Rand-Iceland01", "Rand-Grassland01",
    "Rand-Orenia01", "Rand-OreniaNite01", "Rand-DesertNite01", "Rand-GrasslandNite01",
    "Rand-IcelandNite01", "endgame", "lenele2d", "sewerboss",
]

LEVEL_RE = re.compile(rb'\$Level:\s*"([^"\r\n]{1,40})"')
SCRIPT_RE = re.compile(rb'\+Script:\s*"([^"\r\n]{1,40})"')


def norm(s: str) -> str:
    """case-insensitive comparison key (ngps_stricmp is a plain case-fold, no punctuation strip)."""
    return s.lower()


def parse_table(blob: bytes):
    b = blob.find(BANNER)
    if b < 0:
        raise SystemExit("REFUSED: could not find the script_filenames.tbl warning banner")
    first = LEVEL_RE.search(blob, b)
    if not first:
        raise SystemExit("REFUSED: no $Level: after the banner")
    start = first.start()
    end = blob.find(END_MARK, start)
    if end < 0:
        raise SystemExit("REFUSED: no #End marker after the table start")
    body = blob[start:end]

    # Split into per-$Level: records. Each record = from its $Level: to the next $Level:.
    lvl_iters = list(LEVEL_RE.finditer(body))
    records = []
    for i, m in enumerate(lvl_iters):
        name = m.group(1).decode("latin-1")
        seg_end = lvl_iters[i + 1].start() if i + 1 < len(lvl_iters) else len(body)
        seg = body[m.end():seg_end]
        scripts = [s.group(1).decode("latin-1") for s in SCRIPT_RE.finditer(seg)]
        records.append((name, scripts))
    return start, end, records


def main():
    info = discover.identify(str(ISO))
    t = discover.find_tables(info.vpps)
    with open(ISO, "rb") as f:
        f.seek(t.base)
        blob = f.read(t.total_size)

    start, end, records = parse_table(blob)
    print(f"table body: vpp 0x{start:X}..0x{end:X} (iso 0x{t.base+start:X}), {len(records)} $Level: records")

    # --- Cross-check 1: the 51-level inventory ---
    parsed_names = [n for n, _ in records]
    if len(records) != 51:
        print(f"WARNING: expected 51 $Level: records, got {len(records)}")
    set_parsed = {norm(n) for n in parsed_names}
    set_51 = {norm(n) for n in LEVEL_INFO_51}
    missing = sorted(set_51 - set_parsed)   # in Level_info but not in the script table
    extra = sorted(set_parsed - set_51)     # in the script table but not in Level_info
    print(f"cross-check vs 51-level inventory: missing_from_table={missing}  extra_in_table={extra}")

    # --- Build the per-level map + safety boolean ---
    levels = {}
    for name, scripts in records:
        base = scripts[0] if scripts else None
        # A no-script door targeting this level is SAFE iff the destination NAME resolves to a
        # script this level provides. The name used is the level name; the engine searches ALL
        # of this level's scripts (Level_script_info[level][0..6]) with ngps_stricmp. So SAFE iff
        # ANY of this level's scripts equals the level name case-insensitively. (The base script
        # is index 0 and is what's loaded first, but the search is over the whole list.)
        provides_self = any(norm(s) == norm(name) for s in scripts)
        base_is_self = (base is not None and norm(base) == norm(name))
        levels[name] = {
            "scripts": scripts,
            "base_script": base,
            "base_is_name": base_is_self,
            "provides_name_script": provides_self,
            "safe_no_script_target": provides_self,
        }

    safe = sorted([n for n, v in levels.items() if v["safe_no_script_target"]], key=str.lower)
    unsafe = sorted([n for n, v in levels.items() if not v["safe_no_script_target"]], key=str.lower)
    print(f"\nlevels SAFE as a no-script target ({len(safe)}): {safe}")
    print(f"levels UNSAFE as a no-script target ({len(unsafe)}): {unsafe}")

    # --- Cross-check 3: the no-script doors in transitions.json ---
    door_report = None
    if TRANSITIONS.is_file():
        tr = json.loads(TRANSITIONS.read_text(encoding="utf-8"))
        doors = tr.get("doors", [])
        no_script = [d for d in doors if not d.get("has_script")]
        with_script = [d for d in doors if d.get("has_script")]
        safe_norm = {norm(n) for n in safe}
        # index the safety by normalized level name
        by_norm = {norm(n): v for n, v in levels.items()}
        safe_doors, unsafe_doors, unknown_doors = [], [], []
        for d in no_script:
            dn = norm(d["dest"])
            if dn in safe_norm:
                safe_doors.append(d)
            elif dn in by_norm:
                unsafe_doors.append(d)
            else:
                unknown_doors.append(d)  # dest not even in the 51-level table
        from collections import Counter
        unsafe_dest_counts = Counter(d["dest"] for d in unsafe_doors)
        unknown_dest_counts = Counter(d["dest"] for d in unknown_doors)
        door_report = {
            "total_doors": len(doors),
            "with_script": len(with_script),
            "no_script": len(no_script),
            "no_script_safe": len(safe_doors),
            "no_script_unsafe": len(unsafe_doors),
            "no_script_unknown_dest": len(unknown_doors),
            "unsafe_dest_counts": dict(unsafe_dest_counts),
            "unknown_dest_counts": dict(unknown_dest_counts),
        }
        print("\n--- no-script door cross-check (transitions.json) ---")
        print(f"total doors: {len(doors)}   with +Script: {len(with_script)}   no +Script: {len(no_script)}")
        print(f"no-script doors targeting a SAFE level:   {len(safe_doors)}")
        print(f"no-script doors targeting an UNSAFE level: {len(unsafe_doors)}  {dict(unsafe_dest_counts)}")
        print(f"no-script doors targeting a dest NOT in the 51-level table: {len(unknown_doors)}  {dict(unknown_dest_counts)}")
    else:
        print("\n(transitions.json not found - skipping door cross-check)")

    # --- Emit level_scripts.json (NAMES only; derived metadata artifact) ---
    export = {
        "_note": ("Authoritative level->script map parsed from script_filenames.tbl in TABLES.VPP. "
                  "NAMES only (derived metadata, like door-triggers.json). No game data bytes."),
        "iso": ISO.name,
        "tables_base": t.base,
        "table_body_vpp": [start, end],
        "table_body_iso": [t.base + start, t.base + end],
        "level_count": len(records),
        "cross_check_51": {"missing_from_table": missing, "extra_in_table": extra,
                           "matches_inventory": (not missing and not extra and len(records) == 51)},
        "safe_no_script_targets": safe,
        "unsafe_no_script_targets": unsafe,
        "levels": levels,
        "door_cross_check": door_report,
    }
    OUT.write_text(json.dumps(export, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
